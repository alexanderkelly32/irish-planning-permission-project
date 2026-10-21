#!/usr/bin/env python3
"""Generate an auditable, non-model revision-pair candidate table."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from revision_pairs import build_revision_pairs

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "04_fi" / "current" / "greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv"
DEFAULT_OUTPUT = ROOT / "02_development" / "current" / "project_revision_pairs.csv"
DEFAULT_AUDIT = ROOT / "02_development" / "current" / "project_revision_pair_audit.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()
    pairs = build_revision_pairs(pd.read_csv(args.input, low_memory=False))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(args.output, index=False)
    audit_columns = ["original_case_key", "revised_case_key", "match_method", "confidence_same_project", "description_similarity", "units_delta", "storeys_delta", "normalized_address", "original_description", "revised_description", "original_source_url", "revised_source_url"]
    pairs.reindex(columns=audit_columns).assign(audit_status="pending", audit_notes="").to_csv(args.audit_output, index=False)
    print({"pairs": len(pairs), "output": str(args.output), "audit_output": str(args.audit_output)})


if __name__ == "__main__":
    main()
