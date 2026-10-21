"""Runner: parse TIC pages into estate entries and match to cohort schemes.

Extracts list-like lines (estate name patterns) from the fetched TIC texts,
writes tic_entries.csv, then matches entries to mature cohort schemes by
estate-name tokens (PPR-style). Outputs scheme_tic_labels.csv with
taken_in_charge evidence per scheme.
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

PAGES_DIR = settings.SILVER_DIR / "tic_pages"


def parse_entries(text: str, authority: str) -> list[dict]:
    entries = []
    lines = re.split(r"[\n;•]", text)
    for line in lines:
        line = line.strip()
        if not (8 < len(line) < 160):
            continue
        if not re.search(r"[A-Za-z]", line):
            continue
        # Estate-like: contains a proper-noun pattern such as "Name Estate" or "Estate, Town"
        if re.search(r"^\s*([A-Z][A-Za-z'&.()\- ]{3,60})\s*(?:estate|park|manor|heights|wood|groves|drive|lawn|crescent|close|view|lodge|gardens|walk|court|avenue|green|fields|grange|abbey|hill|vale|rise|dene|glen)\b", line, re.IGNORECASE):
            match = re.search(r"^\s*([A-Z][A-Za-z'&.()\- ]{3,60})", line)
            if not match:
                continue
            name = match.group(1).strip().strip(",-. ")
            entries.append({"authority": authority, "estate_name": name, "raw_line": line[:160]})
    return entries


if __name__ == "__main__":
    records = []
    for text_path in sorted(PAGES_DIR.glob("*_tic.txt")):
        authority = text_path.stem.replace("_tic", "")
        text = text_path.read_text(encoding="utf-8", errors="ignore")
        records.extend(parse_entries(text, authority))
    entries = pd.DataFrame(records).drop_duplicates(subset=["authority", "estate_name"])
    entries.to_csv(PAGES_DIR / "tic_entries.csv", index=False)
    print(f"TIC entries parsed: {len(entries)} across {entries['authority'].nunique()} authorities", flush=True)
    print(entries.groupby("authority").size().sort_values(ascending=False).head(10).to_dict())

    # Match to cohort schemes.
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    mature["addr_tokens"] = mature["DevelopmentAddress"].fillna("").map(address_tokens)
    matches = []
    for _, entry in entries.iterrows():
        tokens = address_tokens(entry["estate_name"])
        if len(tokens) < 1:
            continue
        for _, scheme in mature.iterrows():
            overlap = tokens & set(scheme["addr_tokens"])
            if len(overlap) >= max(1, min(2, len(tokens))):
                matches.append({
                    "scheme_id": str(scheme["case_key"]),
                    "authority": entry["authority"],
                    "tic_estate_name": entry["estate_name"],
                    "scheme_address": str(scheme["DevelopmentAddress"])[:80],
                    "token_overlap": len(overlap),
                    "source_line": entry["raw_line"],
                })
    matched = pd.DataFrame(matches).drop_duplicates(subset=["scheme_id", "tic_estate_name"])
    matched.to_csv(settings.SILVER_DIR / "scheme_tic_matches.csv", index=False)
    summary = {
        "tic_entries": int(len(entries)),
        "matched_schemes": int(matched["scheme_id"].nunique()) if len(matched) else 0,
        "match_rows": int(len(matched)),
        "note": "candidate matches only; estate-name tokens, requires verification before use as labels",
    }
    (PAGES_DIR / "match_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
