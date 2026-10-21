#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_ge10_fixed.csv"
DEFAULT_RESULTS_GLOB = str(ROOT / "02_development" / "current" / "development_review_gpt5_results_part*.csv")
DEFAULT_OUTPUT = ROOT / "02_development" / "current" / "ground_source_extracted_final_wide_ge10_fixed_gpt5_reviewed_partial.csv"

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Append GPT-5 development review columns to the GE10 development CSV.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--results-glob", default=DEFAULT_RESULTS_GLOB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    reviews = load_reviews(args.results_glob)

    with args.input.open("r", encoding="utf-8-sig", newline="") as src:
        reader = csv.DictReader(src)
        fieldnames = list(reader.fieldnames or []) + REVIEW_COLUMNS
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=fieldnames)
            writer.writeheader()
            for row_number, row in enumerate(reader, start=2):
                review = reviews.get(row_number)
                row["gpt5_review"] = compact_review_summary(review)
                row["gpt5_review_status"] = (review or {}).get("status", "")
                row["gpt5_review_confidence"] = (review or {}).get("confidence", "")
                row["gpt5_review_note"] = (review or {}).get("note", "")
                row["gpt5_review_unsupported_fields"] = (review or {}).get("unsupported_fields", "")
                row["gpt5_review_corrected_fields"] = (review or {}).get("corrected_fields", "")
                row["gpt5_review_missing_obvious_fields"] = (review or {}).get("missing_obvious_fields", "")
                row["gpt5_review_api_error"] = (review or {}).get("api_error", "")
                row["gpt5_review_source_file"] = (review or {}).get("_source_file", "")
                writer.writerow(row)

    summary = {
        "input": str(args.input),
        "output": str(args.output),
        "review_rows_loaded": len(reviews),
        "results_glob": args.results_glob,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
