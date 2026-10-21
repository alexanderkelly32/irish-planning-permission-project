"""Runner: 4Dublin pipeline - alternate ArcGIS endpoints.

Tries the ArcGIS Hub search API variants and the org item search, records
accessible dataset/service URLs for the Dublin housing pipeline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.SILVER_DIR / "4dublin"
HEADERS = {"User-Agent": "Mozilla/5.0 planning-risk-review/1.0 (local research)"}


def probe(url: str, **params) -> dict:
    try:
        response = requests.get(url, params=params, timeout=60, headers=HEADERS)
        return {"status": response.status_code, "len": len(response.text), "url": response.url[:120]}
    except Exception as error:  # noqa: BLE001
        return {"error": f"{type(error).__name__}: {str(error)[:120]}"}


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "hub_search_v3": probe("https://hub.arcgis.com/api/v3/search", q="housing supply dublin"),
        "hub_datasets_v3": probe("https://hub.arcgis.com/api/v3/datasets", q="housing dublin", limit=5),
        "arcgis_portal_search": probe(
            "https://www.arcgis.com/sharing/rest/search",
            q="dublin housing supply", f="json", num=5,
        ),
        "hub_site_html": probe("https://housinggovie.maps.arcgis.com/"),
        "hub_org_search": probe("https://hub.arcgis.com/api/search/v1/collections/datasets", q="housing dublin"),
    }
    out = OUT_DIR / "endpoint_probe.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
