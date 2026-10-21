#!/usr/bin/env python3
"""Background retrieval of missing refused-arm decision PDFs for tagging."""
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
DECISIONS = ROOT / "02_development" / "source_data" / "refused_arm_decisions"
LOG = CURRENT / "refused_arm_theme_campaign" / "decision_download_log.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/pdf,text/html,*/*;q=0.8",
}


def log(message: str) -> None:
    with LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")
    print(message, flush=True)


def main() -> None:
    merged = pd.read_csv(CURRENT / "refused_refused_audit_merged.csv", low_memory=False)
    accepted = merged[merged["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")]
    themes = pd.read_csv(CURRENT / "refused_arm_themes.csv", low_memory=False)
    tagged_keys = set(themes.loc[themes["case_primary_tags"].notna(), "original_case_key"].astype(str))
    pending = accepted[~accepted["original_case_key"].astype(str).isin(tagged_keys)]
    session = requests.Session()
    ok = failed = skipped = 0
    for _, row in pending.iterrows():
        url = str(row.get("original_source_url") or "")
        if not url.startswith("http"):
            continue
        ref = url.rsplit("/", 2)[1] if "/" in url else ""
        if not ref:
            continue
        ocr_exists = any((DECISIONS / d).exists() and (DECISIONS / d / "ocr_text" / f"{ref}_decision_ocr.txt").exists() for d in (DECISIONS.iterdir() if DECISIONS.exists() else []))
        if ocr_exists:
            continue
        pdf_dest = None
        for council_dir in (DECISIONS.iterdir() if DECISIONS.exists() else []):
            candidate = council_dir / f"{ref}_decision.pdf"
            if candidate.exists():
                skipped += 1
                break
            pdf_dest = candidate
        if pdf_dest is None or pdf_dest.exists():
            continue
        try:
            response = session.get(url, headers=HEADERS, timeout=60)
            if response.status_code == 200 and response.content.startswith(b"%PDF"):
                pdf_dest.write_bytes(response.content)
                ok += 1
                log(f"OK {ref} ({len(response.content)} bytes)")
            else:
                failed += 1
                log(f"FAIL {ref} http={response.status_code} {url[:120]}")
        except Exception as exc:
            failed += 1
            log(f"ERR {ref} {type(exc).__name__}")
        time.sleep(0.4)
    log(f"DONE ok={ok} failed={failed} skipped={skipped}")


if __name__ == "__main__":
    main()
