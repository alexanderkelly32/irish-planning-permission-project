#!/usr/bin/env python3
"""Build the manual evidence-annotation registry and an observed-delta summary."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from revision_evidence_registry import build_revision_evidence_registry, summarize_observed_deltas

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"


def main() -> None:
    accepted = pd.read_csv(CURRENT / "accepted_revision_pairs.csv")
    registry = build_revision_evidence_registry(accepted)
    output_path = CURRENT / "revision_evidence_annotation_registry.csv"
    try:
        registry.to_csv(output_path, index=False)
    except PermissionError:
        output_path = CURRENT / "revision_evidence_annotation_registry_with_links.csv"
        registry.to_csv(output_path, index=False)
    summary = {
        "accepted_pair_count": int(len(registry)),
        "pairs_with_refusal_reason_text": int(registry["refusal_reason_available"].sum()),
        "observed_numeric_deltas": summarize_observed_deltas(registry),
        "status": "manual_annotation_required_before_intervention_recommendations",
        "registry_output": str(output_path),
    }
    (CURRENT / "revision_evidence_coverage.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
