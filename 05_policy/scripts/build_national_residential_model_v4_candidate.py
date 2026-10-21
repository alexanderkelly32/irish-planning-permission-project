#!/usr/bin/env python3
"""Evaluate a text-plus-structured successor candidate without replacing Model v3."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import GroupKFold

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
OUTPUT_DIR = ROOT / "05_policy" / "current"
sys.path.insert(0, str(SCRIPT_DIR))

from build_comparable_feature_experiment import COMPARABLE_FEATURES_PATH, V3_NUMERIC, metrics  # noqa: E402
from build_national_residential_model_v2 import CALIBRATION_START, TRAIN_CUTOFF, apply_platt, build_scaled_pipeline, load_data_with_history, platt_calibrate  # noqa: E402
from build_prospective_calibration_backtest import score_metrics  # noqa: E402
from related_project_validation import build_related_project_group  # noqa: E402
from structured_feature_utils import STRUCTURED_NUMERIC, add_structured_scheme_features  # noqa: E402

V4_NUMERIC = V3_NUMERIC + STRUCTURED_NUMERIC
V4_FEATURES = ["PlanningAuthority", "application_bucket", "description_stripped"] + V4_NUMERIC
ACCEPTED_GROUP_MAP = ROOT / "02_development" / "current" / "accepted_revision_pair_group_map.csv"


def _normal_case_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def load_accepted_revision_groups(data: pd.DataFrame) -> dict[str, str]:
    if not ACCEPTED_GROUP_MAP.exists():
        return {}
    source = pd.read_csv(ACCEPTED_GROUP_MAP)
    source["normalized_key"] = source["case_key"].map(_normal_case_key)
    model = data[["case_key"]].drop_duplicates().copy()
    model["normalized_key"] = model["case_key"].map(_normal_case_key)
    matched = source.merge(model, on="normalized_key", how="inner", validate="one_to_one")
    return dict(zip(matched["case_key_y"].astype(str), matched["project_group_id"].astype(str), strict=False))


def fit_predict(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    model = build_scaled_pipeline(V4_NUMERIC)
    # SGDClassifier log_loss is the documented probabilistic linear-loss mode.
    # Source: https://scikit-learn.org/1.6/modules/generated/sklearn.linear_model.SGDClassifier.html
    model.set_params(
        model=SGDClassifier(
            loss="log_loss",
            alpha=0.0001,
            max_iter=100,
            tol=1e-3,
            class_weight="balanced",
            random_state=42,
            average=True,
        )
    )
    model.fit(train[V4_FEATURES], train["target_refused"])
    return model.predict_proba(test[V4_FEATURES])[:, 1]


def grouped_oof_predictions(train: pd.DataFrame, groups: pd.Series) -> tuple[np.ndarray, list[dict[str, int]]]:
    """Five non-overlapping GroupKFold OOF scores; grouping is evaluation metadata only.

    Source: https://scikit-learn.org/1.6/modules/generated/sklearn.model_selection.GroupKFold.html
    """
    predicted = np.full(len(train), np.nan)
    splitter = GroupKFold(n_splits=5, shuffle=True, random_state=42)
    folds: list[dict[str, int]] = []
    for fold, (fit_idx, test_idx) in enumerate(splitter.split(train, groups=groups)):
        fit_groups = set(groups.iloc[fit_idx])
        test_groups = set(groups.iloc[test_idx])
        if fit_groups & test_groups:
            raise AssertionError("related project leaked across grouped validation fold")
        predicted[test_idx] = fit_predict(train.iloc[fit_idx], train.iloc[test_idx])
        folds.append({"fold": fold, "train_rows": int(len(fit_idx)), "test_rows": int(len(test_idx)), "test_groups": int(len(test_groups))})
    if np.isnan(predicted).any():
        raise AssertionError("missing grouped out-of-fold predictions")
    return predicted, folds


def main() -> None:
    comparable = pd.read_parquet(COMPARABLE_FEATURES_PATH)
    data = load_data_with_history().merge(comparable, on="case_key", how="left", validate="one_to_one")
    data = add_structured_scheme_features(data)
    data[V4_NUMERIC] = data[V4_NUMERIC].replace([np.inf, -np.inf], np.nan)
    train = data[data["received_date_dt"] < TRAIN_CUTOFF].reset_index(drop=True)
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].reset_index(drop=True)

    ranking = fit_predict(train, test)
    calibration_train = data[data["received_date_dt"] < CALIBRATION_START].copy()
    calibration_set = data[(data["received_date_dt"] >= CALIBRATION_START) & (data["received_date_dt"] < TRAIN_CUTOFF)].copy()
    calibration_raw = fit_predict(calibration_train, calibration_set)
    calibrator = platt_calibrate(calibration_raw, calibration_set["target_refused"])
    calibrated = apply_platt(calibrator, ranking)

    explicit_groups = load_accepted_revision_groups(data)
    groups = build_related_project_group(train, explicit_groups).reset_index(drop=True)
    grouped_predictions, folds = grouped_oof_predictions(train, groups)
    v3_manifest = json.loads((OUTPUT_DIR / "model_v3" / "manifest.json").read_text(encoding="utf-8"))
    result = {
        "model_version": "national_residential_v4_structured_candidate",
        "status": "candidate_evaluation_only_not_deployed",
        "definition": "Text, v3 time-safe history/comparable features, and submitted structured register fields; deterministic SGD logistic candidate trained pre-2025 and evaluated on the untouched 2025 holdout.",
        "prediction_time": "immediately before submission",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "features_added_to_v3": STRUCTURED_NUMERIC,
        "structured_coverage": {column: float(data[column].notna().mean()) for column in STRUCTURED_NUMERIC},
        "temporal_2025_ranking": metrics(test["target_refused"], ranking, include_ci=True),
        "temporal_2025_calibrated": score_metrics(test["target_refused"], calibrated),
        "frozen_v3_ranking_context": v3_manifest["ranking_model"]["metrics"],
        "accepted_revision_members_mapped": int(len(explicit_groups)),
        "grouped_pre2025": {"folds": folds, "ranking_metrics": metrics(train["target_refused"], grouped_predictions, include_ci=False)},
        "limitations": [
            "Accepted revision links are evaluation grouping metadata, not model features or submission-time inputs.",
            "This uses SGD logistic regression for tractable grouped cross-validation, so it is not an estimator-identical ablation of the liblinear v3 artifact.",
            "Most rows remain singleton groups; grouped validation prevents known accepted-pair leakage but is not a comprehensive site-identity benchmark.",
            "No v4 artifact is written or used by the application until explicit review and promotion.",
        ],
    }
    predictions = test[["case_key", "PlanningAuthority", "application_bucket", "target_refused", "received_date_dt"]].copy()
    predictions["v4_ranking_score"] = ranking
    predictions["v4_platt_risk"] = calibrated
    predictions.to_csv(OUTPUT_DIR / "raw_planning_v4_2025_predictions.csv", index=False)
    (OUTPUT_DIR / "raw_planning_v4_candidate_evaluation.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
