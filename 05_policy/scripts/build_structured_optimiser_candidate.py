#!/usr/bin/env python3
"""Train and evaluate the text-free structured optimiser candidate (Task 4)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from structured_optimiser import (
    AUTHORITY_FEATURE,
    BASE_FEATURES,
    STRUCTURED_FEATURES,
    apply_calibration,
    bootstrap_ci,
    build_cohort,
    calibrate_with_cv,
    evaluate_probas,
    make_lightgbm,
    make_logistic,
    sensitivity_sweep,
    split_temporal,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
DEFAULT_SOURCE = ROOT / "02_development" / "current" / "height_storeys_extraction_2026-09-04" / "ground_source_storeys_verified.csv"

ALL_FEATURES = [*STRUCTURED_FEATURES, AUTHORITY_FEATURE]
BASE_ALL = [*BASE_FEATURES, AUTHORITY_FEATURE]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()

    cohort = build_cohort(pd.read_csv(args.source, low_memory=False))
    train, test = split_temporal(cohort, cutoff_year=2025)
    y_test = test["target_refused"]

    logistic = make_logistic(ALL_FEATURES)
    logistic.fit(train[ALL_FEATURES], train["target_refused"])
    logistic_p = logistic.predict_proba(test[ALL_FEATURES])[:, 1]
    calibrator = calibrate_with_cv(logistic, train[ALL_FEATURES], train["target_refused"])
    calibrated_p = apply_calibration(calibrator, logistic_p)

    lgbm = make_lightgbm(ALL_FEATURES)
    lgbm.fit(train[ALL_FEATURES], train["target_refused"])
    lgbm_p = lgbm.predict_proba(test[ALL_FEATURES])[:, 1]

    base_logistic = make_logistic(BASE_ALL)
    base_logistic.fit(train[BASE_ALL], train["target_refused"])
    base_p = base_logistic.predict_proba(test[BASE_ALL])[:, 1]

    # Sensitivity sweeps on the logistic model with medians held constant.
    medians = train[ALL_FEATURES].median(numeric_only=True).to_dict()
    base_row = dict(medians)
    base_row["authority_ordinal"] = float(train[train["PlanningAuthority"] == "Dublin City Council"]["authority_ordinal"].mode().iloc[0]) if not train[train["PlanningAuthority"] == "Dublin City Council"].empty else float(medians["authority_ordinal"])
    sweeps = {
        "storeys": sensitivity_sweep(logistic, base_row, ALL_FEATURES, "storeys", [1, 2, 3, 4, 5, 6, 8, 10, 12]),
        "log_units": sensitivity_sweep(logistic, base_row, ALL_FEATURES, "log_units", [float(f"{(x)}") for x in ["2.30", "2.71", "3.00", "3.69", "4.25", "4.61", "5.30"]]),
        "log_parking_spaces": sensitivity_sweep(logistic, base_row, ALL_FEATURES, "log_parking_spaces", [0.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
    }

    results = {
        "model_version": "structured_optimiser_candidate_2026-09-04",
        "definition": "Text-free structured cohort model (GE10 + extracted storeys); logistic regression and LightGBM on structured design variables only. Candidate only - never replaces v3.",
        "cohort": {
            "rows": int(len(cohort)),
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_years": [int(train["received_year"].min()), int(train["received_year"].max())],
            "test_years": [int(test["received_year"].min()), int(test["received_year"].max())],
            "feature_coverage": {
                feature: round(float(train[feature].notna().mean()), 4)
                for feature in ALL_FEATURES
            },
        },
        "evaluation": {
            "structured_logistic": evaluate_probas(y_test, logistic_p),
            "structured_logistic_calibrated": evaluate_probas(y_test, calibrated_p),
            "structured_lightgbm": evaluate_probas(y_test, lgbm_p),
            "base_authority_year_units_only": evaluate_probas(y_test, base_p),
            "bootstrap_ci_logistic": bootstrap_ci(y_test, logistic_p),
        },
        "sensitivity_sweeps": sweeps,
        "caveat": (
            "GE10-only cohort with a small 2025 holdout; storeys values are LLM extracts with a "
            "100-row human verification sample (96.2% precision, 81.0% recall) and verified "
            "values overlaid where available. Effects are associations in a candidate model, "
            "not causal recommendations."
        ),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "raw_planning_structured_optimiser_candidate.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    cohort.to_csv(OUTPUT_DIR / "raw_planning_structured_optimiser_cohort.csv", index=False)
    test.assign(structured_logistic_risk=logistic_p, structured_calibrated_risk=calibrated_p, structured_lightgbm_risk=lgbm_p).to_csv(
        OUTPUT_DIR / "raw_planning_structured_optimiser_2025_predictions.csv", index=False
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
