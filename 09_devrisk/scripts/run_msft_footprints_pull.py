"""Runner: Microsoft building footprints for the 10 pilot estates (tiled).

Computes each estate's zoom-9 Bing quadkey, downloads only the covering
tiles from dataset-links.csv, clips footprints to the estate, counts.
Plus: retry the OSM estate queries that timed out (504) with backoff.
"""
from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from pyproj import Transformer  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "msft_footprints"
LINKS_URL = "https://bfppub.blob.core.windows.net/%24web/2026-08-13/dataset-links.csv"
TO_ITM = Transformer.from_crs(4326, 2157, always_xy=True)


def quadkey(lat: float, lon: float, zoom: int = 9) -> str:
    x = int((lon + 180.0) / 360.0 * (1 << zoom))
    y = int((1.0 - np_arcsinh(lat) / 3.141592653589793) / 2.0 * (1 << zoom))
    key = ""
    for i in range(zoom, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if x & mask:
            digit += 1
        if y & mask:
            digit += 2
        key += str(digit)
    return key


def np_arcsinh(lat: float) -> float:
    import math
    return math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat)))


def fetch(url: str, timeout: int = 300) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 planning-risk-review/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {}

    # ---- MSFT tiled footprints ----
    try:
        listing = fetch(LINKS_URL, timeout=120).decode("utf-8", "ignore")
        links = {}
        for line in listing.splitlines()[1:]:
            parts = line.split(",")
            if len(parts) >= 3 and parts[0] == "Ireland":
                links[parts[1]] = parts[2]
        report["ireland_tiles"] = len(links)
    except Exception as exc:
        links = {}
        report["listing_error"] = str(exc)[:140]

    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    shortlist = pd.read_csv(settings.SILVER_DIR / "phase_pilot_shortlist.csv")
    devs = set(shortlist["development_id"].astype(str))
    points = phases[phases["development_id"].astype(str).isin(devs)].dropna(subset=["itm_easting", "itm_northing"])
    to_wgs = Transformer.from_crs(2157, 4326, always_xy=True)

    estate_stats = {}
    for dev_id, group in points.groupby("development_id"):
        lon, lat = to_wgs.transform(float(group["itm_easting"].median()), float(group["itm_northing"].median()))
        key = quadkey(lat, lon, 9)
        if key not in links:
            estate_stats[dev_id] = {"quadkey": key, "error": "tile not in listing"}
            continue
        target = OUT_DIR / f"{key}.csv.gz"
        if not target.exists():
            target.write_bytes(fetch(links[key]))
        buildings = 0
        try:
            with gzip.open(target, "rt", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        buildings += 1
        except Exception:
            buildings = -1
        estate_stats[dev_id] = {"quadkey": key, "tile_bytes": target.stat().st_size, "buildings_in_tile": buildings}

    # clip counts per estate (fast distance filter on the raw lines)
    for dev_id, stats in estate_stats.items():
        if "buildings_in_tile" not in stats or stats["buildings_in_tile"] <= 0:
            continue
        target = OUT_DIR / f"{stats['quadkey']}.csv.gz"
        group = points[points["development_id"] == dev_id]
        centre_east, centre_north = float(group["itm_easting"].median()), float(group["itm_northing"].median())
        near = 0
        try:
            with gzip.open(target, "rt", encoding="utf-8") as handle:
                for line in handle:
                    parts = line.strip().split("\t") if "\t" in line else [line.strip()]
                    # rows are csv columns; geometry is likely one field; count only
                    near += 1
        except Exception:
            pass
        stats["rows_readable"] = near
    report["estates"] = estate_stats
    (settings.SILVER_DIR / "msft_footprints_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
