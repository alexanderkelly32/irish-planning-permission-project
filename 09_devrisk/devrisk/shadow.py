"""Shadow deployment: append-only, write-once prediction log.

Predictions are frozen at write time with model version, state, feature
snapshot and interval; outcomes are filled later and scored. Predictions
are never regenerated retrospectively - the log is append-only and
prediction_id collisions raise.

Table: silver/shadow/shadow_predictions.csv
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from devrisk import settings

SHADOW_DIR = settings.SILVER_DIR / "shadow"
SHADOW_DIR.mkdir(parents=True, exist_ok=True)
TABLE_PATH = SHADOW_DIR / "shadow_predictions.csv"

COLUMNS = ["prediction_id", "case_key", "prediction_timestamp", "model_version",
           "state_at_prediction", "target_transition", "prediction",
           "features_snapshot", "eventual_observed_outcome", "outcome_date", "source"]


def _load() -> pd.DataFrame:
    if TABLE_PATH.exists():
        return pd.read_csv(TABLE_PATH, dtype=str)
    return pd.DataFrame(columns=COLUMNS)


def log_prediction(case_key: str, model_version: str, state_at_prediction: str,
                   target_transition: str, prediction: dict,
                   features_snapshot: dict | None = None,
                   source: str = "engine",
                   timestamp: str | None = None) -> str:
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    pred_id = hashlib.sha256(
        f"{case_key}|{model_version}|{state_at_prediction}|{target_transition}|{ts}".encode()
    ).hexdigest()[:16]
    frame = _load()
    if pred_id in set(frame["prediction_id"]) if len(frame) else False:
        raise ValueError(f"prediction_id {pred_id} already exists - predictions are write-once")
    row = {"prediction_id": pred_id, "case_key": case_key,
           "prediction_timestamp": ts, "model_version": model_version,
           "state_at_prediction": state_at_prediction,
           "target_transition": target_transition,
           "prediction": json.dumps(prediction),
           "features_snapshot": json.dumps(features_snapshot or {}),
           "eventual_observed_outcome": "",
           "outcome_date": "", "source": source}
    frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True)
    frame.to_csv(TABLE_PATH, index=False)
    return pred_id


def record_outcome(prediction_id: str, observed_days: float, outcome_date: str) -> None:
    frame = _load()
    mask = frame["prediction_id"] == prediction_id
    if not mask.any():
        raise KeyError(f"unknown prediction_id {prediction_id}")
    frame.loc[mask, "eventual_observed_outcome"] = str(observed_days)
    frame.loc[mask, "outcome_date"] = outcome_date
    frame.to_csv(TABLE_PATH, index=False)


def score_shadow() -> dict:
    frame = _load()
    resolved = frame[(frame["eventual_observed_outcome"] != "") & (frame["eventual_observed_outcome"].notna())]
    out = {"n_total": int(len(frame)), "n_resolved": int(len(resolved))}
    if not len(resolved):
        return out
    preds = resolved["prediction"].map(json.loads)
    med = pd.to_numeric(preds.map(lambda p: p.get("median_days")), errors="coerce")
    obs = pd.to_numeric(resolved["eventual_observed_outcome"], errors="coerce")
    lo50 = pd.to_numeric(preds.map(lambda p: p.get("pct50_lower")), errors="coerce")
    hi50 = pd.to_numeric(preds.map(lambda p: p.get("pct50_upper")), errors="coerce")
    lo80 = pd.to_numeric(preds.map(lambda p: p.get("pct80_lower")), errors="coerce")
    hi80 = pd.to_numeric(preds.map(lambda p: p.get("pct80_upper")), errors="coerce")
    out.update({
        "mae_days": round(float((obs - med).abs().mean()), 1),
        "median_abs_days": round(float((obs - med).abs().median()), 1),
        "pct50_coverage": round(float(((obs >= lo50) & (obs <= hi50)).mean() * 100), 1),
        "pct80_coverage": round(float(((obs >= lo80) & (obs <= hi80)).mean() * 100), 1),
        "within_3m_hit": round(float((obs <= 91).mean() * 100), 1),
        "within_6m_hit": round(float((obs <= 183).mean() * 100), 1),
        "within_12m_hit": round(float((obs <= 365).mean() * 100), 1),
    })
    return out
