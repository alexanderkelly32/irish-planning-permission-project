"""Runner: parcel geometry features + ablation.

From site_polygons.geojson: area, perimeter, compactness, frontage proxy
(longest bounding-box side), elongation. Ablation on commencement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import shape  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)


if __name__ == "__main__":
    geojson = json.loads((settings.SILVER_DIR / "site_polygons.geojson").read_text(encoding="utf-8"))
    rows = []
    for feature in geojson["features"]:
        polygon = shape(feature["geometry"])
        minx, miny, maxx, maxy = polygon.bounds
        width = maxx - minx
        height = maxy - miny
        perimeter = polygon.length
        area = polygon.area
        compactness = 4 * np.pi * area / max(perimeter ** 2, 1e-9)
        rows.append({
            "case_key": str(feature["properties"]["development_id"]),
            "parcel_area_m2": float(area),
            "parcel_perimeter_m": float(perimeter),
            "parcel_compactness": float(compactness),
            "parcel_frontage_proxy_m": float(min(width, height)),
            "parcel_elongation": float(max(width, height) / max(min(width, height), 1e-9)),
        })
    geometry_features = pd.DataFrame(rows)
    geometry_features.to_csv(settings.SILVER_DIR / "parcel_geometry_features.csv", index=False)

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    base = labels.merge(reg, on="case_key", how="inner").merge(geometry_features, on="case_key", how="left")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    CBASE = ["log_units", "type_apartment", "grant_year"]
    GEO = [c for c in geometry_features.columns if c != "case_key"]

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        return np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)

    p_base, p_geo = run(CBASE), run(CBASE + GEO)
    y = test["activation"].to_numpy()
    report = {
        "sites_with_geometry": int(len(geometry_features)),
        "n_train": int(len(train)), "n_test": int(len(test)),
        "base_mae": round(float(np.mean(np.abs(y - p_base))), 0),
        "geo_mae": round(float(np.mean(np.abs(y - p_geo))), 0),
        "delta": round(float(np.mean(np.abs(y - p_geo)) - np.mean(np.abs(y - p_base))), 0),
    }
    out = settings.SILVER_DIR / "parcel_geometry_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
