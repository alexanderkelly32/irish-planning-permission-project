"""Runner: per-pixel change feature extraction (batched, EE-side).

For each year: cosine-change image vs prior year -> reduceRegions over all
646 polygons (median, p90, mean) + per-site heterogeneity (mean |pixel -
site mean|). Appends columns to alphaearth_features.csv. Resume-safe.
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
YEARS = list(range(2018, 2026))
BAND_NAMES = [f"A{i:02d}" for i in range(64)]


def build_fc() -> ee.FeatureCollection:
    geojson = json.loads(POLYGONS_PATH.read_text(encoding="utf-8"))
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry(feature["geometry"]), {"development_id": feature["properties"]["development_id"]})
        for feature in geojson["features"]
    ])


def cosine_change_image(prev: ee.Image, curr: ee.Image) -> ee.Image:
    def per_pixel(pair):
        a = pair.select(BAND_NAMES).toArray()
        b = ee.Image(pair.get("curr")).select(BAND_NAMES).toArray()
        dot = a.multiply(b).arrayReduce(ee.Reducer.sum(), [0])
        norm = a.multiply(a).arrayReduce(ee.Reducer.sum(), [0]).sqrt().multiply(
            b.multiply(b).arrayReduce(ee.Reducer.sum(), [0]).sqrt())
        similarity = dot.divide(norm).clamp(0, 1)
        return ee.Image(1).subtract(similarity).rename("change")
    return ee.Image.cat([per_pixel(ee.Image(prev).addBands(curr))])


if __name__ == "__main__":
    ee.Initialize(project="planning-project-1")
    state_path = OUT_DIR / "change_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"years_done": []}
    collection = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL").filterDate("2017-01-01", "2025-12-31")
    images = {year: collection.filterDate(f"{year}-01-01", f"{year}-12-31").mosaic() for year in range(2017, 2026)}
    fc = build_fc()
    features_csv = OUT_DIR / "alphaearth_features.csv"
    frame = pd.read_csv(features_csv) if features_csv.exists() and features_csv.stat().st_size > 0 else pd.DataFrame()
    state = {y for y in state["years_done"]} if state["years_done"] else set()

    for year in YEARS:
        if year in state:
            continue
        prev = images[year - 1]
        curr = images[year]
        # per-pixel cosine change via array ops on a joined image
        dot = prev.select(BAND_NAMES).toArray().multiply(curr.select(BAND_NAMES).toArray()).arrayReduce(ee.Reducer.sum(), [0]).arrayGet([0])
        norm_a = prev.select(BAND_NAMES).toArray().multiply(prev.select(BAND_NAMES).toArray()).arrayReduce(ee.Reducer.sum(), [0]).arrayGet([0]).sqrt()
        norm_b = curr.select(BAND_NAMES).toArray().multiply(curr.select(BAND_NAMES).toArray()).arrayReduce(ee.Reducer.sum(), [0]).arrayGet([0]).sqrt()
        similarity = dot.divide(norm_a.multiply(norm_b)).clamp(0, 1)
        change = ee.Image(1).subtract(similarity).rename("change")

        change_stats = change.reduceRegions(
            collection=fc, reducer=ee.Reducer.mean().combine(ee.Reducer.median(), sharedInputs=True).combine(
                ee.Reducer.percentile([90]), sharedInputs=True), scale=10).getInfo()
        change_by_dev = {f["properties"]["development_id"]: f["properties"] for f in change_stats["features"]}

        # heterogeneity: mean |pixel - site_mean|, per band then averaged
        site_means = curr.select(BAND_NAMES).reduceRegions(
            collection=fc, reducer=ee.Reducer.mean(), scale=10).getInfo()
        hetero_rows = []
        for feature in site_means["features"]:
            dev_id = feature["properties"]["development_id"]
            means = ee.Image.constant([feature["properties"].get(b, 0.0) for b in BAND_NAMES])
            diff = curr.select(BAND_NAMES).toArray().subtract(means.toArray()).abs().arrayReduce(ee.Reducer.sum(), [0]).arrayGet([0])
            value = ee.Image(diff).rename("hetero").reduceRegion(
                reducer=ee.Reducer.mean(), geometry=ee.Geometry(feature["geometry"]), scale=10, maxPixels=1e9).getInfo()
            hetero_rows.append({"development_id": dev_id, "heterogeneity": float(value.get("hetero", 0.0))})
        hetero_by_dev = {r["development_id"]: r for r in hetero_rows}

        year_rows = []
        for dev_id, stats in change_by_dev.items():
            row = {"development_id": dev_id, "year": year,
                   "change_mean": float(stats.get("change_mean", 0.0)),
                   "change_median": float(stats.get("change_median", 0.0)),
                   "change_p90": float(stats.get("change_p90", 0.0))}
            hetero = hetero_by_dev.get(dev_id, {})
            row["heterogeneity"] = float(hetero.get("heterogeneity", 0.0))
            year_rows.append(row)
        year_frame = pd.DataFrame(year_rows)
        frame = frame.merge(year_frame, on=["development_id", "year"], how="outer")
        for column in year_frame.columns:
            if column not in ("development_id", "year"):
                base_col = column
                if f"{base_col}_x" in frame.columns:
                    frame[base_col] = frame[f"{base_col}_y"].fillna(frame[f"{base_col}_x"])
                    frame = frame.drop(columns=[f"{base_col}_x", f"{base_col}_y"])
        frame.to_csv(features_csv, index=False)
        state.add(year)
        state_path.write_text(json.dumps({"years_done": sorted(state)}), encoding="utf-8")
        print(f"year {year}: {len(year_rows)} sites", flush=True)

    print(json.dumps({"years_done": sorted(state), "rows": int(len(frame))}, indent=2))
