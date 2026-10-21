"""Granular raster export: per-site multiband GeoTIFFs for spatial build-out.

One file per site (74 polygon sites), bands:
  ndbi_2019 (pre-construction baseline), ndbi_2022, ndbi_2024, ndbi_2025
  vh_2019, vh_2023, vh_2025 (dB)
  dndbi_25v19 = NDBI_2025 - NDBI_2019
  dvh_25v19 = VH_2025 - VH_2019 (dB)

10m resolution, site geometry bounds, getDownloadURL (no Drive). Resume-safe.
Output: silver/imagery/rasters/<development_id>.tif
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import ee  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "imagery" / "rasters"
OUT.mkdir(parents=True, exist_ok=True)
STATE = SILVER / "imagery" / "raster_state.json"


def mask_s2(img):
    qa = img.select("QA60")
    cloud = qa.bitwiseAnd(1 << 10).Or(qa.bitwiseAnd(1 << 11))
    scl = img.select("SCL")
    keep = cloud.eq(0).And(scl.eq(3).eq(0)).And(scl.neq(9))
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndbi = img.normalizedDifference(["B11", "B8"]).rename("NDBI")
    return (img.addBands([ndvi, ndbi]).updateMask(keep).select(["NDVI", "NDBI"]))


def s2_med(year: int) -> ee.Image:
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterDate(start, end).map(mask_s2).select("NDBI").median())


def s1_med(year: int) -> ee.Image:
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    return (ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterDate(start, end)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .select("VH").median())


def main() -> None:
    ee.Initialize(project="planning-project-1")
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"done": []}
    done = set(state["done"])
    geo = json.loads((SILVER / "site_polygons.geojson").read_text(encoding="utf-8"))
    cohort = pd.read_csv(SILVER / "imagery" / "feasibility_100.csv", dtype=str)
    ids = set(cohort["case_key"])
    feats = {f["properties"]["development_id"]: ee.Geometry(f["geometry"])
             for f in geo["features"] if f["properties"]["development_id"] in ids}
    print("sites:", len(feats), flush=True)
    for pid, g in feats.items():
        if pid in done:
            continue
        out = OUT / f"{pid}.tif"
        try:
            n19 = s2_med(2019).rename("ndbi_2019")
            n22 = s2_med(2022).rename("ndbi_2022")
            n24 = s2_med(2024).rename("ndbi_2024")
            n25 = s2_med(2025).rename("ndbi_2025")
            v19 = s1_med(2019).rename("vh_2019")
            v23 = s1_med(2023).rename("vh_2023")
            v25 = s1_med(2025).rename("vh_2025")
            dndbi = n25.subtract(n19).rename("dndbi_25v19")
            dvh = v25.subtract(v19).rename("dvh_25v19")
            stack = ee.Image.cat([n19, n22, n24, n25, v19, v23, v25, dndbi, dvh])
            url = stack.getDownloadURL({
                "region": g.bounds(), "scale": 10, "crs": "EPSG:2157",
                "format": "GEO_TIFF", "maxPixels": 1e8})
            req = urllib.request.Request(url, headers={"User-Agent": "planning-project"})
            with urllib.request.urlopen(req, timeout=300) as resp, open(out, "wb") as fh:
                fh.write(resp.read())
            done.add(pid)
            state["done"] = sorted(done)
            STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
            print(f"ok {pid} -> {out.stat().st_size // 1024}KB", flush=True)
        except Exception as exc:
            print(f"fail {pid} {str(exc)[:120]}", flush=True)
        time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
