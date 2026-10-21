#!/usr/bin/env python3
"""Screen structured submission-time fields against frozen v3; never promotes a model."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
OUTPUT_DIR = ROOT / "05_policy" / "current"
sys.path.insert(0, str(SCRIPT_DIR))

from build_comparable_feature_experiment import COMPARABLE_FEATURES_PATH, V3_NUMERIC, metrics  # noqa: E402
from build_national_residential_model_v2 import TRAIN_CUTOFF, load_data_with_history  # noqa: E402
from structured_feature_utils import STRUCTURED_NUMERIC, add_structured_scheme_features  # noqa: E402

CATEGORICAL = ["PlanningAuthority", "application_bucket"]


def fit_score(train: pd.DataFrame, test: pd.DataFrame, numeric: list[str]) -> tuple[dict, np.ndarray]:
    features = CATEGORICAL + numeric
    preprocessor = ColumnTransformer([
        ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median"))]), numeric),
        ("categorical", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), CATEGORICAL),
    ])
    model = Pipeline([("preprocessor", preprocessor), ("model", SGDClassifier(loss="log_loss", alpha=0.0001, max_iter=100, tol=1e-3, class_weight="balanced", random_state=42))])
    model.fit(train[features], train["target_refused"])
    predicted = model.predict_proba(test[features])[:, 1]
    return metrics(test["target_refused"], predicted, include_ci=True), predicted


def main() -> None:
    comparable = pd.read_parquet(COMPARABLE_FEATURES_PATH)
    data = load_data_with_history().merge(comparable, on="case_key", how="left")
    data = add_structured_scheme_features(data)
    data[STRUCTURED_NUMERIC] = data[STRUCTURED_NUMERIC].replace([float("inf"), float("-inf")], np.nan)
    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].copy()
    base_metrics, base_predicted = fit_score(train, test, V3_NUMERIC)
    candidate_metrics, predicted = fit_score(train, test, V3_NUMERIC + STRUCTURED_NUMERIC)
    v3_manifest = json.loads((OUTPUT_DIR / "model_v3" / "manifest.json").read_text(encoding="utf-8"))
    baseline = v3_manifest["ranking_model"]["metrics"]
    result = {
        "status": "text_free_incremental_signal_screening_not_promoted",
        "definition": "Frozen pre-2025 training and 2025 prospective holdout. Both arms use authority, application bucket, time-safe history and comparable aggregates; only the candidate adds structured register fields. Neither arm includes description text. The classifier is deterministic SGD logistic regression for fast signal screening.",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "features_added": STRUCTURED_NUMERIC,
        "coverage": {column: float(data[column].notna().mean()) for column in STRUCTURED_NUMERIC},
        "text_free_base_metrics": base_metrics,
        "text_free_structured_metrics": candidate_metrics,
        "delta_structured_minus_text_free_base": {key: float(candidate_metrics[key] - base_metrics[key]) for key in ["roc_auc", "average_precision", "brier", "log_loss"]},
        "frozen_v3_ranking_context": {key: baseline[key] for key in ["roc_auc", "average_precision", "brier", "log_loss"]},
        "limitations": [
            "This screening omits text and is not a deployable model or a direct replacement benchmark for v3.",
            "Height, setbacks, amenity and transport fields are not included because national coverage is not yet adequate.",
            "Do not expose structured scenario effects until a candidate passes calibration, subgroup and grouped-project robustness checks.",
        ],
    }
    output = OUTPUT_DIR / "raw_planning_v4_structured_screening.json"
    predictions = test[["case_key", "PlanningAuthority", "application_bucket", "target_refused", "received_date_dt"]].copy()
    predictions["v4_structured_screening_score"] = predicted
    predictions.to_csv(OUTPUT_DIR / "raw_planning_v4_structured_screening_predictions.csv", index=False)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
