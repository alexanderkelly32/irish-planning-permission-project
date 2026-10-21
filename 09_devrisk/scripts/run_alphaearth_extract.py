"""Runner: AlphaEarth extraction (batched - 9 calls, not 5,800).

One reduceRegions per year over all 646 site polygons (+ one for the 100m
ring), then feature assembly client-side. Resume-safe per year.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ee  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "alphaearth"
POLYGONS_PATH = settings.SILVER_DIR / "site_polygons.geojson"
YEARS = list(range(2017, 2026))
BAND_NAMES = [f"A{i:02d}" for i in range(64)]


def build_fc() -> ee.FeatureCollection:
    geojson = json.loads(POLYGONS_PATH.read_text(encoding="utf-8"))
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry(feature["geometry"]), {"development_id": feature["properties"]["development_id"]})
        for feature in geojson["features"]
    ])


def run() -> dict:
    ee.Initialize(project="planning-project-1")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state_path = OUT_DIR / "extract_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"years_done": []}
    collection = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL").filterDate("2017-01-01", "2025-12-31")
    fc = build_fc()
    ring_fc = fc.map(lambda f: f.setGeometry(f.geometry().buffer(100)))
    report = {"ee_images": int(collection.size().getInfo()), "years_done_before": list(state["years_done"])}

    out_csv = OUT_DIR / "alphaearth_features.csv"
    previous = pd.DataFrame()
    if out_csv.exists() and out_csv.stat().st_size > 0:
        try:
            previous = pd.read_csv(out_csv)
        except Exception:
            previous = pd.DataFrame()

    for year in YEARS:
        if year in state["years_done"]:
            continue
        image = collection.filterDate(f"{year}-01-01", f"{year}-12-31").mosaic()
        site_reduced = image.select(BAND_NAMES).reduceRegions(
            collection=fc, reducer=ee.Reducer.mean(), scale=10).getInfo()
        ring_reduced = image.select(BAND_NAMES).reduceRegions(
            collection=ring_fc, reducer=ee.Reducer.mean(), scale=10).getInfo()

        rows = []
        site_by_dev = {f["properties"]["development_id"]: f["properties"] for f in site_reduced["features"]}
        ring_by_dev = {f["properties"]["development_id"]: f["properties"] for f in ring_reduced["features"]}
        for dev_id, site in site_by_dev.items():
            ring = ring_by_dev.get(dev_id, {})
            site_vector = np.array([float(site.get(band, 0.0)) for band in BAND_NAMES])
            ring_vector = np.array([float(ring.get(band, 0.0)) for band in BAND_NAMES])
            row = {"development_id": dev_id, "year": year}
            for i, value in enumerate(site_vector):
                row[f"band{i}_mean"] = value
            row["ring_mean_norm"] = float(np.linalg.norm(ring_vector))
            row["site_mean_norm"] = float(np.linalg.norm(site_vector))
            row["contrast"] = float(np.linalg.norm(site_vector - ring_vector))
            rows.append(row)

        year_frame = pd.DataFrame(rows)
        state["years_done"].append(year)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        previous = pd.concat([previous[previous["year"] != year], year_frame], ignore_index=True) if len(previous) else year_frame
        previous.to_csv(out_csv, index=False)
        print(f"year {year}: {len(rows)} sites (cumulative rows {len(previous)})", flush=True)

    report["feature_rows"] = int(len(previous))
    report["sites_covered"] = int(previous["development_id"].nunique()) if len(previous) else 0
    (OUT_DIR / "extract_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
