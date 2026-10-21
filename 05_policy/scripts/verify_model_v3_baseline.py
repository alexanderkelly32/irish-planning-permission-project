#!/usr/bin/env python3
"""Verify the frozen Model v3 holdout outputs without rebuilding artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "05_policy" / "current" / "model_v3"
PREDICTIONS = ROOT / "05_policy" / "current" / "raw_planning_v3_2025_predictions.csv"
sys.path.insert(0, str(ROOT / "06_copilot" / "scripts"))
from precedent_copilot_logic import score_submission_risk  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric_block(y: pd.Series, p: pd.Series) -> dict[str, float]:
    values = np.clip(p.to_numpy(dtype=float), 1e-6, 1 - 1e-6)
    return {
        "roc_auc": float(roc_auc_score(y, values)),
        "average_precision": float(average_precision_score(y, values)),
        "brier": float(brier_score_loss(y, values)),
        "log_loss": float(log_loss(y, values, labels=[0, 1])),
    }


def snapshot_signature(snapshot: dict[str, object]) -> str:
    normalized = {}
    for key, value in snapshot.items():
        if isinstance(value, (float, np.floating)) and not np.isfinite(value):
            normalized[key] = None
        else:
            normalized[key] = value.item() if isinstance(value, np.generic) else value
    return json.dumps(normalized, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()

    predictions = pd.read_csv(PREDICTIONS)
    y = predictions["target_refused"]
    manifest = json.loads((MODEL_DIR / "manifest.json").read_text(encoding="utf-8"))
    bundle = joblib.load(MODEL_DIR / "national_residential_v3_comparables.joblib")
    query = {
        "PlanningAuthority": "Dublin City Council",
        "ApplicationType": "New development",
        "DevelopmentDescription": "Construction of 42 apartments with communal open space and vehicular access.",
        "units_total_best": 42,
        "received_year": 2026.0,
    }
    first = score_submission_risk(query, bundle)
    second = score_submission_risk(query, bundle)
    deterministic = (
        first.get("refusal_score") == second.get("refusal_score")
        and snapshot_signature(first.get("feature_snapshot", {}))
        == snapshot_signature(second.get("feature_snapshot", {}))
    )
    result = {
        "verification": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {
                "pandas": pd.__version__,
                "numpy": np.__version__,
                "scikit_learn": sklearn.__version__,
                "joblib": joblib.__version__,
            },
            "metric_tolerance": 1e-12,
            "command": "python 05_policy/scripts/verify_model_v3_baseline.py --registry 05_policy/baselines/model_v3_2026-09-01.json",
        },
        "model_version": manifest["model_version"],
        "holdout": {
            "n": int(len(predictions)),
            "refusal_rate": float(y.mean()),
            "date_min": str(predictions["received_date_dt"].min()),
            "date_max": str(predictions["received_date_dt"].max()),
            "ranking": metric_block(y, predictions["v3_ranking_score"]),
            "calibrated": metric_block(y, predictions["v3_platt_risk"]),
        },
        "smoke": {
            "deterministic": deterministic,
            "risk_score_0_100": first.get("risk_score_0_100"),
            "risk_band": first.get("risk_band"),
            "feature_keys": sorted(first.get("feature_snapshot", {})),
        },
        "sha256": {
            "model": sha256(MODEL_DIR / "national_residential_v3_comparables.joblib"),
            "manifest": sha256(MODEL_DIR / "manifest.json"),
            "predictions": sha256(PREDICTIONS),
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.registry:
        args.registry.parent.mkdir(parents=True, exist_ok=True)
        args.registry.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
