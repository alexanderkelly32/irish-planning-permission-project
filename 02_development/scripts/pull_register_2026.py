#!/usr/bin/env python3
"""Pull all 2026 planning applications from the national ArcGIS register."""
import json
import time
from pathlib import Path

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"}
BASE = "https://services.arcgis.com/NzlPQPKn5QF9v2US/arcgis/rest/services/IrishPlanningApplications/FeatureServer/0/query"
OUT = Path(r"00_base\source_data\register_2026.jsonl")

FIELDS = "*"
rows = []
offset = 0
page_size = 2000
while True:
    params = {
        "where": "ReceivedDate >= '2026-01-01'",
        "outFields": FIELDS,
        "returnGeometry": "false",
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "orderByFields": "OBJECTID",
        "f": "json",
    }
    response = requests.get(BASE, params=params, headers=H, timeout=180)
    data = response.json()
    if "features" not in data:
        print("ERROR page:", json.dumps(data)[:300], flush=True)
        break
    features = data["features"]
    rows.extend([f["attributes"] for f in features])
    print(f"page offset={offset} got={len(features)} total={len(rows)}", flush=True)
    if len(features) < page_size:
        break
    offset += page_size
    time.sleep(0.3)

with OUT.open("w", encoding="utf-8", newline="\n") as handle:
    for row in rows:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
print("SAVED", len(rows), "rows ->", OUT, flush=True)
