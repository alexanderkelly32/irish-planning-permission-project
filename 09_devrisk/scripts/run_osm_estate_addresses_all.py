"""Runner: OSM address pull for ALL pool estates via Overpass (light).

One light query per estate (addr:housenumber nodes + buildings with addr,
+-600m), 2s spacing, resume-safe state. Covers exactly our estates - no
national mirror needed. Feeds the v2 confirmation inventory.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from pyproj import Transformer  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "osm_estates"
STATE_PATH = settings.SILVER_DIR / "osm_estate_pull_state.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
TO_WGS = Transformer.from_crs(2157, 4326, always_xy=True)


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"done": {}}
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    estates = phases.dropna(subset=["itm_easting", "itm_northing"]).groupby("development_id").agg(
        centre_e=("itm_easting", "median"), centre_n=("itm_northing", "median")).reset_index()

    for _, estate in estates.iterrows():
        dev_id = str(estate["development_id"])
        if dev_id in state["done"]:
            continue
        lon, lat = TO_WGS.transform(float(estate["centre_e"]), float(estate["centre_n"]))
        d = 0.0055
        query = f'[out:json][timeout:45];(node["addr:housenumber"]({lat-d},{lon-d},{lat+d},{lon+d});way["addr:housenumber"]({lat-d},{lon-d},{lat+d},{lon+d}););out tags center;'
        for attempt in range(2):
            try:
                request = urllib.request.Request(OVERPASS, data=query.encode(),
                                                 headers={"User-Agent": "planning-risk-review/1.0 (local research)"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                (OUT_DIR / f"{dev_id.split('__')[1]}.geojson").write_text(json.dumps(payload), encoding="utf-8")
                state["done"][dev_id] = len(payload.get("elements", []))
                break
            except Exception:
                time.sleep(8.0)
        else:
            state["done"][dev_id] = -1
        if len(state["done"]) % 50 == 0:
            STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
            print(f"done {len(state['done'])}", flush=True)
        time.sleep(2.0)

    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
    counts = [v for v in state["done"].values() if isinstance(v, int) and v >= 0]
    summary = {"estates": len(state["done"]), "with_addresses": int(sum(1 for c in counts if c > 0)),
               "address_elements_total": int(sum(counts)), "out_dir": str(OUT_DIR)}
    (settings.SILVER_DIR / "osm_estate_pull_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
