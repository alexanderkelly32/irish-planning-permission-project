#!/usr/bin/env python3
"""Fetch missing council written statements from official pages.

Enumerates PDF links on each council's plan page, downloads policy-bearing
files (written statement / volume / chapter / general policies), verifies
PDF magic bytes, saves to 05_policy/documents/staging/<slug>/.

Usage: python 05_policy/scripts/fetch_missing_plan_docs.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "05_policy" / "documents" / "staging"
LOG_PATH = STAGING / "fetch_log.jsonl"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-IE,en;q=0.9",
}

WANTED = re.compile(
    r"(written|volume|chapter|policy|statement|core strategy|settlement|development plan|cdp)", re.IGNORECASE)
SKIP = re.compile(
    r"(map|appendix|natura|appropriate assessment|sea|strategic environmental|flood|sfra|screening|determination|record of protected|protected structure|environmental report|conclusion)", re.IGNORECASE)

TARGETS = {
    "sligo": [
        "https://www.sligococo.ie/cdp/",
        "https://www.sligococo.ie/cdp/Sligo%20CDP%202024-2030%20-%20Volume%203%20-%20General%20policies%20%28updated%20after%20Variation%20No.%201%29.pdf",
        "https://www.sligococo.ie/cdp/5.%20Appendix%20A%20-%20Infrastructural%20Assessment.pdf",
    ],
    "kerry": [
        "https://www.kerrycoco.ie/kerry-county-development-plan-2022-2028/",
    ],
    "wexford": [
        "https://www.wexfordcoco.ie/planning/development-and-local-area-plans/current-plans/wexford-county-development-plan-2022-2028",
    ],
    "offaly": [
        "https://www.offaly.ie/c/county-development-plan/",
    ],
    "roscommon": [
        "https://www.roscommoncoco.ie/en/services/planning/development-plans/",
    ],
    "carlow": [
        "https://carlow.ie/planning-and-building/forward-planning/development-plan-consultation",
    ],
    "donegal": [
        "https://www.donegalcoco.ie/en/services/planning/development-plans-strategies/county-development-plans",
    ],
    "waterford": [
        "https://waterfordcouncil.ie/documents/development-plan-2022-2028/",
    ],
}


def log_entry(entry: dict) -> None:
    with LOG_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def fetch(url: str, timeout: int = 45):
    response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    return response


def pdf_links_from(page_url: str, html: str) -> list[str]:
    links = set()
    for match in re.finditer(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html, re.IGNORECASE):
        href = match.group(1).replace("&amp;", "&")
        absolute = urljoin(page_url, href)
        if absolute.lower().endswith(".pdf") or ".pdf?" in absolute.lower():
            links.add(absolute)
    return sorted(links)


def download_file(url: str, slug: str, session: requests.Session) -> dict:
    try:
        response = session.get(url, headers=HEADERS, timeout=120)
    except requests.RequestException as exc:
        return {"url": url, "status": f"error: {type(exc).__name__} {str(exc)[:80]}"}
    if response.status_code != 200:
        return {"url": url, "status": f"http {response.status_code}"}
    data = response.content
    if not data.startswith(b"%PDF"):
        return {"url": url, "status": f"not_pdf ({data[:20]!r})"}
    name = Path(urlparse(url).path).name
    digest = hashlib.sha256(data).hexdigest()[:12]
    out = STAGING / slug / f"{digest}__{name}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return {"url": url, "status": "downloaded", "file": str(out), "bytes": len(data), "sha256": digest}


def main() -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    for slug, urls in TARGETS.items():
        print(f"=== {slug} ===", flush=True)
        page_links: set[str] = set()
        for url in urls:
            record = {"council": slug, "page": url}
            try:
                response = fetch(url)
            except requests.RequestException as exc:
                record["status"] = f"page_error {type(exc).__name__}"
                print(json.dumps(record, ensure_ascii=False), flush=True)
                log_entry(record)
                continue
            record["status"] = f"page {response.status_code}"
            print(json.dumps(record, ensure_ascii=False), flush=True)
            log_entry(record)
            if response.status_code == 200 and "text/html" in (response.headers.get("Content-Type") or ""):
                page_links.update(pdf_links_from(url, response.text))
        candidates = [u for u in page_links if WANTED.search(Path(urlparse(u).path).name) and not SKIP.search(Path(urlparse(u).path).name)]
        print(f"  {len(page_links)} pdf links, {len(candidates)} policy candidates", flush=True)
        for url in candidates:
            result = download_file(url, slug, session)
            result["council"] = slug
            print("  " + json.dumps(result, ensure_ascii=False), flush=True)
            log_entry(result)
            time.sleep(0.5)


if __name__ == "__main__":
    main()
