"""Runner: archaeology-event features (SMR sites within site polygons).

SMR bulk CSV -> spatial join against site polygons: count of monuments
inside/within 250m, nearest distance, monument-class diversity. Ablation
on commencement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402
from shapely import STRtree  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)

if __name__ == "__main__":
    smr = pd.read_csv(settings.RAW_DIR / "smr" / "smr_sites.csv", low_memory=False)
    lon_col = next((c for c in smr.columns if c.lower() in ("x", "lon", "longitude", "itme", "easting")), None)
    lat_col = next((c for c in smr.columns if c.lower() in ("y", "lat", "latitude", "itmn", "northing")), None)
    print("coords:", lon_col, lat_col, "| rows:", len(smr))
    from pyproj import Transformer  # noqa: E402
    to_itm = Transformer.from_crs(4326, 2157, always_xy=True)
    smr["east"] = pd.to_numeric(smr[lon_col], errors="coerce")
    smr["north"] = pd.to_numeric(smr[lat_col], errors="coerce")
    smr = smr.dropna(subset=["east", "north"])
    # Handle EPSG: if coords look like ITM already (x>100000), skip transform
    if smr["east"].median() < 100:
        east, north = to_itm.transform(smr["east"].to_numpy(), smr["north"].to_numpy())
        smr["east"], smr["north"] = east, north
    tree = STRtree([Point(x, y) for x, y in zip(smr["east"], smr["north"], strict=False)])
    class_col = next((c for c in smr.columns if "class" in c.lower() or "monument" in c.lower() or "sites_and" in c.lower()), None)
    classes = smr[class_col].astype(str).to_numpy() if class_col else np.full(len(smr), "")

    polygons = json.loads((settings.SILVER_DIR / "site_polygons.geojson").read_text(encoding="utf-8"))
    rows = []
    for feature in polygons["features"]:
        polygon = shape(feature["geometry"])
        idx = tree.query(polygon)
        nearby = idx if isinstance(idx, list) else idx.tolist()
        inside = [i for i in nearby if polygon.contains(Point(smr.iloc[i]["east"], smr.iloc[i]["north"]))]
        rows.append({
            "case_key": str(feature["properties"]["development_id"]),
            "smr_within_site": len(inside),
            "smr_within_250m": len(nearby),
            "smr_class_diversity": int(len(set(classes[nearby]))) if nearby else 0,
        })
    features = pd.DataFrame(rows)
    features.to_csv(settings.SILVER_DIR / "archaeology_event_features.csv", index=False)

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    base = labels.merge(reg, on="case_key", how="inner").merge(features, on="case_key", how="left")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    CBASE = ["log_units", "type_apartment", "grant_year"]
    ARCH = ["smr_within_site", "smr_within_250m", "smr_class_diversity"]

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        return np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)

    p_base, p_arch = run(CBASE), run(CBASE + ARCH)
    y = test["activation"].to_numpy()
    report = {
        "scheme_coverage": round(float(base["smr_within_site"].notna().mean()), 3),
        "n_train": int(len(train)), "n_test": int(len(test)),
        "base_mae": round(float(np.mean(np.abs(y - p_base))), 0),
        "arch_mae": round(float(np.mean(np.abs(y - p_arch))), 0),
        "delta": round(float(np.mean(np.abs(y - p_arch)) - np.mean(np.abs(y - p_base))), 0),
    }
    out = settings.SILVER_DIR / "archaeology_event_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
