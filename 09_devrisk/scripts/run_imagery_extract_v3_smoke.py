"""Smoke test: extract 2 sites x 3 months with v3 code path."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ee  # noqa: E402

import run_imagery_extract_v3 as r  # noqa: E402

SILVER = r.SILVER
OUT = r.OUT
r.OUTFILE = OUT / "sentinel_monthly_v3_smoke.csv"
r.STATE = OUT / "extract_state_v3_smoke.json"

ee.Initialize(project="planning-project-1")
geo = json.loads((SILVER / "site_polygons.geojson").read_text(encoding="utf-8"))
ids = [f["properties"]["development_id"] for f in geo["features"][:2]]
feats = []
for f in geo["features"]:
    pid = f["properties"]["development_id"]
    if pid in ids:
        g = ee.Geometry(f["geometry"])
        feats.append(ee.Feature(g, {"id": pid, "part": "site"}))
        feats.append(ee.Feature(g.buffer(250).difference(g), {"id": pid, "part": "ring"}))
fc = ee.FeatureCollection(feats)

s2_2019 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterDate("2019-01-01", "2019-12-31").filterBounds(fc.geometry()).map(r.mask_s2))
base2 = s2_2019.median().select(["NDBI"])
s1_2019 = (ee.ImageCollection("COPERNICUS/S1_GRD")
           .filterDate("2019-01-01", "2019-12-31").filterBounds(fc.geometry())
           .filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")))
base1 = s1_2019.select(["VH"]).median()

prev2 = prev1 = None
for ym in ["2021-06", "2021-07"]:
    y, m = int(ym[:4]), int(ym[5:7])
    start, end = f"{ym}-01", f"{ym}-28"
    med2 = None
    med1 = None
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterDate(start, end).filterBounds(fc.geometry()).map(r.mask_s2))
    if s2.size().getInfo() > 0:
        med2 = s2.median()
        stats = ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True)
        red2 = med2.reduceRegions(collection=fc, reducer=stats, scale=10, tileScale=2).getInfo()
        print(ym, "s2 features:", len(red2["features"]), "first keys:", list(red2["features"][0]["properties"].keys()))
    frac2 = {}
    if med2 is not None:
        nb, db = r.frac_band(med2.select("NDBI"), base2, 0.20)
        bands = [nb.rename("num_base"), db.rename("den_base")]
        if prev2 is not None:
            np2, dp2 = r.frac_band(med2.select("NDBI"), prev2.select("NDBI"), 0.12)
            bands += [np2.rename("num_prev"), dp2.rename("den_prev")]
        rf = (ee.Image.cat(bands).reduceRegions(collection=fc.filter(ee.Filter.eq("part", "site")),
                                                reducer=ee.Reducer.sum(), scale=10, tileScale=2).getInfo())
        for f in rf["features"]:
            p = f["properties"]
            db_ = p.get("den_base") or 0
            frac2[f["properties"]["id"]] = {
                "frac_chg_ndbi_base": (p.get("num_base") or 0) / db_ if db_ else None}
        print(ym, "fracs:", {k: round(v["frac_chg_ndbi_base"], 4) if v["frac_chg_ndbi_base"] is not None else None for k, v in frac2.items()})
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
          .filterDate(start, end).filterBounds(fc.geometry())
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")))
    if s1.size().getInfo() > 0:
        med1 = s1.select(["VV", "VH"]).median()
        stats1 = ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True)
        red1 = med1.reduceRegions(collection=fc, reducer=stats1, scale=10, tileScale=2).getInfo()
        print(ym, "s1 features:", len(red1["features"]))
    prev2 = med2
    prev1 = med1
print("SMOKE OK")
