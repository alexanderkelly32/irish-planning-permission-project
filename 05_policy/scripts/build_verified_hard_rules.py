#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = ROOT / "05_policy"
CURRENT_DIR = POLICY_ROOT / "current"
SOURCE_DIR = POLICY_ROOT / "source_data"


def load_hard_rules_module():
    path = POLICY_ROOT / "scripts" / "build_dublin_hard_rules.py"
    spec = importlib.util.spec_from_file_location("hard_rules", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_verified_rules() -> pd.DataFrame:
    verified_path = SOURCE_DIR / "verified_hard_policy_rules.csv"
    review_queue_path = CURRENT_DIR / "hard_rule_review_queue.csv"
    if verified_path.exists():
        df = pd.read_csv(verified_path)
    elif review_queue_path.exists():
        df = pd.read_csv(review_queue_path)
    else:
        raise FileNotFoundError("No verified rules file or review queue found.")

    if "review_status" not in df.columns:
        raise ValueError("Verified rules file must include a review_status column.")

    approved = df[df["review_status"].astype(str).str.lower() == "approved"].copy()
    return approved.reset_index(drop=True)


def build_summary(approved: pd.DataFrame, features_df: pd.DataFrame, matches_df: pd.DataFrame) -> dict[str, object]:
    return {
        "approved_rules": int(len(approved)),
        "approved_rules_by_family": approved["rule_family"].value_counts().to_dict(),
        "cases_scored": int(len(features_df)),
        "cases_with_any_verified_hard_match": int(features_df["hard_rule_apartment_sizes_parsed"].fillna(0).gt(0).sum()),
        "cases_with_any_verified_breach": int(features_df["hard_rule_apartment_size_breach_any"].fillna(0).sum()),
        "cases_with_verified_communal_amenity_rules_available": int(pd.to_numeric(features_df.get("hard_rule_communal_amenity_rules_available"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_verified_parking_rules_available": int(pd.to_numeric(features_df.get("hard_rule_parking_rules_available"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_verified_parking_compare_possible": int(pd.to_numeric(features_df.get("hard_rule_parking_compare_possible"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_verified_parking_breach_any": int(pd.to_numeric(features_df.get("hard_rule_parking_breach_any"), errors="coerce").fillna(0).sum()),
        "cases_with_verified_open_space_rules_available": int(pd.to_numeric(features_df.get("hard_rule_open_space_rules_available"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_verified_open_space_compare_possible": int(pd.to_numeric(features_df.get("hard_rule_open_space_compare_possible"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_verified_open_space_breach_any": int(pd.to_numeric(features_df.get("hard_rule_open_space_breach_any"), errors="coerce").fillna(0).sum()),
        "verified_rule_matches": int(len(matches_df)),
    }


def main() -> None:
    hard_module = load_hard_rules_module()
    policy_module = hard_module.load_policy_module()
    approved = load_verified_rules()

    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    approved.to_csv(CURRENT_DIR / "verified_hard_policy_rules.csv", index=False)

    if approved.empty:
        features = policy_module.load_dublin_cases()[["case_key", "PlanningAuthority", "ApplicationNumber"]].copy()
        features["policy_plan_key"] = ""
        features["policy_coverage_flag"] = ""
        features["units_apartments_best"] = pd.NA
        features["hard_rule_apartment_size_rules_available"] = 0
        features["hard_rule_apartment_sizes_parsed"] = 0
        features["hard_rule_apartment_size_breach_count"] = 0
        features["hard_rule_apartment_size_breach_any"] = 0
        features["hard_rule_apartment_size_worst_margin_sqm"] = pd.NA
        features["hard_rule_apartment_size_parseable_case"] = 0
        features["hard_rule_apartment_size_subjects_found"] = ""
        features["hard_rule_communal_amenity_rules_available"] = 0
        features["hard_rule_communal_amenity_subjects_available"] = ""
        features["hard_rule_parking_rules_available"] = 0
        features["hard_rule_parking_compare_possible"] = 0
        features["hard_rule_parking_required_spaces_min"] = pd.NA
        features["hard_rule_parking_spaces_provided"] = pd.NA
        features["hard_rule_parking_margin_spaces"] = pd.NA
        features["hard_rule_parking_breach_any"] = 0
        features["hard_rule_parking_rule_basis"] = ""
        features["hard_rule_open_space_rules_available"] = 0
        features["hard_rule_open_space_compare_possible"] = 0
        features["hard_rule_open_space_required_sqm_min"] = pd.NA
        features["hard_rule_open_space_sqm_provided"] = pd.NA
        features["hard_rule_open_space_margin_sqm"] = pd.NA
        features["hard_rule_open_space_breach_any"] = 0
        features["hard_rule_open_space_rule_basis"] = ""
        matches = pd.DataFrame()
    else:
        features, matches = hard_module.build_case_hard_rule_features(policy_module, approved)

    features.to_csv(CURRENT_DIR / "dublin_case_verified_hard_rule_features.csv", index=False)
    matches.to_csv(CURRENT_DIR / "dublin_case_verified_hard_rule_matches.csv", index=False)
    summary = build_summary(approved, features, matches)
    (CURRENT_DIR / "verified_hard_rule_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
