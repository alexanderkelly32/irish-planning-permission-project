"""Runner: ABP appeal ingest - first-stage API discovery probe.

The ABP case search is a JS app. This stage fetches the page + its JS bundle,
extracts candidate API endpoints, tries the most common patterns, and logs
what responds. Findings guide the real scraper.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from devrisk import settings  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) planning-risk-review/1.0 (local research)"}
OUT_DIR = settings.SILVER_DIR / "abp"
BASE = "https://www.pleanala.ie"


def probe(url: str, method: str = "GET", **kwargs) -> dict:
    try:
        response = requests.request(method, url, timeout=60, headers=HEADERS, **kwargs)
        return {"status": response.status_code, "len": len(response.text), "type": response.headers.get("content-type", "")[:40]}
    except Exception as error:  # noqa: BLE001
        return {"error": f"{type(error).__name__}: {str(error)[:120]}"}


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    page = requests.get(f"{BASE}/en-ie/case-search", timeout=60, headers=HEADERS)
    html = page.text
    js_urls = sorted(set(re.findall(r'(?:src|href)="([^"]+\.js[^"]*)"', html)))
    results["page"] = {"status": page.status_code, "js_bundles": js_urls[:6]}

    # Common ABP API patterns.
    for name, url in (
        ("search_api", f"{BASE}/api/search"),
        ("cases_api", f"{BASE}/api/cases"),
        ("case_list_web", f"{BASE}/en-ie/case-list"),
        ("weekly_lists", f"{BASE}/en-ie/decisions-weekly"),
        ("sitemap", f"{BASE}/sitemap.xml"),
    ):
        results[name] = probe(url)

    # Extract api-ish strings from the main JS bundle.
    for js in js_urls[:3]:
        js_url = js if js.startswith("http") else BASE + js
        try:
            js_text = requests.get(js_url, timeout=60, headers=HEADERS).text
            api_strings = sorted(set(re.findall(r'["\'](/[a-zA-Z0-9\-_/]+(?:search|case|decision|list)[a-zA-Z0-9\-_/]*)["\']', js_text)))[:10]
            results[f"js_{js[:40]}"] = {"len": len(js_text), "api_strings": api_strings}
        except Exception as error:  # noqa: BLE001
            results[f"js_{js[:40]}"] = {"error": str(error)[:120]}

    out = OUT_DIR / "api_probe.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
