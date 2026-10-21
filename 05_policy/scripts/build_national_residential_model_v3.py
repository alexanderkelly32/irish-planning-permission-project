#!/usr/bin/env python3
"""Build national residential Model v3 with history and comparable-case features."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
OUTPUT_DIR = ROOT / "05_policy" / "current"
V3_DIR = OUTPUT_DIR / "model_v3"

sys.path.insert(0, str(SCRIPT_DIR))
from build_comparable_feature_experiment import (  # noqa: E402
    COMPARABLE_FEATURES_PATH,
    COMPARABLE_NUMERIC,
    REFERENCE_LOOKBACK_YEARS,
    V3_FEATURES,
    V3_NUMERIC,
    build_comparable_features,
    metrics,
)
from build_national_residential_model_v2 import (  # noqa: E402
    CALIBRATION_START,
    TRAIN_CUTOFF,
    apply_platt,
    build_scaled_pipeline,
    load_data_with_history,
    platt_calibrate,
)
from build_prospective_calibration_backtest import grouped_band_reliability, reliability, score_metrics  # noqa: E402


def add_comparable_features(data: pd.DataFrame) -> pd.DataFrame:
    comparable = build_comparable_features(data)
    return data.merge(comparable, on="case_key", how="left")


def fit_predict(train: pd.DataFrame, test: pd.DataFrame) -> tuple[object, np.ndarray]:
    model = build_scaled_pipeline(V3_NUMERIC)
    model.fit(train[V3_FEATURES], train["target_refused"])
    return model, model.predict_proba(test[V3_FEATURES])[:, 1]


def compact_comparable_reference(data: pd.DataFrame) -> pd.DataFrame:
    return data[
        [
            "case_key",
            "PlanningAuthority",
            "application_bucket",
            "received_date_dt",
            "target_refused",
            "description_stripped",
        ]
    ].copy()


def main() -> None:
    data = load_data_with_history().reset_index(drop=True)
    data = add_comparable_features(data)
    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].copy()

    ranking_model, ranking_p = fit_predict(train, test)

    calibration_train = data[data["received_date_dt"] < CALIBRATION_START].copy()
    calibration_set = data[(data["received_date_dt"] >= CALIBRATION_START) & (data["received_date_dt"] < TRAIN_CUTOFF)].copy()
    calibrated_base_model, _ = fit_predict(calibration_train, calibration_set)
    calibration_raw_p = calibrated_base_model.predict_proba(calibration_set[V3_FEATURES])[:, 1]
    test_raw_p = calibrated_base_model.predict_proba(test[V3_FEATURES])[:, 1]
    platt = platt_calibrate(calibration_raw_p, calibration_set["target_refused"])
    calibrated_test_p = apply_platt(platt, test_raw_p)
    calibrated_validation_p = apply_platt(platt, calibration_raw_p)
    band_thresholds = tuple(float(x) for x in np.quantile(calibrated_validation_p, [1 / 3, 2 / 3]))

    results: dict[str, object] = {
        "model_version": "national_residential_v3_comparables",
        "definition": "National residential model with v2 history features plus time-safe text-similar precedent outcome features.",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "ranking_model": metrics(test["target_refused"], ranking_p, include_ci=True),
        "calibrated_probability_model": score_metrics(test["target_refused"], calibrated_test_p),
        "feature_columns": V3_FEATURES,
        "comparable_features": COMPARABLE_NUMERIC,
    }

    scored = test[["case_key", "PlanningAuthority", "application_bucket", "target_refused", "received_date_dt"]].copy()
    scored["v3_ranking_score"] = ranking_p
    scored["v3_platt_risk"] = calibrated_test_p
    scored.to_csv(OUTPUT_DIR / "raw_planning_v3_2025_predictions.csv", index=False)
    reliability(test["target_refused"], ranking_p).to_csv(OUTPUT_DIR / "raw_planning_v3_2025_ranking_reliability.csv", index=False)
    reliability(test["target_refused"], calibrated_test_p).to_csv(OUTPUT_DIR / "raw_planning_v3_2025_platt_reliability.csv", index=False)

    authority_metrics: dict[str, object] = {}
    type_metrics: dict[str, object] = {}
    for column, sink in [("PlanningAuthority", authority_metrics), ("application_bucket", type_metrics)]:
        for value, group in scored.groupby(column):
            if group["target_refused"].nunique() < 2:
                sink[str(value)] = {"n": int(len(group)), "status": "only_one_class"}
            else:
                sink[str(value)] = score_metrics(group["target_refused"], group["v3_ranking_score"].to_numpy())
    results["by_authority"] = authority_metrics
    results["by_application_type"] = type_metrics

    metadata_frame = scored[["PlanningAuthority", "application_bucket", "target_refused", "v3_platt_risk"]].copy()
    grouped_band_reliability(
        metadata_frame,
        "PlanningAuthority",
        "v3_platt_risk",
        band_thresholds,
        authority_metrics,
    ).to_csv(OUTPUT_DIR / "raw_planning_v3_reliability_by_authority.csv", index=False)
    grouped_band_reliability(
        metadata_frame,
        "application_bucket",
        "v3_platt_risk",
        band_thresholds,
        type_metrics,
    ).to_csv(OUTPUT_DIR / "raw_planning_v3_reliability_by_application_type.csv", index=False)

    comparable_vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=80_000,
        min_df=2,
        sublinear_tf=True,
        strip_accents="unicode",
    )
    comparable_vectorizer.fit(train["description_stripped"].fillna("").astype(str))

    V3_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model_version": "national_residential_v3_comparables",
        "prediction_time": "immediately before submission",
        "feature_columns": V3_FEATURES,
        "numeric_features": V3_NUMERIC,
        "comparable_features": COMPARABLE_NUMERIC,
        "comparable_lookback_years": REFERENCE_LOOKBACK_YEARS,
        "ranking_model": ranking_model,
        "calibrated_base_model": calibrated_base_model,
        "platt_calibrator": platt,
        "risk_band_thresholds": {"low_max": band_thresholds[0], "medium_max": band_thresholds[1]},
        "history_reference": joblib.load(OUTPUT_DIR / "model_v2" / "national_residential_v2_history.joblib").get("history_reference"),
        "comparable_reference": compact_comparable_reference(train),
        "comparable_vectorizer": comparable_vectorizer,
    }
    joblib.dump(bundle, V3_DIR / "national_residential_v3_comparables.joblib", compress=3)

    manifest = {
        "model_version": bundle["model_version"],
        "status": "candidate",
        "scope": "Irish residential planning applications identified by submission-time residential signals",
        "target": "local-authority refusal versus grant/approval",
        "prediction_time": bundle["prediction_time"],
        "features": V3_FEATURES,
        "comparable_features": {
            "description": "For each scored application, retrieve text-similar prior applications in the same residential bucket and aggregate their outcomes.",
            "lookback_years": REFERENCE_LOOKBACK_YEARS,
            "features": COMPARABLE_NUMERIC,
            "feature_cache": str(COMPARABLE_FEATURES_PATH),
        },
        "banned_inputs": ["FI requests", "decision fields for the scored case", "appeals", "refusal reasons", "post-submission status"],
        "ranking_model": {
            "training_cutoff_exclusive": "2025-01-01",
            "training_rows": int(len(train)),
            "prospective_test_period": [str(test["received_date_dt"].min()), str(test["received_date_dt"].max())],
            "metrics": results["ranking_model"],
        },
        "calibrated_probability_model": {
            "classifier_training_cutoff_exclusive": "2023-01-01",
            "classifier_training_rows": int(len(calibration_train)),
            "calibration_period": [str(calibration_set["received_date_dt"].min()), str(calibration_set["received_date_dt"].max())],
            "calibration_rows": int(len(calibration_set)),
            "prospective_metrics": results["calibrated_probability_model"],
        },
        "risk_band_thresholds": bundle["risk_band_thresholds"],
        "reliability_metadata": {
            "authority": str(OUTPUT_DIR / "raw_planning_v3_reliability_by_authority.csv"),
            "application_type": str(OUTPUT_DIR / "raw_planning_v3_reliability_by_application_type.csv"),
        },
        "limitations": [
            "Comparable features are text-based and should be audited for over-reliance on repeated wording.",
            "The candidate uses previous-year comparables for historical training rows and pre-2025 comparables for the 2025 test.",
            "The app uses the frozen pre-2025 comparable reference for future-dated queries until a fresh model snapshot is built.",
        ],
    }
    (V3_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "raw_planning_v3_comparable_backtest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(V3_DIR / "manifest.json"), "ranking": results["ranking_model"], "calibrated": results["calibrated_probability_model"]}, indent=2))


if __name__ == "__main__":
    main()
