#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_ge10_fixed.csv"
DEFAULT_RESULTS_GLOB = str(ROOT / "02_development" / "current" / "development_review_gpt5_results_part*.csv")
DEFAULT_OUTPUT = ROOT / "02_development" / "current" / "ground_source_extracted_final_wide_ge10_fixed_gpt5_replaced_partial.csv"

REVIEW_COLUMNS = [
    "gpt5_review",
    "gpt5_review_status",
    "gpt5_review_confidence",
    "gpt5_review_note",
    "gpt5_review_unsupported_fields",
    "gpt5_review_corrected_fields",
    "gpt5_review_missing_obvious_fields",
    "gpt5_review_api_error",
    "gpt5_review_source_file",
    "gpt5_review_applied",
    "gpt5_review_changed_fields",
]


def load_reviews(pattern: str) -> Dict[int, Dict[str, str]]:
    reviews: Dict[int, Dict[str, str]] = {}
    for path_str in sorted(glob.glob(pattern)):
        path = Path(path_str)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_number_raw = (row.get("row_number") or "").strip()
                if not row_number_raw:
                    continue
                try:
                    row_number = int(row_number_raw)
                except ValueError:
                    continue
                row["_source_file"] = path.name
                reviews[row_number] = row
    return reviews


def parse_json_array(raw: str) -> list:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def compact_review_summary(review: Dict[str, str] | None) -> str:
    if not review:
        return ""
    status = (review.get("status") or "").strip()
    confidence = (review.get("confidence") or "").strip()
    note = (review.get("note") or "").strip()
    api_error = (review.get("api_error") or "").strip()
    if api_error:
        return f"gpt5 review error: {api_error}"
    parts: List[str] = ["gpt5"]
    if status:
        parts.append(status)
    if confidence:
        parts.append(confidence)
    summary = " | ".join(parts)
    if note:
        summary = f"{summary} | {note}"
    return summary


def normalize_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else format(value, "g")
    return str(value)


def apply_review_to_row(row: Dict[str, str], review: Dict[str, str] | None) -> Tuple[Dict[str, str], List[str], bool]:
    changed_fields: List[str] = []
    applied = False
    if not review:
        return row, changed_fields, applied
    if (review.get("api_error") or "").strip():
        return row, changed_fields, applied

    unsupported_fields = parse_json_array(review.get("unsupported_fields", ""))
    corrected_fields = parse_json_array(review.get("corrected_fields", ""))
    missing_fields = parse_json_array(review.get("missing_obvious_fields", ""))

    for field in unsupported_fields:
        if not isinstance(field, str) or field not in row:
            continue
        if row.get(field, "") != "":
            row[field] = ""
            changed_fields.append(field)
            applied = True

    for item in corrected_fields + missing_fields:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        if not isinstance(field, str) or field not in row:
            continue
        new_value = normalize_value(item.get("value"))
        if row.get(field, "") != new_value:
            row[field] = new_value
            changed_fields.append(field)
            applied = True

    return row, sorted(set(changed_fields)), applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply GPT-5 review outputs as replacements into a new GE10 development CSV.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--results-glob", default=DEFAULT_RESULTS_GLOB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    reviews = load_reviews(args.results_glob)

    with args.input.open("r", encoding="utf-8-sig", newline="") as src:
        reader = csv.DictReader(src)
        fieldnames = list(reader.fieldnames or []) + REVIEW_COLUMNS
        args.output.parent.mkdir(parents=True, exist_ok=True)
        applied_rows = 0
        changed_cells = 0
        with args.output.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=fieldnames)
            writer.writeheader()
            for row_number, row in enumerate(reader, start=2):
                review = reviews.get(row_number)
                row, changed_fields, applied = apply_review_to_row(row, review)
                if applied:
                    applied_rows += 1
                    changed_cells += len(changed_fields)
                row["gpt5_review"] = compact_review_summary(review)
                row["gpt5_review_status"] = (review or {}).get("status", "")
                row["gpt5_review_confidence"] = (review or {}).get("confidence", "")
                row["gpt5_review_note"] = (review or {}).get("note", "")
                row["gpt5_review_unsupported_fields"] = (review or {}).get("unsupported_fields", "")
                row["gpt5_review_corrected_fields"] = (review or {}).get("corrected_fields", "")
                row["gpt5_review_missing_obvious_fields"] = (review or {}).get("missing_obvious_fields", "")
                row["gpt5_review_api_error"] = (review or {}).get("api_error", "")
                row["gpt5_review_source_file"] = (review or {}).get("_source_file", "")
                row["gpt5_review_applied"] = "1" if applied else ""
                row["gpt5_review_changed_fields"] = json.dumps(changed_fields, ensure_ascii=True) if changed_fields else ""
                writer.writerow(row)

    summary = {
        "input": str(args.input),
        "output": str(args.output),
        "review_rows_loaded": len(reviews),
        "applied_rows": applied_rows,
        "changed_cells": changed_cells,
        "results_glob": args.results_glob,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
