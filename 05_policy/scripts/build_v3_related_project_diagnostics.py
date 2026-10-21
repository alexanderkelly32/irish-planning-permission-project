#!/usr/bin/env python3
"""Audit frozen Model v3's 2025 holdout for authority-scoped related-site overlap."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
OUTPUT_DIR = ROOT / "05_policy" / "current"
sys.path.insert(0, str(SCRIPT_DIR))

from build_national_residential_model_v2 import TRAIN_CUTOFF, load_data_with_history  # noqa: E402
from related_project_validation import (  # noqa: E402
    binary_score_metrics,
    build_related_project_group,
    group_kfold_summary,
    split_temporal_related_project_scores,
)

PREDICTIONS_PATH = OUTPUT_DIR / "raw_planning_v3_2025_predictions.csv"
OUTPUT_JSON = OUTPUT_DIR / "raw_planning_v3_related_project_diagnostics.json"
OUTPUT_CSV = OUTPUT_DIR / "raw_planning_v3_2025_predictions_related_project.csv"
ACCEPTED_GROUP_MAP = ROOT / "02_development" / "current" / "accepted_revision_pair_group_map.csv"


def _normal_case_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def load_accepted_revision_groups(data: pd.DataFrame) -> dict[str, str]:
    """Map manually accepted source keys to the model's canonical case keys."""
    if not ACCEPTED_GROUP_MAP.exists():
        return {}
    source_groups = pd.read_csv(ACCEPTED_GROUP_MAP)
    source_groups["normalized_key"] = source_groups["case_key"].map(_normal_case_key)
    model_cases = data[["case_key"]].drop_duplicates().copy()
    model_cases["normalized_key"] = model_cases["case_key"].map(_normal_case_key)
    merged = source_groups.merge(model_cases, on="normalized_key", how="left", validate="one_to_one")
    matched = merged.dropna(subset=["case_key_y"])
    return dict(zip(matched["case_key_y"].astype(str), matched["project_group_id"].astype(str), strict=False))


def main() -> None:
    if not PREDICTIONS_PATH.exists():
        raise FileNotFoundError(f"Expected frozen v3 predictions: {PREDICTIONS_PATH}")
    data = load_data_with_history()
    explicit_groups = load_accepted_revision_groups(data)
    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    holdout_metadata = data[data["received_date_dt"] >= TRAIN_CUTOFF][
        ["case_key", "PlanningAuthority", "SiteId", "target_refused", "received_date_dt"]
    ].copy()
    predictions = pd.read_csv(PREDICTIONS_PATH)
    scored = holdout_metadata.merge(
        predictions,
        on="case_key",
        how="inner",
        suffixes=("", "_prediction"),
        validate="one_to_one",
    )
    if len(scored) != len(predictions):
        raise ValueError("v3 prediction rows did not match the eligible temporal holdout one-to-one")
    if not (scored["target_refused"] == scored["target_refused_prediction"]).all():
        raise ValueError("v3 prediction target differs from the reconstructed holdout target")

    split = split_temporal_related_project_scores(train, scored, explicit_group_by_case=explicit_groups)
    audited = split["scored"]
    site_id_present = train["SiteId"].fillna("").astype(str).str.strip().ne("")
    grouped_train = train.loc[site_id_present].copy()
    grouped_train["related_project_group"] = build_related_project_group(grouped_train)
    repeated_site_groups = grouped_train["related_project_group"].duplicated(keep=False)
    grouped_train = grouped_train.loc[repeated_site_groups].copy()
    topology_groups = grouped_train["related_project_group"].drop_duplicates().sort_values().head(2_000)
    topology_sample = grouped_train[grouped_train["related_project_group"].isin(topology_groups)].copy()
    accepted_train = train[train["case_key"].astype(str).isin(explicit_groups)].copy()
    results: dict[str, object] = {
        "model_version": "national_residential_v3_comparables",
        "status": "supplemental_related_project_temporal_diagnostic_not_a_group_retrained_model_evaluation",
        "definition": (
            "Authority-scoped SiteId identifies a related project. Missing SiteIds become singleton "
            "case groups, so this diagnostic does not infer site relationships from address text."
        ),
        "train_cutoff_exclusive": str(TRAIN_CUTOFF),
        "train_rows": int(len(train)),
        "train_rows_in_repeated_site_groups": int(len(grouped_train)),
        "group_kfold_topology_sample_rows": int(len(topology_sample)),
        "accepted_revision_group_train_rows": int(len(accepted_train)),
        "holdout_rows": int(len(audited)),
        "accepted_revision_group_members_mapped_to_model_data": int(len(explicit_groups)),
        "holdout_group_status_counts": split["group_status_counts"],
        "frozen_train_group_kfold_topology": group_kfold_summary(topology_sample),
        "accepted_revision_group_kfold_topology": group_kfold_summary(
            accepted_train, explicit_group_by_case=explicit_groups
        ),
        "metrics": {},
        "limitations": [
            "This measures frozen temporal holdout performance separately for known related sites and unseen sites.",
            "It does not claim every resubmission has a usable SiteId and does not replace a full grouped retraining experiment for a new candidate.",
            "No post-submission fields are used as predictor inputs; final outcomes are evaluation labels only.",
        ],
    }
    for score_column in ["v3_ranking_score", "v3_platt_risk"]:
        results["metrics"][score_column] = {
            "overall": binary_score_metrics(audited["target_refused"], audited[score_column]),
            "seen_before": binary_score_metrics(
                audited.loc[audited["seen_before"], "target_refused"],
                audited.loc[audited["seen_before"], score_column],
            ),
            "unseen": binary_score_metrics(
                audited.loc[~audited["seen_before"], "target_refused"],
                audited.loc[~audited["seen_before"], score_column],
            ),
        }
    audited.to_csv(OUTPUT_CSV, index=False)
    OUTPUT_JSON.write_text(json.dumps(results, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(results, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
