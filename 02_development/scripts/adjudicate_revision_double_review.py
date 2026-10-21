#!/usr/bin/env python3
"""Adjudicate the completed double review against the original pilot labels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from double_review import merge_double_review, summarize_double_review

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
DEFAULT_PILOT = CURRENT / "full_revision_manual_review_pilot_fixed.csv"
DEFAULT_REVIEWER_B = CURRENT / "full_revision_double_review_slice_fixed.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--reviewer-b", type=Path, default=DEFAULT_REVIEWER_B)
    args = parser.parse_args()

    pilot = pd.read_csv(args.pilot, low_memory=False)
    reviewer_b = pd.read_csv(args.reviewer_b, low_memory=False)
    adjudication = merge_double_review(pilot, reviewer_b)
    summary = summarize_double_review(adjudication)
    summary["source_pilot"] = str(args.pilot.resolve())
    summary["source_reviewer_b"] = str(args.reviewer_b.resolve())

    CURRENT.mkdir(parents=True, exist_ok=True)
    adjudication.to_csv(CURRENT / "full_revision_double_review_adjudication.csv", index=False)
    (CURRENT / "full_revision_double_review_agreement_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
