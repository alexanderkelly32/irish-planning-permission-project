"""Weather QC extraction: ERA5-Land daily aggregates, monthly per site.

Features per site-month: total precipitation (mm), mean/max 2m temperature,
mean 10m wind speed. Used as measurement-control features for the optical/radar
change detection (rain before acquisition, season, frost, wind).

Resume-safe. Output: silver/imagery/weather_monthly.csv
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
STATE = OUT / "weather_state.json"
OUTFILE = OUT / "weather_monthly.csv"


def main() -> None:
    ee.Initialize(project="planning-project-1")
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"done": []}
    done = set(state["done"])
    geo = json.loads((SILVER / "site_polygons.geojson").read_text(encoding="utf-8"))
    cohort = pd.read_csv(OUT / "feasibility_100.csv", dtype=str)
    ids = set(cohort["case_key"])
    feats = [ee.Feature(ee.Geometry(f["geometry"]), {"id": f["properties"]["development_id"]})
             for f in geo["features"] if f["properties"]["development_id"] in ids]
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
        try:
            coll = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").filterDate(start, end)
            if coll.size().getInfo() == 0:
                continue
            img = (ee.Image.cat([
                coll.select("total_precipitation_sum").sum().rename("precip_mm"),
                coll.select("temperature_2m_mean").mean().rename("t2m_mean"),
                coll.select("temperature_2m_max").max().rename("t2m_max"),
                coll.select("temperature_2m_min").min().rename("t2m_min"),
                coll.select("u_component_of_wind_10m_mean").mean().rename("u10"),
                coll.select("v_component_of_wind_10m_mean").mean().rename("v10"),
            ]))
            red = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=11132, tileScale=2).getInfo()
            rows = []
            for f in red["features"]:
                p = f["properties"]
                u = p.get("u10")
                v = p.get("v10")
                wind = (u * u + v * v) ** 0.5 if u is not None and v is not None else None
                rows.append({"development_id": p["id"], "ym": ym,
                             "precip_mm": p.get("precip_mm"), "t2m_mean": p.get("t2m_mean"),
                             "t2m_max": p.get("t2m_max"), "t2m_min": p.get("t2m_min"),
                             "wind_ms": wind})
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
        print(f"{ym} rows={len(existing)}", flush=True)
        time.sleep(0.2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
