#!/usr/bin/env python3
"""Export the structured optimiser candidate as a frozen, caveated bundle for the app."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from structured_optimiser import (
    AUTHORITY_FEATURE,
    STRUCTURED_FEATURES,
    build_cohort,
    make_logistic,
    split_temporal,
)

ALL_FEATURES = [*STRUCTURED_FEATURES, AUTHORITY_FEATURE]

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current" / "model_structured_candidate"
DEFAULT_SOURCE = ROOT / "02_development" / "current" / "height_storeys_extraction_2026-09-04" / "ground_source_storeys_verified.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()

    cohort = build_cohort(pd.read_csv(args.source, low_memory=False))
    train, test = split_temporal(cohort, cutoff_year=2025)
    model = make_logistic(ALL_FEATURES)
    model.fit(train[ALL_FEATURES], train["target_refused"])
    test_probs = model.predict_proba(test[ALL_FEATURES])[:, 1]

    from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

    clipped = test_probs.clip(1e-6, 1 - 1e-6)
    y = test["target_refused"]

    authority_map = dict(enumerate(pd.factorize(train["PlanningAuthority"].fillna(""))[1]))
    medians = train[ALL_FEATURES].median(numeric_only=True).to_dict()

    bundle = {
        "model_version": "structured_optimiser_candidate_2026-09-08",
        "pipeline": model,
        "feature_columns": ALL_FEATURES,
        "authority_map": authority_map,
        "feature_medians": {key: float(value) for key, value in medians.items()},
        "definition": (
            "Text-free structured optimiser candidate (logistic regression over units/storeys/"
            "parking/open-space/site-area/authority/year). Experimental only: never replaces v3."
        ),
    }
    manifest = {
        "model_version": bundle["model_version"],
        "status": "experimental_candidate",
        "scope": "GE10 cohort with extracted storeys; sensitivity analysis only",
        "cohort": {"rows": int(len(cohort)), "train_rows": int(len(train)), "test_rows": int(len(test))},
        "holdout_metrics": {
            "n": int(len(test)),
            "refusal_rate": round(float(y.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y, clipped)), 4),
            "average_precision": round(float(average_precision_score(y, clipped)), 4),
            "brier": round(float(brier_score_loss(y, clipped)), 4),
            "log_loss": round(float(log_loss(y, clipped, labels=[0, 1])), 4),
        },
        "caveats": [
            "GE10-only cohort; small 2025 holdout; associations are not causal effects.",
            "Height/setback values are still too sparse to feature in this candidate.",
            "Scenario movements are modelled sensitivity, holding other inputs constant.",
        ],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, OUTPUT_DIR / "structured_optimiser_candidate.joblib")
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
