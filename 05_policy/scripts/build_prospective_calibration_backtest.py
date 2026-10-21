#!/usr/bin/env python3
"""Frozen 2025+ backtest and temporal probability calibration."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
RAW_DATA = ROOT / "old_original_attempt" / "first_attempt_messy" / "irish_planning_dataset_clean_model.parquet"
OUTPUT_DIR = ROOT / "05_policy" / "current"
V1_DIR = OUTPUT_DIR / "model_v1"
sys.path.insert(0, str(SCRIPT_DIR))
from build_dublin_submission_model import (  # noqa: E402
    bootstrap_metric_ci,
    build_simple_pipeline,
    calibration_intercept_slope,
    decision_to_submission_target,
    strip_text_leakage_clues,
)
from build_raw_planning_benchmarks import residential_bucket  # noqa: E402


FEATURES = ["received_year", "PlanningAuthority", "application_bucket", "description_stripped"]


def prepare() -> pd.DataFrame:
    df = pd.read_parquet(RAW_DATA)
    units = pd.to_numeric(df["NumResidentialUnits"], errors="coerce")
    terms = r"\b(?:apartment|apartments|dwelling|dwellings|house|houses|residential|home|extension|retention|change of use|one-off|one off)\b"
    residential = units.gt(0) | df["OneOffHouse"].fillna("").astype(str).str.strip().str.lower().isin({"y", "yes", "one", "single house"})
    residential |= df["DevelopmentDescription"].fillna("").astype(str).str.contains(terms, case=False, regex=True)
    df = df[residential].copy()
    df["received_date_dt"] = pd.to_datetime(df["ReceivedDate"], utc=True, errors="coerce")
    df["received_year"] = df["received_date_dt"].dt.year.astype(float)
    df["description_stripped"] = df["DevelopmentDescription"].map(strip_text_leakage_clues)
    df["application_bucket"] = df.apply(residential_bucket, axis=1)
    targets = df["Decision"].map(decision_to_submission_target)
    df["target_refused"] = [x[0] for x in targets]
    df["target_mapping_status"] = [x[1] for x in targets]
    df["case_key"] = df["PlanningAuthority"].fillna("").astype(str) + "__" + df["ApplicationNumber"].fillna("").astype(str)
    return df[df["target_refused"].notna() & df["received_date_dt"].notna()].drop_duplicates("case_key").sort_values(["received_date_dt", "case_key"])


def fit_model(train: pd.DataFrame):
    model = build_simple_pipeline(
        numeric=["received_year"],
        categorical=["PlanningAuthority", "application_bucket"],
        include_text=True,
        text_column="description_stripped",
    )
    model.fit(train[FEATURES], train["target_refused"])
    return model


def score_metrics(y: pd.Series, p: np.ndarray) -> dict[str, float | int]:
    from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

    out = {
        "n": int(len(y)),
        "refusal_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, p)) if y.nunique() == 2 else np.nan,
        "average_precision": float(average_precision_score(y, p)) if y.nunique() == 2 else np.nan,
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1])),
    }
    if y.nunique() == 2:
        out.update(bootstrap_metric_ci(y, p, n_boot=500))
        out.update(calibration_intercept_slope(y, p))
    return out


def reliability(y: pd.Series, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    frame = pd.DataFrame({"target_refused": y.to_numpy(), "predicted_risk": p})
    frame["risk_band"] = pd.qcut(frame["predicted_risk"].rank(method="first"), q=min(bins, len(frame)), labels=False) + 1
    return frame.groupby("risk_band", as_index=False).agg(
        cases=("target_refused", "size"),
        mean_predicted_risk=("predicted_risk", "mean"),
        actual_refusal_rate=("target_refused", "mean"),
    )


def confidence_tier(n: int, auc: float | None) -> str:
    if auc is None or pd.isna(auc) or n < 100:
        return "limited"
    if n >= 500 and auc >= 0.75:
        return "good"
    if n >= 250 and auc >= 0.65:
        return "moderate"
    return "limited"


def grouped_band_reliability(
    scored: pd.DataFrame,
    group_col: str,
    score_col: str,
    thresholds: tuple[float, float],
    performance: dict[str, object],
) -> pd.DataFrame:
    low, high = thresholds
    frame = scored.copy()
    frame["risk_band"] = pd.cut(frame[score_col], bins=[-np.inf, low, high, np.inf], labels=["Low", "Medium", "High"])
    rows = []
    for (group, band), part in frame.groupby([group_col, "risk_band"], observed=False):
        payload = performance.get(str(group), {}) if isinstance(performance, dict) else {}
        auc = payload.get("roc_auc") if isinstance(payload, dict) else None
        group_n = int(payload.get("n", len(frame[frame[group_col] == group]))) if isinstance(payload, dict) else int(len(part))
        rows.append(
            {
                group_col: group,
                "risk_band": str(band),
                "cases": int(len(part)),
                "mean_calibrated_risk": float(part[score_col].mean()) if len(part) else np.nan,
                "actual_refusal_rate": float(part["target_refused"].mean()) if len(part) else np.nan,
                "evaluation_n": group_n,
                "evaluation_auc": auc,
                "confidence": confidence_tier(group_n, auc),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    data = prepare()
    train_end = pd.Timestamp("2025-01-01", tz="UTC")
    calibration_start = pd.Timestamp("2023-01-01", tz="UTC")
    train = data[data["received_date_dt"] < train_end].copy()
    test = data[data["received_date_dt"] >= train_end].copy()
    model = fit_model(train)
    test["frozen_refusal_score"] = model.predict_proba(test[FEATURES])[:, 1]

    results: dict[str, object] = {
        "definition": "Train on all eligible applications received before 2025-01-01; score later applications without retraining.",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "train_start": str(train["received_date_dt"].min()),
        "train_end": str(train["received_date_dt"].max()),
        "test_start": str(test["received_date_dt"].min()),
        "test_end": str(test["received_date_dt"].max()),
        "national": score_metrics(test["target_refused"], test["frozen_refusal_score"].to_numpy()),
        "by_authority": {},
        "by_application_type": {},
    }
    for column, key in [("PlanningAuthority", "by_authority"), ("application_bucket", "by_application_type")]:
        for value, group in test.groupby(column):
            results[key][str(value)] = score_metrics(group["target_refused"], group["frozen_refusal_score"].to_numpy())
    reliability(test["target_refused"], test["frozen_refusal_score"]).to_csv(OUTPUT_DIR / "raw_planning_frozen_2025_reliability.csv", index=False)

    # Separate temporal calibration track: fit classifier through 2022,
    # calibrate on 2023-2024, and evaluate on the untouched 2025+ period.
    calibration_train = data[data["received_date_dt"] < calibration_start].copy()
    calibration_set = data[(data["received_date_dt"] >= calibration_start) & (data["received_date_dt"] < train_end)].copy()
    calibration_model = fit_model(calibration_train)
    calibration_p = calibration_model.predict_proba(calibration_set[FEATURES])[:, 1]
    test_p = calibration_model.predict_proba(test[FEATURES])[:, 1]
    logit = np.log(np.clip(calibration_p, 1e-6, 1 - 1e-6) / (1 - np.clip(calibration_p, 1e-6, 1 - 1e-6))).reshape(-1, 1)
    calibrator = LogisticRegression(C=1_000_000, solver="lbfgs", max_iter=1000).fit(logit, calibration_set["target_refused"])
    test_logit = np.log(np.clip(test_p, 1e-6, 1 - 1e-6) / (1 - np.clip(test_p, 1e-6, 1 - 1e-6))).reshape(-1, 1)
    calibrated_p = calibrator.predict_proba(test_logit)[:, 1]
    isotonic = IsotonicRegression(out_of_bounds="clip").fit(calibration_p, calibration_set["target_refused"])
    isotonic_p = isotonic.predict(test_p)
    results["temporal_calibration"] = {
        "classifier_train_n": int(len(calibration_train)),
        "calibration_n": int(len(calibration_set)),
        "calibration_start": str(calibration_set["received_date_dt"].min()),
        "calibration_end": str(calibration_set["received_date_dt"].max()),
        "test_n": int(len(test)),
        "uncalibrated": score_metrics(test["target_refused"], test_p),
        "platt_logistic": score_metrics(test["target_refused"], calibrated_p),
        "isotonic": score_metrics(test["target_refused"], isotonic_p),
    }
    calibration_output = test[["case_key", "PlanningAuthority", "application_bucket", "target_refused"]].copy()
    calibration_output["uncalibrated_risk"] = test_p
    calibration_output["platt_risk"] = calibrated_p
    calibration_output["isotonic_risk"] = isotonic_p
    calibration_output.to_csv(OUTPUT_DIR / "raw_planning_frozen_2025_calibration_predictions.csv", index=False)
    reliability(test["target_refused"], calibrated_p).to_csv(OUTPUT_DIR / "raw_planning_frozen_2025_platt_reliability.csv", index=False)

    calibration_calibrated_p = calibrator.predict_proba(logit)[:, 1]
    band_thresholds = tuple(float(x) for x in np.quantile(calibration_calibrated_p, [1 / 3, 2 / 3]))
    scored_for_metadata = test[["PlanningAuthority", "application_bucket", "target_refused"]].copy()
    scored_for_metadata["platt_risk"] = calibrated_p
    authority_reliability = grouped_band_reliability(
        scored_for_metadata,
        "PlanningAuthority",
        "platt_risk",
        band_thresholds,
        results["by_authority"],
    )
    type_reliability = grouped_band_reliability(
        scored_for_metadata,
        "application_bucket",
        "platt_risk",
        band_thresholds,
        results["by_application_type"],
    )
    authority_reliability.to_csv(OUTPUT_DIR / "raw_planning_v1_reliability_by_authority.csv", index=False)
    type_reliability.to_csv(OUTPUT_DIR / "raw_planning_v1_reliability_by_application_type.csv", index=False)

    V1_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model_version": "national_residential_v1",
        "prediction_time": "immediately before submission",
        "feature_columns": FEATURES,
        "ranking_model": model,
        "calibrated_base_model": calibration_model,
        "platt_calibrator": calibrator,
        "risk_band_thresholds": {"low_max": band_thresholds[0], "medium_max": band_thresholds[1]},
    }
    joblib.dump(bundle, V1_DIR / "national_residential_v1.joblib")
    manifest = {
        "model_version": "national_residential_v1",
        "status": "frozen",
        "scope": "Irish residential planning applications identified by submission-time residential signals",
        "target": "local-authority refusal versus grant/approval",
        "prediction_time": "immediately before submission",
        "features": FEATURES,
        "banned_inputs": ["FI requests", "decision fields", "appeals", "refusal reasons", "post-submission status"],
        "ranking_model": {
            "training_cutoff_exclusive": "2025-01-01",
            "training_rows": int(len(train)),
            "prospective_test_period": [str(test["received_date_dt"].min()), str(test["received_date_dt"].max())],
            "metrics": results["national"],
        },
        "calibrated_probability_model": {
            "classifier_training_cutoff_exclusive": "2023-01-01",
            "classifier_training_rows": int(len(calibration_train)),
            "calibration_period": [str(calibration_set["received_date_dt"].min()), str(calibration_set["received_date_dt"].max())],
            "calibration_rows": int(len(calibration_set)),
            "prospective_metrics": results["temporal_calibration"]["platt_logistic"],
        },
        "risk_band_thresholds": bundle["risk_band_thresholds"],
        "reliability_metadata": {
            "authority": str(OUTPUT_DIR / "raw_planning_v1_reliability_by_authority.csv"),
            "application_type": str(OUTPUT_DIR / "raw_planning_v1_reliability_by_application_type.csv"),
        },
        "limitations": [
            "Council and application-type performance varies materially.",
            "Probabilities require continued prospective monitoring and periodic recalibration.",
            "The classifier estimates historical outcome risk; it does not determine planning-law compliance.",
        ],
    }
    (V1_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "raw_planning_frozen_2025_backtest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
