"""Parser: stream-extract OSM addresses from the Ireland XML extract.

Pure stdlib: bz2 streaming + iterparse. Keeps nodes and ways carrying
addr:housenumber; writes osm_address_index.tsv (lat, lon, housenumber,
street, place, name). Background-friendly; resume not needed (single pass).
"""
from __future__ import annotations

import bz2
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

BZ2_PATH = settings.RAW_DIR / "osm_ireland" / "ireland-and-northern-ireland-latest.osm.bz2"
OUT_PATH = settings.RAW_DIR / "osm_ireland" / "osm_address_index.tsv"

WANTED_KEYS = {"addr:housenumber", "addr:street", "addr:place", "name"}


def run() -> dict:
    if not BZ2_PATH.exists():
        return {"error": f"missing {BZ2_PATH}"}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    seen = 0
    with bz2.open(BZ2_PATH, "rt", encoding="utf-8") as source, OUT_PATH.open("w", encoding="utf-8") as out:
        out.write("lat\tlon\thousenumber\tstreet\tplace\tname\n")
        context = ET.iterparse(source, events=("end",))
        for event, element in context:
            tag = element.tag
            if tag not in ("node", "way"):
                element.clear()
                continue
            seen += 1
            tags = {}
            for child in element:
                if child.tag == "tag":
                    key = child.get("k")
                    if key in WANTED_KEYS:
                        tags[key] = child.get("v")
            if "addr:housenumber" not in tags:
                element.clear()
                continue
            lat = element.get("lat")
            lon = element.get("lon")
            if lat is None or lon is None:
                element.clear()
                continue
            out.write("\t".join([
                lat, lon,
                tags.get("addr:housenumber", "").replace("\t", " "),
                tags.get("addr:street", "").replace("\t", " "),
                tags.get("addr:place", "").replace("\t", " "),
                tags.get("name", "").replace("\t", " "),
            ]) + "\n")
            kept += 1
            element.clear()
            if kept % 200000 == 0:
                print(f"kept {kept} of {seen}", flush=True)
    return {"elements_seen": seen, "addresses_kept": kept, "out": str(OUT_PATH)}


if __name__ == "__main__":
    result = run()
    import json

    (settings.RAW_DIR / "osm_ireland" / "osm_address_parse_report.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
