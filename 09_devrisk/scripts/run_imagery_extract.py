"""Stage 1 extraction v2: BATCHED monthly Sentinel-1/2 via reduceRegions.

One EE request per month per sensor over all 41 site polygons (vs 41
requests before - removes the throttle bottleneck). Resume-safe: months
already written are skipped. Output: silver/imagery/sentinel_monthly.csv.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import ee  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "imagery"
STATE = OUT / "extract_state_v2.json"
OUTFILE = OUT / "sentinel_monthly.csv"


def mask_s2(img):
    qa = img.select("QA60")
    cloud = qa.bitwiseAnd(1 << 10).Or(qa.bitwiseAnd(1 << 11))
    scl = img.select("SCL")
    keep = cloud.eq(0).And(scl.eq(3).eq(0)).And(scl.neq(9))
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndbi = img.normalizedDifference(["B11", "B8"]).rename("NDBI")
    return (img.addBands([ndvi, ndbi])
            .updateMask(keep)
            .select(["B2", "B4", "B8", "B11", "NDVI", "NDBI"]))


def main() -> None:
    ee.Initialize(project="planning-project-1")
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"done": []}
    done = set(state["done"])
    geo = json.loads((SILVER / "site_polygons.geojson").read_text(encoding="utf-8"))
    cohort = pd.read_csv(OUT / "feasibility_50.csv", dtype=str)
    ids = set(cohort["case_key"])
    feats = []
    for f in geo["features"]:
        pid = f["properties"]["development_id"]
        if pid in ids:
            feats.append(ee.Feature(ee.Geometry(f["geometry"]), {"id": pid}))
    fc = ee.FeatureCollection(feats)
    print("sites:", len(feats), flush=True)

    months = [(y, m) for y in range(2018, 2027) for m in range(1, 13)
              if (y < 2026) or m <= 10]
    existing = pd.read_csv(OUTFILE) if OUTFILE.exists() else pd.DataFrame()
    existing_ym = set(existing["ym"].astype(str)) if len(existing) else set()
    for y, m in months:
        ym = f"{y}-{m:02d}"
        if ym in done or ym in existing_ym:
            continue
        start = f"{y}-{m:02d}-01"
        end = f"{y}-{m:02d}-28"
        rows = []
        try:
            s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                  .filterDate(start, end).filterBounds(fc.geometry()).map(mask_s2))
            if s2.size().getInfo() > 0:
                med2 = s2.median()
                n2 = s2.select("NDVI").count().rename("n_obs")
                red2 = med2.reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                                          scale=10, tileScale=2).getInfo()
                red2n = n2.reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                                         scale=10, tileScale=2).getInfo()
                by_id = {f["properties"]["id"]: f["properties"] for f in red2["features"]}
                by_n = {f["properties"]["id"]: f["properties"] for f in red2n["features"]}
            else:
                by_id = {}
                by_n = {}
            s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
                  .filterDate(start, end).filterBounds(fc.geometry())
                  .filter(ee.Filter.eq("instrumentMode", "IW"))
                  .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")))
            if s1.size().getInfo() > 0:
                med1 = s1.select(["VV", "VH"]).median()
                red1 = med1.reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                                          scale=10, tileScale=2).getInfo()
                by_1 = {f["properties"]["id"]: f["properties"] for f in red1["features"]}
            else:
                by_1 = {}
            for pid in ids:
                r2 = by_id.get(pid, {})
                rn = by_n.get(pid, {})
                r1 = by_1.get(pid, {})
                rows.append({"development_id": pid, "ym": ym,
                             "s2_ndvi": r2.get("NDVI"), "s2_ndbi": r2.get("NDBI"),
                             "s2_b2": r2.get("B2"), "s2_b4": r2.get("B4"),
                             "s2_b8": r2.get("B8"), "s2_b11": r2.get("B11"),
                             "s2_valid_px": rn.get("n_obs"),
                             "s1_vv": r1.get("VV"), "s1_vh": r1.get("VH")})
        except Exception as exc:
            print(f"{ym} error {str(exc)[:100]}", flush=True)
        if rows:
            frame = pd.DataFrame(rows)
            if len(existing):
                frame = pd.concat([existing, frame], ignore_index=True)
            frame.to_csv(OUTFILE, index=False)
            existing = frame
        done.add(ym)
        state["done"] = sorted(done)
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"{ym} total_rows={len(existing)}", flush=True)
        time.sleep(0.3)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
