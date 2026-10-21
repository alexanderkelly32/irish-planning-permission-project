"""Permission-timing engine (e + i): score P20/P50/P80 and explain drivers.

Loads the persisted GBM quantile models (gold/decision_timing_gbm_v1.joblib),
computes time-safe authority-congestion features at query time from register
rows received before the query date, scores the three quantiles, and exposes
per-model feature importances as the driver table (product brief 6.4/6.8).
"""
from __future__ import annotations

from typing import Any

import joblib
import numpy as np
import pandas as pd

from .. import settings

HORIZON_DAYS = (183, 365)


def load_artifact():
    return joblib.load(settings.GOLD_DIR / "decision_timing_gbm_v1.joblib")


def _congestion_features(register: pd.DataFrame, authority: str, query_date: pd.Timestamp) -> dict[str, float]:
    earlier = register[
        (register["PlanningAuthority"] == authority)
        & (register["received_date_dt"] < query_date)
    ]
    prior_90d = earlier[earlier["received_date_dt"] >= query_date - pd.Timedelta(days=90)]
    prior_180d = earlier[earlier["received_date_dt"] >= query_date - pd.Timedelta(days=180)]
    median = prior_180d["duration_days"].median()
    return {
        "auth_prior_90d_count": float(len(prior_90d)),
        "auth_prior_180d_median_duration": float(median) if not pd.isna(median) else 136.0,
    }


def _register_durations() -> pd.DataFrame:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = register.copy()
    frame["received_date_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["decision_date_dt"] = pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce")
    frame["duration_days"] = (frame["decision_date_dt"] - frame["received_date_dt"]).dt.days
    return frame[frame["received_date_dt"].notna() & frame["decision_date_dt"].notna()]


def score_timing(
    *,
    authority: str,
    units: float | None,
    description: str,
    received_date: pd.Timestamp,
    register: pd.DataFrame | None = None,
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = artifact or load_artifact()
    register = register if register is not None else _register_durations()

    description_lower = str(description or "").lower()
    type_apartment = int(bool(pd.Series([description_lower]).str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).iloc[0]))
    type_house = int(bool(pd.Series([description_lower]).str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True).iloc[0] and not type_apartment))

    congestion = _congestion_features(register, authority, received_date)
    row = {
        "log_units": float(np.log1p(units if units else 0)),
        "type_apartment": type_apartment,
        "type_house": type_house,
        "received_year": float(received_date.year),
        "received_month": float(received_date.month),
        "auth_prior_90d_count": np.log1p(congestion["auth_prior_90d_count"]),
        "auth_prior_180d_median_duration": np.log1p(congestion["auth_prior_180d_median_duration"]),
    }
    columns = artifact["feature_columns"]
    frame = pd.DataFrame([{column: row.get(column, 0.0) for column in columns}])
    frame[f"authority_{authority}"] = 1.0

    predictions: dict[str, Any] = {}
    for quantile, model in artifact["models"].items():
        predictions[quantile] = float(np.maximum(model.predict(frame)[0], 1.0))
    result = {
        "model_version": artifact["model_version"],
        "P20_days": round(predictions["0.2"], 0),
        "P50_days": round(predictions["0.5"], 0),
        "P80_days": round(predictions["0.8"], 0),
        "clock_origin": "submission (ReceivedDate)",
        "event": "local-authority decision",
    }
    if "horizon_models" in artifact:
        result["horizon_probabilities"] = {
            str(horizon): float(np.clip(model.predict_proba(frame)[:, 1][0], 1e-6, 1 - 1e-6))
            for horizon, model in artifact["horizon_models"].items()
        }
    return result


def explain_timing(
    *,
    authority: str,
    units: float | None,
    description: str,
    received_date: pd.Timestamp,
    artifact: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Feature-importance driver table for the P50 model."""
    artifact = artifact or load_artifact()
    model = artifact["models"]["0.5"]
    importances = model.feature_importances_
    columns = artifact["feature_columns"]
    description_lower = str(description or "").lower()
    type_apartment = int(bool(pd.Series([description_lower]).str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).iloc[0]))
    subject = {
        "log_units": float(np.log1p(units if units else 0)),
        "type_apartment": type_apartment,
        "received_year": float(received_date.year),
        "received_month": float(received_date.month),
        f"authority_{authority}": 1.0,
    }
    rows = []
    for column, importance in sorted(zip(columns, importances, strict=False), key=lambda kv: -kv[1]):
        if importance < 1e-4:
            continue
        value = subject.get(column, 0.0)
        if column == "auth_prior_90d_count":
            value = round(float(np.expm1(value)), 0)
        elif column == "auth_prior_180d_median_duration":
            value = round(float(np.expm1(value)), 0)
        rows.append({
            "feature": column,
            "importance": round(float(importance), 5),
            "subject_value": round(float(value), 2),
        })
    return rows[:12]
