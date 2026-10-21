#!/usr/bin/env python3
"""Build the comparable-retrieval benchmark grading pack."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from find_similar_developments import fit_search_artifacts, transform_rows
from precedent_copilot_logic import normalize_cases
from retrieval_benchmark import build_grading_rows, query_manifest, select_queries

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "retrieval_benchmark_grading_2026-09-04"
DEFAULT_CSV = ROOT / "04_fi" / "current" / "greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv"

QUERY_COUNTS = {
    "10+ units": 40,
    "other residential": 20,
    "extension / alteration": 15,
    "single dwelling": 10,
    "retention": 10,
    "change of use": 5,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--queries", type=int, default=100)
    args = parser.parse_args()

    cases = normalize_cases(pd.read_csv(args.csv, low_memory=False))
    artifacts = fit_search_artifacts(cases)
    case_matrix = transform_rows(cases, artifacts)
    queries = select_queries(cases, QUERY_COUNTS)
    if len(queries) < args.queries:
        raise ValueError(f"only {len(queries)} queries selected; wanted {args.queries}")
    queries = queries.head(args.queries)
    grading_rows, gold_mapping = build_grading_rows(cases, queries, artifacts, case_matrix)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grading_rows.to_csv(OUT_DIR / "grading_rows.csv", index=False)
    query_manifest(queries, gold_mapping).to_csv(OUT_DIR / "query_manifest.csv", index=False)
    (ROOT / "06_copilot" / "current").mkdir(parents=True, exist_ok=True)
    (ROOT / "06_copilot" / "current" / "retrieval_benchmark_gold_mapping.json").write_text(
        json.dumps(gold_mapping, indent=2), encoding="utf-8"
    )
    summary = {
        "query_count": int(len(queries)),
        "grading_row_count": int(len(grading_rows)),
        "queries_by_bucket": queries["query_bucket"].value_counts().to_dict(),
        "gold_rows": len(gold_mapping),
        "grading_file": str(OUT_DIR / "grading_rows.csv"),
        "query_manifest_file": str(OUT_DIR / "query_manifest.csv"),
        "note": "The gold mapping is stored locally in 06_copilot/current and must NOT be included in the emailed pack.",
    }
    (OUT_DIR / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
