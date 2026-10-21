"""Runner: pull TED procurement notices (construction, Ireland) via API.

TED (Tenders Electronic Daily) has a free JSON API. Queries contract-award
and prior-information notices for CPV construction works, Ireland, 2019+.
Saves raw JSONL to raw/ted/; parsing (contractor, value, dates, scheme match)
is a follow-up. Probe-first: if the API shape differs, snapshot whatever
comes back.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "ted"
USER_AGENT = "Mozilla/5.0 planning-risk-review/1.0 (local personal research)"
API = "https://api.ted.europa.eu/v3/notices/search"


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for query in (
        {"query": 'CPV=45000000 AND place-of-performance="IE" AND notice-type IN (7,2)', "note": "construction contract awards + notices IE"},
        {"query": 'CPV=45210000 AND place-of-performance="IE" AND notice-type=7', "note": "building construction awards IE"},
    ):
        for page in range(1, 11):
            payload = {
                "query": query["query"],
                "fields": ["publication-number", "publication-date", "title", "buyer-name",
                           "place-of-performance", "cpv-codes", "notice-type", "contract-nature",
                           "awarded-contract", "procurement-documents", "notice-sent-date"],
                "page": page,
                "limit": 100,
                "language": "en",
            }
            try:
                data = post_json(API, payload)
            except Exception as exc:
                print(json.dumps({"error": str(exc), "query": query, "page": page}), flush=True)
                break
            notices = data.get("notices") or data.get("results") or []
            if not notices:
                break
            for notice in notices:
                notice["_query_note"] = query["note"]
                rows.append(notice)
            print(f"page {page}: +{len(notices)} (total {len(rows)})", flush=True)
            time.sleep(1.0)
    out = OUT_DIR / "ted_construction_ie.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows), "out": str(out)}), flush=True)
