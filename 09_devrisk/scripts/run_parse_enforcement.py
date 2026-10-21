"""Runner: parse enforcement pages into notice entries and match to schemes.

Extracts lines that look like notice entries (address + optional date) from
the harvested enforcement pages, writes enforcement_entries.csv, and matches
to cohort schemes by address tokens.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.scoring import address_tokens  # noqa: E402

PAGES_DIR = settings.SILVER_DIR / "enforcement_pages"

DATE_RE = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b")


def parse_entries(text: str, authority: str) -> list[dict]:
    entries = []
    for line in re.split(r"[\n;]", text):
        line = line.strip()
        if not (10 < len(line) < 200):
            continue
        if not re.search(r"\d", line):
            continue
        date = DATE_RE.search(line)
        has_address = re.search(r"\b(road|street|avenue|estate|park|manor|close|drive|lane|townland|co\.?\s?[a-z]+)\b", line, re.IGNORECASE)
        if date or has_address:
            entries.append({
                "authority": authority,
                "entry": line[:180],
                "date": date.group(1) if date else None,
                "has_address": bool(has_address),
            })
    return entries


if __name__ == "__main__":
    records = []
    for text_path in sorted(PAGES_DIR.glob("*_enforcement.txt")):
        authority = text_path.stem.replace("_enforcement", "")
        text = text_path.read_text(encoding="utf-8", errors="ignore")
        records.extend(parse_entries(text, authority))
    entries = pd.DataFrame(records)
    entries.to_csv(PAGES_DIR / "enforcement_entries.csv", index=False)

    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    mature["addr_tokens"] = mature["DevelopmentAddress"].fillna("").map(address_tokens)
    matches = []
    for _, entry in entries.iterrows():
        tokens = address_tokens(entry["entry"])
        if len(tokens) < 2:
            continue
        for _, scheme in mature.iterrows():
            overlap = tokens & set(scheme["addr_tokens"])
            if len(overlap) >= 2:
                matches.append({
                    "scheme_id": str(scheme["case_key"]),
                    "authority": entry["authority"],
                    "enforcement_entry": entry["entry"][:140],
                    "entry_date": entry["date"],
                    "token_overlap": len(overlap),
                })
    matched = pd.DataFrame(matches).drop_duplicates(subset=["scheme_id", "enforcement_entry"])
    matched.to_csv(settings.SILVER_DIR / "scheme_enforcement_matches.csv", index=False)

    summary = {
        "entries_parsed": int(len(entries)),
        "authorities_with_entries": int(entries["authority"].nunique()) if len(entries) else 0,
        "matched_schemes": int(matched["scheme_id"].nunique()) if len(matched) else 0,
        "note": "candidate matches only; page text is noisy, verify before use",
    }
    (PAGES_DIR / "parse_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
