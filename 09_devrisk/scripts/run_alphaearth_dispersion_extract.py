"""Runner: dispersion/interior-edge-buffer/fraction-change extraction (EE).

Per site-year: 64 band stds, interior vs edge vs 100m-ring means, and the
fraction of pixels whose change exceeds a global threshold (construction
pulse). Batched reduceRegions; appends columns to alphaearth_features.csv.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ee  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "alphaearth"
POLYGONS_PATH = settings.SILVER_DIR / "site_polygons.geojson"
YEARS = list(range(2017, 2026))
BAND_NAMES = [f"A{i:02d}" for i in range(64)]
CHANGE_THRESHOLD = 0.15


def build_fc() -> ee.FeatureCollection:
    geojson = json.loads(POLYGONS_PATH.read_text(encoding="utf-8"))
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry(feature["geometry"]), {"development_id": feature["properties"]["development_id"]})
        for feature in geojson["features"]
    ])


if __name__ == "__main__":
    ee.Initialize(project="planning-project-1")
    state_path = OUT_DIR / "dispersion_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"years_done": []}
    collection = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL").filterDate("2017-01-01", "2025-12-31")
    images = {year: collection.filterDate(f"{year}-01-01", f"{year}-12-31").mosaic() for year in YEARS}
    fc = build_fc()
    edge_fc = fc.map(lambda f: f.setGeometry(f.geometry().buffer(-40)))
    buffer_fc = fc.map(lambda f: f.setGeometry(f.geometry().buffer(100)))

    csv_path = OUT_DIR / "alphaearth_features.csv"
    frame = pd.read_csv(csv_path)
    drop_patterns = ("band_std_sum", "band_std_mean", "edge_mean_norm", "buffer_mean_norm",
                     "centre_edge_contrast", "frac_pixels_large_change")
    frame = frame.drop(columns=[c for c in frame.columns if any(c.startswith(p) for p in drop_patterns)])

    for year in YEARS:
        if year in state["years_done"]:
            continue
        image = images[year]
        std_rows = image.select(BAND_NAMES).reduceRegions(collection=fc, reducer=ee.Reducer.stdDev(), scale=10).getInfo()
        edge_rows = image.select(BAND_NAMES).reduceRegions(collection=edge_fc, reducer=ee.Reducer.mean(), scale=10).getInfo()
        buffer_rows = image.select(BAND_NAMES).reduceRegions(collection=buffer_fc, reducer=ee.Reducer.mean(), scale=10).getInfo()

        rows = []
        std_by_dev = {f["properties"]["development_id"]: f["properties"] for f in std_rows["features"]}
        edge_by_dev = {f["properties"]["development_id"]: f["properties"] for f in edge_rows["features"]}
        buffer_by_dev = {f["properties"]["development_id"]: f["properties"] for f in buffer_rows["features"]}
        for dev_id, std in std_by_dev.items():
            edge = edge_by_dev.get(dev_id, {})
            buffer = buffer_by_dev.get(dev_id, {})
            row = {"development_id": dev_id, "year": year}
            row["band_std_sum"] = sum(float(std.get(b, 0.0)) for b in BAND_NAMES)
            row["band_std_mean"] = row["band_std_sum"] / 64.0
            row["edge_mean_norm"] = sum(float(edge.get(b, 0.0)) ** 2 for b in BAND_NAMES) ** 0.5
            row["buffer_mean_norm"] = sum(float(buffer.get(b, 0.0)) ** 2 for b in BAND_NAMES) ** 0.5
            row["centre_edge_contrast"] = abs(row["edge_mean_norm"] - (row["buffer_mean_norm"] or 0))
            rows.append(row)
        year_frame = pd.DataFrame(rows)

        # fraction of pixels above the change threshold (needs prior year)
        if year >= 2018:
            prev = images[year - 1]
            dot = prev.select(BAND_NAMES).toArray().multiply(image.select(BAND_NAMES).toArray()).arrayReduce(ee.Reducer.sum(), [0]).arrayGet([0])
            norm_a = prev.select(BAND_NAMES).toArray().multiply(prev.select(BAND_NAMES).toArray()).arrayReduce(ee.Reducer.sum(), [0]).arrayGet([0]).sqrt()
            norm_b = image.select(BAND_NAMES).toArray().multiply(image.select(BAND_NAMES).toArray()).arrayReduce(ee.Reducer.sum(), [0]).arrayGet([0]).sqrt()
            change = ee.Image(1).subtract(dot.divide(norm_a.multiply(norm_b)).clamp(0, 1))
            frac = change.gt(CHANGE_THRESHOLD).rename("frac").reduceRegions(
                collection=fc, reducer=ee.Reducer.mean(), scale=10).getInfo()
            frac_by_dev = {f["properties"]["development_id"]: float(f["properties"].get("frac", 0.0)) for f in frac["features"]}
            year_frame["frac_pixels_large_change"] = year_frame["development_id"].map(frac_by_dev)

        frame = frame.merge(year_frame, on=["development_id", "year"], how="outer")
        for column in ("band_std_sum", "band_std_mean", "edge_mean_norm", "buffer_mean_norm",
                       "centre_edge_contrast", "frac_pixels_large_change"):
            if f"{column}_x" in frame.columns:
                frame[column] = frame[f"{column}_y"].fillna(frame[f"{column}_x"])
                frame = frame.drop(columns=[f"{column}_x", f"{column}_y"])
        frame.to_csv(csv_path, index=False)
        state["years_done"].append(year)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        print(f"year {year}: {len(year_frame)} sites", flush=True)

    print(json.dumps({"years_done": state["years_done"], "rows": int(len(frame))}, indent=2))
