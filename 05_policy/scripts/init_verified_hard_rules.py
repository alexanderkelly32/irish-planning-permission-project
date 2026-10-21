#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = ROOT / "05_policy"
CURRENT_DIR = POLICY_ROOT / "current"
SOURCE_DIR = POLICY_ROOT / "source_data"


REVIEW_COLUMNS = [
    "review_status",
    "review_priority",
    "reviewer",
    "reviewed_at",
    "review_notes",
    "verification_method",
    "verbatim_quote",
    "quote_char_count",
    "llm_candidate_flag",
    "extraction_method",
]


def build_review_queue() -> pd.DataFrame:
    registry_path = CURRENT_DIR / "hard_policy_rules_registry.csv"
    if not registry_path.exists():
        raise FileNotFoundError(f"Missing extracted hard-rule registry: {registry_path}")
    registry = pd.read_csv(registry_path)
    if registry.empty:
        raise ValueError("Extracted hard-rule registry is empty.")

    review_df = registry.copy()
    review_df["review_status"] = "pending"
    review_df["review_priority"] = review_df["rule_family"].map(
        {
            "apartment_min_floor_area": "high",
            "communal_amenity_min_per_unit": "high",
            "private_amenity_min_depth": "medium",
        }
    ).fillna("medium")
    review_df["reviewer"] = ""
    review_df["reviewed_at"] = ""
    review_df["review_notes"] = ""
    review_df["verification_method"] = ""
    review_df["verbatim_quote"] = ""
    review_df["quote_char_count"] = 0
    review_df["llm_candidate_flag"] = 0
    review_df["extraction_method"] = "rule_based_seed"

    ordered_cols = [
        "plan_key",
        "authority",
        "plan_start_year",
        "plan_end_year",
        "rule_family",
        "subject_type",
        "threshold_kind",
        "threshold_value",
        "threshold_unit",
        "scope_note",
        "source_document_label",
        "source_page_range",
        "source_section_title",
        "source_chunk_id",
        "source_excerpt",
        "candidate_threshold_values",
        "candidate_value_counts",
        "source_rule_count",
        "source_chunk_count",
        *REVIEW_COLUMNS,
    ]
    for col in ordered_cols:
        if col not in review_df.columns:
            review_df[col] = ""
    return review_df[ordered_cols].sort_values(
        ["review_priority", "authority", "plan_start_year", "rule_family", "subject_type"],
        ascending=[True, True, True, True, True],
    )


def build_empty_verified_template(review_df: pd.DataFrame) -> pd.DataFrame:
    template = review_df.iloc[0:0].copy()
    return template


def main() -> None:
    review_df = build_review_queue()
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    review_df.to_csv(CURRENT_DIR / "hard_rule_review_queue.csv", index=False)
    apartment_review_df = review_df[review_df["rule_family"] == "apartment_min_floor_area"].copy()
    apartment_review_df.to_csv(CURRENT_DIR / "hard_rule_review_queue_apartment.csv", index=False)
    build_empty_verified_template(review_df).to_csv(SOURCE_DIR / "verified_hard_policy_rules_template.csv", index=False)


if __name__ == "__main__":
    main()
