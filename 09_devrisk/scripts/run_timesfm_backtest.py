"""Runner: TimesFM-3.0 zero-shot backtest on authority-level decision-duration series.

Series: monthly median decision duration per authority (all residential
decisions), 2017-2024 for context, 2025 (12 months) as holdout. Baselines:
persistence (last value), seasonal naive (same month last year), context
mean. Metric: MAE over the 12-month holdout, per series and pooled.

LICENCE: TimesFM 3.0 is released under the TimesFM Non-Commercial License
v1.0. This evaluation is research-only; commercial use requires a licence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

HORIZON = 12
CONTEXT = 60


def build_series() -> dict[str, np.ndarray]:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = register.copy()
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["decision_dt"] = pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce")
    frame["duration"] = (frame["decision_dt"] - frame["received_dt"]).dt.days
    frame = frame[frame["duration"].between(0, 1095) & frame["decision_dt"].notna()]
    frame["month"] = frame["decision_dt"].dt.to_period("M")
    series = {}
    for authority, group in frame.groupby("PlanningAuthority"):
        monthly = group.groupby("month")["duration"].median()
        monthly.index = monthly.index.to_timestamp()
        monthly = monthly.resample("MS").asfreq()
        if monthly.notna().sum() < CONTEXT + HORIZON:
            continue
        series[str(authority)] = monthly.to_numpy(dtype=float)
    return series


def backtest(series: dict[str, np.ndarray]) -> dict:
    results = {}
    for name, values in series.items():
        values = np.asarray(values, dtype=float)
        context = values[-(CONTEXT + HORIZON):-HORIZON]
        actual = values[-HORIZON:]
        if np.isnan(context).any() or np.isnan(actual).any():
            continue
        forecasts = {
            "persistence": np.full(HORIZON, context[-1]),
            "seasonal_naive": context[-12:],
            "context_mean": np.full(HORIZON, context.mean()),
        }
        metrics = {}
        for method, prediction in forecasts.items():
            metrics[method] = round(float(np.mean(np.abs(actual - prediction))), 2)
        results[name] = {"actual": actual.round(1).tolist(), "baselines": metrics}
    return results


if __name__ == "__main__":
    series = build_series()
    print(f"series built: {len(series)} authorities", flush=True)
    baseline_results = backtest(series)

    from timesfm import TimesFM3Forecaster

    forecaster = TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch", device="cpu")
    print("TimesFM-3.0 loaded", flush=True)

    timesfm_results = {}
    for name, values in series.items():
        context = values[-(CONTEXT + HORIZON):-HORIZON]
        actual = values[-HORIZON:]
        if np.isnan(context).any() or np.isnan(actual).any():
            continue
        try:
            output = forecaster.predict(np.asarray(context, dtype=float).reshape(1, -1), horizon=HORIZON)
            prediction = np.asarray(output.forecast).ravel()[:HORIZON]
        except Exception as error:  # noqa: BLE001
            timesfm_results[name] = {"error": f"{type(error).__name__}: {str(error)[:150]}"}
            continue
        timesfm_results[name] = {
            "mae": round(float(np.mean(np.abs(actual - prediction))), 2),
            "actual": actual.round(1).tolist(),
            "forecast": prediction.round(1).tolist(),
        }

    pooled = {"baselines": {"persistence": [], "seasonal_naive": [], "context_mean": []}, "timesfm": []}
    for name, entry in baseline_results.items():
        for method in pooled["baselines"]:
            pooled["baselines"][method].append(entry["baselines"][method])
        if "mae" in timesfm_results.get(name, {}):
            pooled["timesfm"].append(timesfm_results[name]["mae"])
    summary = {
        "n_series": int(len(pooled["timesfm"])),
        "pooled_mae": {
            **{method: round(float(np.mean(values)), 2) for method, values in pooled["baselines"].items()},
            "timesfm3": round(float(np.mean(pooled["timesfm"])), 2) if pooled["timesfm"] else None,
        },
        "timesfm_beats_persistence": int(sum(
            1 for name in baseline_results if timesfm_results.get(name, {}).get("mae", 1e9) < baseline_results[name]["baselines"]["persistence"]
        )),
        "timesfm_beats_seasonal": int(sum(
            1 for name in baseline_results if timesfm_results.get(name, {}).get("mae", 1e9) < baseline_results[name]["baselines"]["seasonal_naive"]
        )),
        "licence_note": "TimesFM 3.0 Non-Commercial License v1.0 - research evaluation only",
    }
    out = settings.SILVER_DIR / "timesfm_backtest.json"
    out.write_text(json.dumps({"summary": summary, "baselines": baseline_results, "timesfm": timesfm_results}, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2))
