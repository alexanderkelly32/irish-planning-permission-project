#!/usr/bin/env python3
"""Phase 2: council development-plan objective/policy code layer.

Scans extracted plan texts for objective/policy code mentions (e.g. "objective
CS02", "policy HP6") and extracts structured rows: council, plan period,
code, objective text, and any quantitative standards in the clause.

Versioned by (council, plan period) with supersession handled by coverage
years, matching how refusals cite plans ("contrary to the Carlow County
Development Plan 2015-2021, objective 5").

Output: 05_policy/current/objective_code_layer.csv
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = ROOT / "05_policy" / "current"

CODE_PATTERN_LETTERED = re.compile(
    r"\b(?i:objectives?|polic(?:y|ies))\s+([A-Z]{1,3}(?:[- ]?[A-Z]{1,3}){0,3}[- ]?\d{1,3}(?:\.\d{1,3})?[A-Z]?)\b"
)
CODE_PATTERN_SLASH = re.compile(
    r"\b(?i:objectives?|polic(?:y|ies))\s+([A-Z]{1,6}/[A-Z]{1,6})\b"
)
CODE_PATTERN_NUMERIC = re.compile(
    r"\b(?:objectives?|polic(?:y|ies))\s+(?:No\.?\s*)?(\d{1,3}(?:\.\d{1,3})?)\b",
    re.IGNORECASE,
)
CODE_STOPWORDS = {
    "NO", "IN", "ON", "OF", "TO", "AN", "AT", "AND", "THE", "FOR", "OR",
    "IF", "IS", "AS", "BY", "BE", "IT", "WE", "SO", "UP", "DO", "HE",
    "PER", "VIA", "MIN", "MAX", "MM", "KM", "HA",
}
PERIOD_FALLBACK = re.compile(r"(20\d{2})\s*[-–]\s*(20\d{2})")


def scan_plan_texts() -> pd.DataFrame:
    index = pd.read_csv(POLICY_DIR / "policy_documents_index.csv", low_memory=False)
    rows = []
    for _, doc in index.iterrows():
        if str(doc.get("extraction_status")) != "ok":
            continue
        text_path = ROOT / "05_policy" / str(doc.get("extracted_text_path") or "")
        if not text_path.exists():
            continue
        start_year = doc.get("coverage_start_year")
        end_year = doc.get("coverage_end_year")
        if pd.isna(start_year) or pd.isna(end_year):
            label_match = PERIOD_FALLBACK.search(str(doc.get("document_label") or ""))
            if label_match:
                start_year, end_year = int(label_match.group(1)), int(label_match.group(2))
        if pd.isna(start_year) or pd.isna(end_year):
            plan_period = "unknown"
        else:
            plan_period = f"{int(start_year)}-{int(end_year)}"
        text = text_path.read_text(encoding="utf-8", errors="replace")
        matches = []
        for pattern, code_format in ((CODE_PATTERN_LETTERED, "lettered"), (CODE_PATTERN_SLASH, "slash"), (CODE_PATTERN_NUMERIC, "numeric")):
            for match in pattern.finditer(text):
                raw = match.group(1)
                if code_format == "lettered":
                    code = re.sub(r"[\s\-]+", "", raw).upper()
                    if code in CODE_STOPWORDS:
                        continue
                elif code_format == "slash":
                    code = raw.upper()
                    if code in CODE_STOPWORDS:
                        continue
                else:
                    code = raw
                matches.append((match.start(), match.end(), code, code_format))
        matches.sort(key=lambda item: item[0])
        kept = []
        last_end = -1
        for start, end, code, code_format in matches:
            if start < last_end:
                continue
            kept.append((start, end, code, code_format))
            last_end = end
        for start, end, code, code_format in kept:
            ctx_start = max(0, start - 400)
            ctx_end = min(len(text), end + 500)
            context = " ".join(text[ctx_start:ctx_end].split())
            rows.append({
                "council": str(doc.get("authority")),
                "plan_period": plan_period,
                "plan_document": str(doc.get("document_label")),
                "objective_code": code,
                "code_format": code_format,
                "context": context,
            })
    return pd.DataFrame(rows)


def main() -> None:
    mentions = scan_plan_texts()
    print("code mentions:", len(mentions))
    doc_counts = mentions.groupby(["council", "plan_period", "objective_code"])["plan_document"].nunique().rename("mention_docs").reset_index()
    counts = mentions.groupby(["council", "plan_period", "objective_code"]).size().rename("mentions").reset_index()
    counts = counts.merge(doc_counts, on=["council", "plan_period", "objective_code"], how="left")
    counts = counts.sort_values("mentions", ascending=False)
    layer = counts.merge(
        mentions.drop_duplicates(["council", "plan_period", "objective_code"])[
            ["council", "plan_period", "objective_code", "code_format", "plan_document", "context"]
        ],
        on=["council", "plan_period", "objective_code"],
        how="left",
    )
    layer.to_csv(POLICY_DIR / "objective_code_layer.csv", index=False)
    summary = {
        "unique_codes": int(len(layer)),
        "codes_with_known_period": int((layer["plan_period"] != "unknown").sum()),
        "top_codes": layer.head(15)[["council", "plan_period", "objective_code", "mentions"]].to_dict("records"),
        "note": "Scan of the extracted plan texts in policy_documents_index.csv; expand coverage by adding councils' plans to the index (download -> extract) and re-running.",
    }
    (POLICY_DIR / "objective_code_layer_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
