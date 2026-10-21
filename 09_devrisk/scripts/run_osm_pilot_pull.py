"""Runner: OSM pilot pull - buildings + addresses for the 10 estates.

Overpass API queries per estate bbox (BCMS phase centroid +-800m): building
ways with addr:housenumber/addr:street, plus standalone addr nodes. Saves
per-estate GeoJSON; no contact, no key.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "osm_pilot"
OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = """[out:json][timeout:120];
(
  way["building"]({s},{w},{n},{e});
  node["addr:housenumber"]({s},{w},{n},{e});
  way["addr:housenumber"]({s},{w},{n},{e});
);
out geom;
"""

if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    shortlist = pd.read_csv(settings.SILVER_DIR / "phase_pilot_shortlist.csv")
    devs = set(shortlist["development_id"].astype(str))
    phase_points = phases[phases["development_id"].astype(str).isin(devs)].copy()
    phase_points = phase_points.dropna(subset=["itm_easting", "itm_northing"])
    # ITM -> WGS84
    from pyproj import Transformer  # noqa: E402
    transformer = Transformer.from_crs(2157, 4326, always_xy=True)

    report = {"estates": {}}
    for dev_id, group in phase_points.groupby("development_id"):
        east = float(group["itm_easting"].median())
        north = float(group["itm_northing"].median())
        lon, lat = transformer.transform(east, north)
        d = 0.008
        query = QUERY.format(s=lat - d, w=lon - d, n=lat + d, e=lon + d)
        try:
            request = urllib.request.Request(OVERPASS, data=query.encode(),
                                             headers={"User-Agent": "planning-risk-review/1.0 (local research)"})
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
            elements = payload.get("elements", [])
            buildings = [e for e in elements if "building" in e.get("tags", {})]
            addr_nodes = [e for e in elements if "addr:housenumber" in e.get("tags", {}) and e.get("type") == "node"]
            addr_ways = [e for e in elements if "addr:housenumber" in e.get("tags", {}) and e.get("type") == "way"]
            (OUT_DIR / f"{dev_id.split('__')[1]}.geojson").write_text(json.dumps(payload), encoding="utf-8")
            report["estates"][dev_id] = {
                "buildings": len(buildings),
                "address_nodes": len(addr_nodes),
                "address_ways": len(addr_ways),
                "elements": len(elements),
            }
        except Exception as exc:
            report["estates"][dev_id] = {"error": str(exc)[:120]}
        time.sleep(2.0)

    (settings.SILVER_DIR / "osm_pilot_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
