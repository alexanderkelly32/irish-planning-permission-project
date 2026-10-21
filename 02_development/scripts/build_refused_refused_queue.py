#!/usr/bin/env python3
"""Build the refused -> later-refused candidate queue (the counterfactual contrast arm)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from full_revision_linkage import build_full_revision_candidates, build_stratified_review_sample, select_residential_scope

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "old_original_attempt" / "first_attempt_messy" / "irish_planning_dataset_clean_model.parquet"
CURRENT = ROOT / "02_development" / "current"
INPUT_COLUMNS = [
    "PlanningAuthority", "ApplicationNumber", "DevelopmentDescription", "DevelopmentAddress",
    "DevelopmentPostcode", "ITMEasting", "ITMNorthing", "ApplicationType", "Decision",
    "ReceivedDate", "SiteId", "ApplicantForename", "ApplicantSurname", "NumResidentialUnits",
    "OneOffHouse", "LinkAppDetails",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--review-per-tier", type=int, default=100)
    args = parser.parse_args()

    raw = pd.read_parquet(args.input, columns=INPUT_COLUMNS)
    residential = select_residential_scope(raw)
    candidates, diagnostics = build_full_revision_candidates(
        residential, maximum_gap_years=8, spatial_radius_m=50, maximum_group_size=25,
        revised_outcome="REFUSED",
    )
    review = build_stratified_review_sample(candidates, per_tier=args.review_per_tier)
    diagnostics.update({
        "revised_outcome": "REFUSED",
        "review_sample_row_count": int(len(review)),
        "status": "candidate_strength_only_manual_validation_required",
    })
    CURRENT.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(CURRENT / "full_revision_refused_refused_candidates.csv", index=False)
    review.to_csv(CURRENT / "refused_refused_manual_review_sample.csv", index=False)
    (CURRENT / "full_revision_refused_refused_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )
    print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()
