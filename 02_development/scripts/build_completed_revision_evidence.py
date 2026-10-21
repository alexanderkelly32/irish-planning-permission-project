#!/usr/bin/env python3
"""Validate completed manual annotations and export scenario-safe revision evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from revision_evidence_registry import (
    build_revision_intervention_evidence,
    summarize_completed_annotations,
    validate_completed_annotations,
)

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
DEFAULT_INPUT = CURRENT / "revision_evidence_annotation_registry_with_links_fixed.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()

    annotations = pd.read_csv(args.input, low_memory=False)
    validated = validate_completed_annotations(annotations)
    intervention = build_revision_intervention_evidence(validated)
    summary = summarize_completed_annotations(validated)
    summary["annotation_input"] = str(args.input.resolve())

    validated_output = CURRENT / "revision_evidence_annotations_validated.csv"
    intervention_output = CURRENT / "revision_intervention_evidence.csv"
    summary_output = CURRENT / "revision_evidence_annotation_summary.json"
    validated.to_csv(validated_output, index=False)
    intervention.to_csv(intervention_output, index=False)
    summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
