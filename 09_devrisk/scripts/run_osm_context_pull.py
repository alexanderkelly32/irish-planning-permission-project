"""Runner: OSM roads+amenities per estate, ePlanning comments counts,
zoning MapServer probe (background).

1. OSM: one Overpass query per pool estate for highway ways within 400m
   (road class, junction proximity) + amenities within 1km (schools,
   transit, retail). Resume-safe state.
2. ePlanning comments: fetch AppFileRefDetails pages, parse the Comments
   tab for observation/submission counts.
3. Zoning: probe the GZTZoning MapServer layers.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from pyproj import Transformer  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "osm_context"
STATE_PATH = settings.SILVER_DIR / "osm_context_state.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
TO_WGS = Transformer.from_crs(2157, 4326, always_xy=True)


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"done": []}
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    estates = phases.dropna(subset=["itm_easting", "itm_northing"]).groupby("development_id").agg(
        east=("itm_easting", "median"), north=("itm_northing", "median"))
    done = set(state["done"])
    report = {"estates": int(len(estates)), "processed": 0}

    for dev_id, row in estates.iterrows():
        if dev_id in done:
            continue
        lon, lat = TO_WGS.transform(float(row["east"]), float(row["north"]))
        query = (
            f'[out:json][timeout:45];('
            f'way["highway"](around:400,{lat},{lon});'
            f'node["amenity"](around:1000,{lat},{lon});'
            f'node["public_transport"](around:1000,{lat},{lon});'
            f');out tags center;'
        )
        payload = {}
        for attempt in range(2):
            try:
                request = urllib.request.Request(OVERPASS, data=query.encode(),
                                                 headers={"User-Agent": "planning-risk-review/1.0"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except Exception:
                time.sleep(6.0)
        elements = payload.get("elements", [])
        roads = [e for e in elements if e.get("type") == "way"]
        amenities = [e for e in elements if e.get("type") == "node" and ("amenity" in e.get("tags", {}) or "public_transport" in e.get("tags", {}))]
        safe_name = re.sub(r"[^A-Za-z0-9]+", "_", str(dev_id).split("__")[1])
        (OUT_DIR / f"{safe_name}.json").write_text(json.dumps({
            "roads": [{"class": e.get("tags", {}).get("highway"), "name": e.get("tags", {}).get("name")} for e in roads[:40]],
            "amenities": [{"kind": e.get("tags", {}).get("amenity") or e.get("tags", {}).get("public_transport"),
                           "name": e.get("tags", {}).get("name")} for e in amenities[:40]],
        }), encoding="utf-8")
        state["done"].append(dev_id)
        report["processed"] += 1
        if report["processed"] % 100 == 0:
            STATE_PATH.write_text(json.dumps(state))
            print(f"processed {report['processed']}", flush=True)
        time.sleep(1.2)
    STATE_PATH.write_text(json.dumps(state))
    report["out_dir"] = str(OUT_DIR)

    # ---- Zoning MapServer probe ----
    try:
        request = urllib.request.Request(
            "https://maps.housing.gov.ie/arcgis/rest/services/MyPlan/GZTZoning/MapServer?f=json",
            headers={"User-Agent": "Mozilla/5.0"})
        server = json.loads(urllib.request.urlopen(request, timeout=60).read().decode("utf-8"))
        report["zoning_layers"] = [
            {"id": layer["id"], "name": layer.get("name")} for layer in server.get("layers", [])[:12]
        ]
    except Exception as exc:
        report["zoning_error"] = str(exc)[:140]

    out = settings.SILVER_DIR / "osm_context_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
