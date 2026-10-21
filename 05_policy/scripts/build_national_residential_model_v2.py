#!/usr/bin/env python3
"""Build national residential Model v2 with historical planning-context features."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
OUTPUT_DIR = ROOT / "05_policy" / "current"
V2_DIR = OUTPUT_DIR / "model_v2"
HISTORY_FEATURES_PATH = OUTPUT_DIR / "raw_planning_history_features.parquet"

sys.path.insert(0, str(SCRIPT_DIR))
from build_dublin_submission_model import calibration_intercept_slope  # noqa: E402
from build_prospective_calibration_backtest import (  # noqa: E402
    FEATURES as V1_FEATURES,
    confidence_tier,
    grouped_band_reliability,
    prepare,
    reliability,
    score_metrics,
)
from build_spatial_history_feature_experiment import (  # noqa: E402
    RAW_HISTORY_NUMERIC,
    add_history_features,
    build_scaled_pipeline,
)


TRAIN_CUTOFF = pd.Timestamp("2025-01-01", tz="UTC")
CALIBRATION_START = pd.Timestamp("2023-01-01", tz="UTC")
COUNT_COLS = [column for column in RAW_HISTORY_NUMERIC if column.endswith("_count")]
RATE_COLS = [column for column in RAW_HISTORY_NUMERIC if column.endswith("_refusal_rate")]
LOG_COUNT_COLS = [f"log_{column}" for column in COUNT_COLS]
V2_NUMERIC = ["received_year"] + LOG_COUNT_COLS + RATE_COLS
V2_FEATURES = ["PlanningAuthority", "application_bucket", "description_stripped"] + V2_NUMERIC


def load_data_with_history() -> pd.DataFrame:
    data = prepare()
    if HISTORY_FEATURES_PATH.exists():
        history = pd.read_parquet(HISTORY_FEATURES_PATH)
        history = history.drop(columns=[column for column in ["received_year"] if column in history.columns])
        data = data.merge(history, on="case_key", how="left")
    else:
        data = add_history_features(data)

    for column in COUNT_COLS:
        if column not in data.columns:
            data[column] = 0.0
        data[f"log_{column}"] = np.log1p(pd.to_numeric(data[column], errors="coerce").fillna(0))
    for column in RATE_COLS:
        if column not in data.columns:
            data[column] = np.nan
    return data


def platt_calibrate(raw_p: np.ndarray, y: pd.Series) -> LogisticRegression:
    p = np.clip(raw_p, 1e-6, 1 - 1e-6)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    return LogisticRegression(C=1_000_000, solver="lbfgs", max_iter=1000).fit(logit, y)


def apply_platt(calibrator: LogisticRegression, raw_p: np.ndarray) -> np.ndarray:
    p = np.clip(raw_p, 1e-6, 1 - 1e-6)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    return calibrator.predict_proba(logit)[:, 1]


def compact_history_reference(data: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_key",
        "PlanningAuthority",
        "application_bucket",
        "received_date_dt",
        "target_refused",
        "ITMEasting",
        "ITMNorthing",
        "SiteId",
    ]
    available = [column for column in columns if column in data.columns]
    return data[available].copy()


def main() -> None:
    data = load_data_with_history()
    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].copy()

    ranking_model = build_scaled_pipeline(V2_NUMERIC)
    ranking_model.fit(train[V2_FEATURES], train["target_refused"])
    ranking_p = ranking_model.predict_proba(test[V2_FEATURES])[:, 1]

    calibration_train = data[data["received_date_dt"] < CALIBRATION_START].copy()
    calibration_set = data[(data["received_date_dt"] >= CALIBRATION_START) & (data["received_date_dt"] < TRAIN_CUTOFF)].copy()
    calibrated_base_model = build_scaled_pipeline(V2_NUMERIC)
    calibrated_base_model.fit(calibration_train[V2_FEATURES], calibration_train["target_refused"])
    calibration_raw_p = calibrated_base_model.predict_proba(calibration_set[V2_FEATURES])[:, 1]
    test_raw_p = calibrated_base_model.predict_proba(test[V2_FEATURES])[:, 1]
    platt = platt_calibrate(calibration_raw_p, calibration_set["target_refused"])
    calibrated_test_p = apply_platt(platt, test_raw_p)
    calibrated_validation_p = apply_platt(platt, calibration_raw_p)
    band_thresholds = tuple(float(x) for x in np.quantile(calibrated_validation_p, [1 / 3, 2 / 3]))

    results: dict[str, object] = {
        "model_version": "national_residential_v2_history",
        "definition": "National residential model with submission-time text, council/type/year, and prior planning-context rates/counts.",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "ranking_model": score_metrics(test["target_refused"], ranking_p),
        "calibrated_probability_model": score_metrics(test["target_refused"], calibrated_test_p),
        "calibrated_probability_model_extra": calibration_intercept_slope(test["target_refused"], calibrated_test_p),
        "v2_numeric_features": V2_NUMERIC,
        "feature_columns": V2_FEATURES,
    }

    scored = test[["case_key", "PlanningAuthority", "application_bucket", "target_refused", "received_date_dt"]].copy()
    scored["v2_ranking_score"] = ranking_p
    scored["v2_platt_risk"] = calibrated_test_p
    scored.to_csv(OUTPUT_DIR / "raw_planning_v2_2025_predictions.csv", index=False)
    reliability(test["target_refused"], ranking_p).to_csv(OUTPUT_DIR / "raw_planning_v2_2025_ranking_reliability.csv", index=False)
    reliability(test["target_refused"], calibrated_test_p).to_csv(OUTPUT_DIR / "raw_planning_v2_2025_platt_reliability.csv", index=False)

    authority_metrics: dict[str, object] = {}
    type_metrics: dict[str, object] = {}
    for column, sink in [("PlanningAuthority", authority_metrics), ("application_bucket", type_metrics)]:
        for value, group in scored.groupby(column):
            if group["target_refused"].nunique() < 2:
                sink[str(value)] = {"n": int(len(group)), "status": "only_one_class"}
            else:
                sink[str(value)] = score_metrics(group["target_refused"], group["v2_ranking_score"].to_numpy())
    results["by_authority"] = authority_metrics
    results["by_application_type"] = type_metrics

    metadata_frame = scored[["PlanningAuthority", "application_bucket", "target_refused", "v2_platt_risk"]].copy()
    grouped_band_reliability(
        metadata_frame,
        "PlanningAuthority",
        "v2_platt_risk",
        band_thresholds,
        authority_metrics,
    ).to_csv(OUTPUT_DIR / "raw_planning_v2_reliability_by_authority.csv", index=False)
    grouped_band_reliability(
        metadata_frame,
        "application_bucket",
        "v2_platt_risk",
        band_thresholds,
        type_metrics,
    ).to_csv(OUTPUT_DIR / "raw_planning_v2_reliability_by_application_type.csv", index=False)

    V2_DIR.mkdir(parents=True, exist_ok=True)
    history_reference = compact_history_reference(data[data["received_date_dt"] < TRAIN_CUTOFF])
    bundle = {
        "model_version": "national_residential_v2_history",
        "prediction_time": "immediately before submission",
        "feature_columns": V2_FEATURES,
        "base_feature_columns": V1_FEATURES,
        "numeric_history_features": V2_NUMERIC,
        "raw_history_features": RAW_HISTORY_NUMERIC,
        "count_features": COUNT_COLS,
        "rate_features": RATE_COLS,
        "log_count_features": LOG_COUNT_COLS,
        "ranking_model": ranking_model,
        "calibrated_base_model": calibrated_base_model,
        "platt_calibrator": platt,
        "risk_band_thresholds": {"low_max": band_thresholds[0], "medium_max": band_thresholds[1]},
        "history_reference": history_reference,
    }
    joblib.dump(bundle, V2_DIR / "national_residential_v2_history.joblib", compress=3)

    manifest = {
        "model_version": bundle["model_version"],
        "status": "candidate",
        "scope": "Irish residential planning applications identified by submission-time residential signals",
        "target": "local-authority refusal versus grant/approval",
        "prediction_time": bundle["prediction_time"],
        "features": V2_FEATURES,
        "history_features": {
            "description": "Rates/counts are calculated only from applications received before the scored application.",
            "rate_features": RATE_COLS,
            "log_count_features": LOG_COUNT_COLS,
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
            "authority": str(OUTPUT_DIR / "raw_planning_v2_reliability_by_authority.csv"),
            "application_type": str(OUTPUT_DIR / "raw_planning_v2_reliability_by_application_type.csv"),
        },
        "limitations": [
            "Requires a submission date and planning authority for full history features.",
            "Nearby-history features require ITM coordinates; otherwise they should be treated as missing.",
            "History reference is frozen to pre-2025 records for this candidate backtest.",
        ],
    }
    (V2_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "raw_planning_v2_history_backtest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(V2_DIR / "manifest.json"), "ranking": results["ranking_model"], "calibrated": results["calibrated_probability_model"]}, indent=2))


if __name__ == "__main__":
    main()
