"""Stage 2 extraction v3: richer spatial features, 100 sites.

Per site-month:
  site: mean/std of S2 bands + NDVI/NDBI, percentiles of NDVI/NDBI,
        valid-pixel count, S1 VV/VH mean/std
  ring (250m buffer minus site): means of NDVI/NDBI/VV/VH
  changed fractions (pixel-level, site only):
        |NDBI - NDBI_base2019| > 0.20   (vs series baseline)
        |NDBI - NDBI_prev_month| > 0.12 (vs previous month)
        |VH - VH_base2019| > 2.0 dB
        |VH - VH_prev_month| > 1.2 dB

Resume-safe: months already written are skipped.
Output: silver/imagery/sentinel_monthly_v3.csv
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
STATE = OUT / "extract_state_v3.json"
OUTFILE = OUT / "sentinel_monthly_v3.csv"


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


def frac_band(cur_band, ref_band, thr):
    both = cur_band.mask().multiply(ref_band.mask())
    diff = cur_band.subtract(ref_band).abs().gt(thr).multiply(both)
    return diff, both


def main() -> None:
    ee.Initialize(project="planning-project-1")
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"done": []}
    done = set(state["done"])
    geo = json.loads((SILVER / "site_polygons.geojson").read_text(encoding="utf-8"))
    cohort = pd.read_csv(OUT / "feasibility_100.csv", dtype=str)
    ids = set(cohort["case_key"])
    feats = []
    for f in geo["features"]:
        pid = f["properties"]["development_id"]
        if pid in ids:
            g = ee.Geometry(f["geometry"])
            feats.append(ee.Feature(g, {"id": pid, "part": "site"}))
            feats.append(ee.Feature(g.buffer(250).difference(g), {"id": pid, "part": "ring"}))
    fc = ee.FeatureCollection(feats)
    print("features:", len(feats), flush=True)

    # 2019 baselines
    s2_2019 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
               .filterDate("2019-01-01", "2019-12-31").filterBounds(fc.geometry()).map(mask_s2))
    base2 = s2_2019.median().select(["NDBI"])
    s1_2019 = (ee.ImageCollection("COPERNICUS/S1_GRD")
               .filterDate("2019-01-01", "2019-12-31").filterBounds(fc.geometry())
               .filter(ee.Filter.eq("instrumentMode", "IW"))
               .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")))
    base1 = s1_2019.select(["VH"]).median()

    months = [(y, m) for y in range(2018, 2027) for m in range(1, 13)
              if (y < 2026) or m <= 10]
    existing = pd.read_csv(OUTFILE) if OUTFILE.exists() else pd.DataFrame()
    existing_ym = set(existing["ym"].astype(str)) if len(existing) else set()
    prev2 = None
    prev1 = None
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
                stats = ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True)
                red2 = med2.reduceRegions(collection=fc, reducer=stats, scale=10, tileScale=2).getInfo()
                red2n = n2.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=10, tileScale=2).getInfo()
                pct = ee.Reducer.percentile([10, 25, 75, 90], outputNames=["p10", "p25", "p75", "p90"])
                red2p = (med2.select(["NDVI", "NDBI"]).reduceRegions(
                    collection=fc.filter(ee.Filter.eq("part", "site")), reducer=pct, scale=10, tileScale=2).getInfo())
                by_id = {(f["properties"]["id"], f["properties"]["part"]): f["properties"] for f in red2["features"]}
                by_n = {f["properties"]["id"]: f["properties"] for f in red2n["features"]}
                by_p = {f["properties"]["id"]: f["properties"] for f in red2p["features"]}
            else:
                by_id, by_n, by_p = {}, {}, {}
                med2 = None
            # changed fractions vs baseline and vs prev month, batched
            frac2 = {}
            if med2 is not None:
                nb, db = frac_band(med2.select("NDBI"), base2, 0.20)
                bands = [nb.rename("num_base"), db.rename("den_base")]
                if prev2 is not None:
                    np2, dp2 = frac_band(med2.select("NDBI"), prev2.select("NDBI"), 0.12)
                    bands += [np2.rename("num_prev"), dp2.rename("den_prev")]
                fimg = ee.Image.cat(bands)
                rf = fimg.reduceRegions(collection=fc.filter(ee.Filter.eq("part", "site")),
                                        reducer=ee.Reducer.sum(), scale=10, tileScale=2).getInfo()
                for f in rf["features"]:
                    p = f["properties"]
                    den_b = p.get("den_base") or 0
                    den_p = p.get("den_prev") or 0
                    frac2[f["properties"]["id"]] = {
                        "frac_chg_ndbi_base": (p.get("num_base") or 0) / den_b if den_b else None,
                        "frac_chg_ndbi_prev": (p.get("num_prev") or 0) / den_p if den_p else None}
            s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
                  .filterDate(start, end).filterBounds(fc.geometry())
                  .filter(ee.Filter.eq("instrumentMode", "IW"))
                  .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")))
            if s1.size().getInfo() > 0:
                med1 = s1.select(["VV", "VH"]).median()
                stats1 = ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True)
                red1 = med1.reduceRegions(collection=fc, reducer=stats1, scale=10, tileScale=2).getInfo()
                by_1 = {(f["properties"]["id"], f["properties"]["part"]): f["properties"] for f in red1["features"]}
            else:
                by_1 = {}
                med1 = None
            frac1 = {}
            if med1 is not None:
                nb1, db1 = frac_band(med1.select("VH"), base1, 2.0)
                bands1 = [nb1.rename("num_base"), db1.rename("den_base")]
                if prev1 is not None:
                    np1, dp1 = frac_band(med1.select("VH"), prev1.select("VH"), 1.2)
                    bands1 += [np1.rename("num_prev"), dp1.rename("den_prev")]
                fimg1 = ee.Image.cat(bands1)
                rf1 = fimg1.reduceRegions(collection=fc.filter(ee.Filter.eq("part", "site")),
                                          reducer=ee.Reducer.sum(), scale=10, tileScale=2).getInfo()
                for f in rf1["features"]:
                    p = f["properties"]
                    den_b = p.get("den_base") or 0
                    den_p = p.get("den_prev") or 0
                    frac1[f["properties"]["id"]] = {
                        "frac_chg_vh_base": (p.get("num_base") or 0) / den_b if den_b else None,
                        "frac_chg_vh_prev": (p.get("num_prev") or 0) / den_p if den_p else None}
            for pid in ids:
                rs = by_id.get((pid, "site"), {})
                rr = by_id.get((pid, "ring"), {})
                rn = by_n.get(pid, {})
                rp = by_p.get(pid, {})
                r1s = by_1.get((pid, "site"), {})
                r1r = by_1.get((pid, "ring"), {})
                f2 = frac2.get(pid, {})
                f1 = frac1.get(pid, {})
                rows.append({"development_id": pid, "ym": ym,
                             "s2_ndvi": rs.get("NDVI_mean"), "s2_ndbi": rs.get("NDBI_mean"),
                             "s2_b2": rs.get("B2_mean"), "s2_b4": rs.get("B4_mean"),
                             "s2_b8": rs.get("B8_mean"), "s2_b11": rs.get("B11_mean"),
                             "s2_ndvi_std": rs.get("NDVI_stdDev"), "s2_ndbi_std": rs.get("NDBI_stdDev"),
                             "ndvi_p10": rp.get("NDVI_p10"), "ndvi_p25": rp.get("NDVI_p25"),
                             "ndvi_p75": rp.get("NDVI_p75"), "ndvi_p90": rp.get("NDVI_p90"),
                             "ndbi_p10": rp.get("NDBI_p10"), "ndbi_p25": rp.get("NDBI_p25"),
                             "ndbi_p75": rp.get("NDBI_p75"), "ndbi_p90": rp.get("NDBI_p90"),
                             "s2_valid_px": rn.get("n_obs"),
                             "ring_ndvi": rr.get("NDVI_mean"), "ring_ndbi": rr.get("NDBI_mean"),
                             "ring_vh": r1r.get("VH_mean"), "ring_vv": r1r.get("VV_mean"),
                             "s1_vv": r1s.get("VV_mean"), "s1_vh": r1s.get("VH_mean"),
                             "s1_vv_std": r1s.get("VV_stdDev"), "s1_vh_std": r1s.get("VH_stdDev"),
                             "frac_chg_ndbi_base": f2.get("frac_chg_ndbi_base"),
                             "frac_chg_ndbi_prev": f2.get("frac_chg_ndbi_prev"),
                             "frac_chg_vh_base": f1.get("frac_chg_vh_base"),
                             "frac_chg_vh_prev": f1.get("frac_chg_vh_prev")})
            if med2 is not None:
                prev2 = med2
            if med1 is not None:
                prev1 = med1
        except Exception as exc:
            print(f"{ym} error {str(exc)[:120]}", flush=True)
        if rows:
            frame = pd.DataFrame(rows)
            if len(existing):
                frame = pd.concat([existing, frame], ignore_index=True)
            frame.to_csv(OUTFILE, index=False)
            existing = frame
        done.add(ym)
        state["done"] = sorted(done)
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"{ym} rows={len(existing)}", flush=True)
        time.sleep(0.3)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
