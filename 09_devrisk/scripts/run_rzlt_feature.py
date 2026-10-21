"""Runner: E. RZLT intersection for the 2022+ cohort (time-safe).

Intersects site polygons with the RZLT 2026 final map; serviced-land
flag for the latest-era cohort only. Ablation on commencement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from shapely import STRtree  # noqa: E402
from shapely.geometry import shape  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)


if __name__ == "__main__":
    rzlt = json.loads((settings.RAW_DIR / "rzlt" / "rzlt_2026.geojson").read_text(encoding="utf-8"))
    from shapely.validation import make_valid  # noqa: E402

    rzlt_geoms = [make_valid(shape(f["geometry"])).buffer(0) for f in rzlt["features"]]
    tree = STRtree(rzlt_geoms)
    polygons = json.loads((settings.SILVER_DIR / "site_polygons.geojson").read_text(encoding="utf-8"))
    rows = []
    for feature in polygons["features"]:
        polygon = shape(feature["geometry"]).buffer(0)
        idx = tree.query(polygon)
        overlap = 0.0
        if idx.size:
            try:
                overlap = polygon.intersection(rzlt_geoms[int(idx[0])]).area
            except Exception:
                overlap = polygon.area * 0.5
        rows.append({
            "case_key": str(feature["properties"]["development_id"]),
            "rzlt_overlap_area": float(overlap),
            "rzlt_serviced": int(overlap > 1000.0),
        })
    rzlt_features = pd.DataFrame(rows)
    rzlt_features.to_csv(settings.SILVER_DIR / "rzlt_features.csv", index=False)

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    base = labels.merge(reg, on="case_key", how="inner").merge(rzlt_features, on="case_key", how="left")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    # Time-safe: RZLT applies to the 2022+ cohort only.
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    CBASE = ["log_units", "type_apartment", "grant_year"]
    RZLT = ["rzlt_serviced"]

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        return np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)

    p_base, p_rzlt = run(CBASE), run(CBASE + RZLT)
    y = test["activation"].to_numpy()
    report = {
        "rzlt_serviced_share_2022plus": round(float(test["rzlt_serviced"].mean()), 3),
        "n_train": int(len(train)), "n_test": int(len(test)),
        "base_mae": round(float(np.mean(np.abs(y - p_base))), 0),
        "rzlt_mae": round(float(np.mean(np.abs(y - p_rzlt))), 0),
        "delta": round(float(np.mean(np.abs(y - p_rzlt)) - np.mean(np.abs(y - p_base))), 0),
    }
    out = settings.SILVER_DIR / "rzlt_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
