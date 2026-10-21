#!/usr/bin/env python3
"""Build canonical Scheme records and deltas from the audited revision pairs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from canonical_revision_schemes import (
    build_canonical_records,
    build_delta_rows,
    load_accepted_pairs,
    summarize_records,
)

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
DEFAULT_QUEUE = CURRENT / "full_revision_candidate_queue.csv"
DEFAULT_STRUCTURED = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_ge10_fixed.csv"
DEFAULT_REFUSAL = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
DEFAULT_ANNOTATIONS = CURRENT / "revision_evidence_annotation_registry_with_links_fixed.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--structured", type=Path, default=DEFAULT_STRUCTURED)
    parser.add_argument("--refusal-master", type=Path, default=DEFAULT_REFUSAL)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--pair-extractions", type=Path, default=None, help="two-sided description extraction CSV (deltas for pairs the structured source missed)")
    parser.add_argument("--pair-report-extractions", type=Path, default=None, help="two-sided planner-report extraction CSV (report-sourced deltas, preferred over descriptions)")
    args = parser.parse_args()

    queue = pd.read_csv(args.queue, low_memory=False)
    accepted = load_accepted_pairs(queue)
    structured = pd.read_csv(args.structured, low_memory=False)
    refusal_master = pd.read_csv(args.refusal_master, low_memory=False) if args.refusal_master.exists() else None
    annotations = pd.read_csv(args.annotations, low_memory=False) if args.annotations.exists() else None
    pair_extractions_path = args.pair_extractions
    if pair_extractions_path is None:
        default_pairs = CURRENT / "revision_pair_extraction_2026-09-13" / "revision_pair_structured_extractions.csv"
        pair_extractions_path = default_pairs if default_pairs.exists() else None
    pair_extractions = pd.read_csv(pair_extractions_path, low_memory=False) if pair_extractions_path else None
    report_extractions_path = args.pair_report_extractions
    if report_extractions_path is None:
        default_reports = CURRENT / "revision_pair_report_extraction_2026-09-13" / "revision_pair_report_extractions.csv"
        report_extractions_path = default_reports if default_reports.exists() else None
    report_extractions = pd.read_csv(report_extractions_path, low_memory=False) if report_extractions_path else None
    if report_extractions is not None and not report_extractions.empty:
        combined = report_extractions if pair_extractions is None else pd.concat(
            [report_extractions, pair_extractions], ignore_index=True,
        )
        pair_extractions = combined.drop_duplicates(
            subset=["original_case_key", "revised_case_key"], keep="first",
        )

    records = build_canonical_records(accepted, structured, refusal_master, annotations, pair_extractions)
    deltas = build_delta_rows(records)
    summary = summarize_records(records)
    summary["source_queue"] = str(args.queue.resolve())
    summary["source_structured"] = str(args.structured.resolve())

    CURRENT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(CURRENT / "canonical_revision_scheme_records.csv", index=False)
    deltas.to_csv(CURRENT / "canonical_revision_scheme_deltas.csv", index=False)
    (CURRENT / "canonical_revision_scheme_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
