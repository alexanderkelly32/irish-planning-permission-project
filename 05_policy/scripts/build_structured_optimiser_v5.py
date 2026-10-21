#!/usr/bin/env python3
"""Build and evaluate the v5 structured optimiser candidate.

v5 = v4 text-free structured cohort (GE10 + extracted storeys) PLUS
planner-report-extracted variables (metre heights, dwelling separations,
vehicular access points, cycle parking, front setbacks, report storeys and
parking). Same temporal discipline: pre-2025 train, 2025 prospective holdout.
Candidate only - never replaces v3.
"""
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
    calibrate_with_cv,
    evaluate_probas,
    make_lightgbm,
    make_logistic,
    sensitivity_sweep,
    split_temporal,
)
from structured_optimiser_v5 import (
    V5_FEATURES,
    build_v5_cohort,
    load_planner_reports,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
DEFAULT_SOURCE = ROOT / "02_development" / "current" / "height_storeys_extraction_2026-09-04" / "ground_source_storeys_verified.csv"

V4_ALL_FEATURES = [*STRUCTURED_FEATURES, AUTHORITY_FEATURE]
V4_BASE_ALL = [*BASE_FEATURES, AUTHORITY_FEATURE]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", type=int, default=2025, help="temporal holdout cutoff year (train strictly earlier)")
    parser.add_argument("--output-tag", type=str, default="v5", help="artifact suffix, e.g. v5b_recent_holdout")
    args = parser.parse_args()

    source = pd.read_csv(DEFAULT_SOURCE, low_memory=False)
    reports = load_planner_reports()
    cohort = build_v5_cohort(source, reports)
    train, test = split_temporal(cohort, cutoff_year=args.cutoff)
    y_test = test["target_refused"]

    v5_logistic = make_logistic(V5_FEATURES)
    v5_logistic.fit(train[V5_FEATURES], train["target_refused"])
    v5_p = v5_logistic.predict_proba(test[V5_FEATURES])[:, 1]
    calibrator = calibrate_with_cv(v5_logistic, train[V5_FEATURES], train["target_refused"])
    v5_calibrated_p = apply_calibration(calibrator, v5_p)

    v5_lgbm = make_lightgbm(V5_FEATURES)
    v5_lgbm.fit(train[V5_FEATURES], train["target_refused"])
    v5_lgbm_p = v5_lgbm.predict_proba(test[V5_FEATURES])[:, 1]

    v4_logistic = make_logistic(V4_ALL_FEATURES)
    v4_logistic.fit(train[V4_ALL_FEATURES], train["target_refused"])
    v4_p = v4_logistic.predict_proba(test[V4_ALL_FEATURES])[:, 1]

    base_logistic = make_logistic(V4_BASE_ALL)
    base_logistic.fit(train[V4_BASE_ALL], train["target_refused"])
    base_p = base_logistic.predict_proba(test[V4_BASE_ALL])[:, 1]

    medians = train[V5_FEATURES].median(numeric_only=True).to_dict()
    base_row = dict(medians)
    base_row["authority_ordinal"] = float(medians.get("authority_ordinal", 0.0))
    sweeps = {
        "storeys": sensitivity_sweep(v5_logistic, base_row, V5_FEATURES, "storeys", [1, 2, 3, 4, 5, 6, 8, 10, 12]),
        "log_max_height_m": sensitivity_sweep(v5_logistic, base_row, V5_FEATURES, "log_max_height_m", [float(f"{x:.3f}") for x in [0.7, 1.1, 1.4, 1.8, 2.2, 2.6, 3.0, 3.4]]),
        "log_nearest_dwelling_separation_m": sensitivity_sweep(v5_logistic, base_row, V5_FEATURES, "log_nearest_dwelling_separation_m", [float(f"{x:.3f}") for x in [0.7, 1.4, 2.1, 2.8, 3.4, 4.0]]),
        "log_vehicular_access_points": sensitivity_sweep(v5_logistic, base_row, V5_FEATURES, "log_vehicular_access_points", [0.0, 0.7, 1.1, 1.4, 1.8, 2.2]),
    }

    results = {
        "model_version": f"structured_optimiser_{args.output_tag}_candidate_2026-09-13",
        "holdout_cutoff_year": args.cutoff,
        "definition": (
            "Text-free structured candidate: v4 cohort plus planner-report-extracted "
            "storeys/heights/separations/access/cycle/setbacks (report values preferred "
            "where extracted, missing flags explicit). Logistic + LightGBM. Never replaces v3."
        ),
        "cohort": {
            "rows": int(len(cohort)),
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_years": [int(train["received_year"].min()), int(train["received_year"].max())],
            "test_years": [int(test["received_year"].min()), int(test["received_year"].max())],
            "planner_report_joinable_rows": int(cohort.get("report_joined", 0).sum()),
            "feature_coverage_train": {
                feature: round(float(train[feature].notna().mean()), 4)
                for feature in V5_FEATURES
            },
            "report_value_counts_train": {
                "report_joined_rows": int(train["report_joined"].eq(1).sum()),
                "storeys_present": int(train["storeys"].notna().sum()),
                "height_present": int(train["height_missing"].eq(0).sum()),
                "separation_present": int(train["separation_missing"].eq(0).sum()),
                "window_present": int(train["window_missing"].eq(0).sum()),
                "access_present": int(train["access_missing"].eq(0).sum()),
                "cycle_present": int(train["cycle_missing"].eq(0).sum()),
                "setback_present": int(train["setback_missing"].eq(0).sum()),
            },
            "report_value_counts_test": {
                "height_present": int(test["height_missing"].eq(0).sum()),
                "separation_present": int(test["separation_missing"].eq(0).sum()),
                "access_present": int(test["access_missing"].eq(0).sum()),
            },
        },
        "evaluation": {
            "v5_logistic": evaluate_probas(y_test, v5_p),
            "v5_logistic_calibrated": evaluate_probas(y_test, v5_calibrated_p),
            "v5_lightgbm": evaluate_probas(y_test, v5_lgbm_p),
            "v4_logistic_replication": evaluate_probas(y_test, v4_p),
            "base_authority_year_units_only": evaluate_probas(y_test, base_p),
            "bootstrap_ci_v5_logistic": bootstrap_ci(y_test, v5_p),
            "holdout_2025_subset": (
                evaluate_probas(y_test[test["received_year"] == 2025], v5_p[test["received_year"] == 2025])
                if (test["received_year"] == 2025).any() else None
            ),
        },
        "sensitivity_sweeps": sweeps,
        "caveat": (
            "Planner-report values are LLM extracts from OCR'd reports (verified ~100% "
            "precision, recall gaps for heights). Joinable subset is a few hundred rows, "
            "so holdout slices are small and new-feature effects are directionally "
            "suggestive only. Associations, not causal recommendations."
        ),
    }
    tag = args.output_tag
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"raw_planning_{tag}_optimiser_candidate.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    cohort.to_csv(OUTPUT_DIR / f"raw_planning_{tag}_optimiser_cohort.csv", index=False)
    test.assign(v5_logistic_risk=v5_p, v5_calibrated_risk=v5_calibrated_p, v5_lightgbm_risk=v5_lgbm_p, v4_replication_risk=v4_p).to_csv(
        OUTPUT_DIR / f"raw_planning_{tag}_optimiser_holdout_predictions.csv", index=False
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
