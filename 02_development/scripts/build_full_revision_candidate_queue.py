#!/usr/bin/env python3
"""Build a national residential revision-linkage queue and first audit batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from accepted_revision_pairs import read_revision_audit_csv
from full_revision_linkage import (
    apply_known_audit_labels,
    audit_labels_from_review,
    build_full_revision_candidates,
    build_stratified_review_sample,
    evaluate_known_pair_recall,
    select_residential_scope,
)

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
    parser.add_argument("--maximum-gap-years", type=float, default=8)
    parser.add_argument("--spatial-radius-m", type=float, default=50)
    parser.add_argument("--maximum-group-size", type=int, default=25)
    parser.add_argument("--review-per-tier", type=int, default=100)
    args = parser.parse_args()

    raw = pd.read_parquet(args.input, columns=INPUT_COLUMNS)
    residential = select_residential_scope(raw)
    candidates, diagnostics = build_full_revision_candidates(
        residential,
        maximum_gap_years=args.maximum_gap_years,
        spatial_radius_m=args.spatial_radius_m,
        maximum_group_size=args.maximum_group_size,
    )
    audits: list[pd.DataFrame] = []
    audit_path = CURRENT / "project_revision_pair_audit.csv"
    if audit_path.exists():
        audits.append(read_revision_audit_csv(audit_path))
    completed_pilot_path = CURRENT / "full_revision_manual_review_pilot_fixed.csv"
    if completed_pilot_path.exists():
        audits.append(audit_labels_from_review(pd.read_csv(completed_pilot_path, low_memory=False)))
    completed_sample_path = CURRENT / "full_revision_manual_review_sample_fixed.csv"
    if completed_sample_path.exists():
        audits.append(audit_labels_from_review(pd.read_csv(completed_sample_path, low_memory=False)))
    high_tier_path = CURRENT / "full_revision_manual_review_high_tier_fixed.csv"
    if high_tier_path.exists():
        audits.append(audit_labels_from_review(pd.read_csv(high_tier_path, low_memory=False)))
    high_tier_2_path = CURRENT / "full_revision_manual_review_high_tier_2_fixed.csv"
    if high_tier_2_path.exists():
        audits.append(audit_labels_from_review(pd.read_csv(high_tier_2_path, low_memory=False)))
    high_tier_3_path = CURRENT / "full_revision_manual_review_high_tier_3_fixed.csv"
    if high_tier_3_path.exists():
        audits.append(audit_labels_from_review(pd.read_csv(high_tier_3_path, low_memory=False)))
    medium_path = CURRENT / "full_revision_manual_review_medium_fixed.csv"
    if medium_path.exists():
        audits.append(audit_labels_from_review(pd.read_csv(medium_path, low_memory=False)))
    if audits:
        candidates = apply_known_audit_labels(candidates, pd.concat(audits, ignore_index=True))
    review = build_stratified_review_sample(candidates, per_tier=args.review_per_tier)
    pilot = build_stratified_review_sample(candidates, per_tier=min(30, args.review_per_tier))
    accepted_path = CURRENT / "accepted_revision_pairs.csv"
    known_pair_recall = (
        evaluate_known_pair_recall(candidates, pd.read_csv(accepted_path, low_memory=False))
        if accepted_path.exists() else None
    )
    diagnostics.update({
        "source": str(args.input.resolve()),
        "raw_row_count": int(len(raw)),
        "residential_scope_row_count": int(len(residential)),
        "review_sample_row_count": int(len(review)),
        "review_pilot_row_count": int(len(pilot)),
        "carried_forward_audit_status_counts": {
            key: int(value)
            for key, value in candidates["manual_review_status"].value_counts().to_dict().items()
            if key != "pending"
        },
        "completed_review_sources": [str(path.name) for path in [audit_path, completed_pilot_path, completed_sample_path, high_tier_path, high_tier_2_path, high_tier_3_path, medium_path] if path.exists()],
        "known_accepted_pair_recall": known_pair_recall,
        "configuration": {
            "maximum_gap_years": args.maximum_gap_years,
            "spatial_radius_m": args.spatial_radius_m,
            "maximum_group_size": args.maximum_group_size,
            "review_per_tier": args.review_per_tier,
        },
        "status": "candidate_strength_only_manual_validation_required",
    })

    CURRENT.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(CURRENT / "full_revision_candidate_queue.csv", index=False)
    review.to_csv(CURRENT / "full_revision_manual_review_sample.csv", index=False)
    pilot.to_csv(CURRENT / "full_revision_manual_review_pilot.csv", index=False)
    (CURRENT / "full_revision_linkage_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )
    print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()
