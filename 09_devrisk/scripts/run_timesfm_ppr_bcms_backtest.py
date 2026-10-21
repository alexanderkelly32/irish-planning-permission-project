"""Runner: TimesFM-3.0 zero-shot backtest on PPR volumes/prices and BCMS commencements.

Series:
  - PPR monthly transaction count per county (2010-2025)
  - PPR monthly median price per county
  - BCMS monthly commencement count per county (2014-2025)

Holdout: last 12 months. Baselines: persistence, seasonal naive, context mean.
Research-only (TimesFM Non-Commercial License v1.0).
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
CONTEXT = 96  # 8 years of context


def monthly_series(frame: pd.DataFrame, group_col: str, date_col: str, value_col: str | None = None) -> dict[str, np.ndarray]:
    frame = frame.copy()
    frame["month"] = pd.to_datetime(frame[date_col], utc=True, errors="coerce").dt.to_period("M")
    frame = frame[frame["month"].notna()]
    out = {}
    for key, group in frame.groupby(group_col):
        if value_col is None:
            monthly = group.groupby("month").size()
        else:
            monthly = group.groupby("month")[value_col].median()
        monthly.index = monthly.index.to_timestamp()
        monthly = monthly.resample("MS").asfreq()
        if monthly.notna().sum() < CONTEXT + HORIZON:
            continue
        out[str(key)] = monthly.to_numpy(dtype=float)
    return out


def evaluate(series: dict[str, np.ndarray], forecaster, label: str) -> dict:
    baseline_results = {}
    timesfm_results = {}
    for name, values in series.items():
        values = np.asarray(values, dtype=float)
        context = values[-(CONTEXT + HORIZON):-HORIZON]
        actual = values[-HORIZON:]
        if np.isnan(context).any() or np.isnan(actual).any():
            continue
        baseline_results[name] = {
            "persistence": round(float(np.mean(np.abs(actual - context[-1]))), 2),
            "seasonal_naive": round(float(np.mean(np.abs(actual - context[-12:]))), 2),
            "context_mean": round(float(np.mean(np.abs(actual - context.mean()))), 2),
        }
        try:
            output = forecaster.predict(np.asarray(context, dtype=float).reshape(1, -1), horizon=HORIZON)
            prediction = np.asarray(output.forecast).ravel()[:HORIZON]
            timesfm_results[name] = round(float(np.mean(np.abs(actual - prediction))), 2)
        except Exception as error:  # noqa: BLE001
            timesfm_results[name] = None

    pooled = {"persistence": [], "seasonal_naive": [], "context_mean": [], "timesfm3": []}
    for name in baseline_results:
        for method in ("persistence", "seasonal_naive", "context_mean"):
            pooled[method].append(baseline_results[name][method])
        if timesfm_results.get(name) is not None:
            pooled["timesfm3"].append(timesfm_results[name])
    return {
        "target": label,
        "n_series": int(len(pooled["timesfm3"])),
        "pooled_mae": {method: round(float(np.mean(values)), 2) for method, values in pooled.items()},
        "timesfm_beats_persistence": int(sum(
            1 for name in baseline_results
            if timesfm_results.get(name) is not None and timesfm_results[name] < baseline_results[name]["persistence"]
        )),
        "timesfm_beats_seasonal": int(sum(
            1 for name in baseline_results
            if timesfm_results.get(name) is not None and timesfm_results[name] < baseline_results[name]["seasonal_naive"]
        )),
    }


if __name__ == "__main__":
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms = bcms[bcms["commencement_date_dt"].notna()]

    targets = {
        "ppr_county_monthly_volume": monthly_series(ppr, "county_norm", "sale_date_dt"),
        "ppr_county_monthly_median_price": monthly_series(ppr, "county_norm", "sale_date_dt", "price_num"),
        "bcms_county_monthly_commencements": monthly_series(bcms, "county", "commencement_date_dt"),
    }
    for name, series in targets.items():
        print(f"{name}: {len(series)} series", flush=True)

    from timesfm import TimesFM3Forecaster

    forecaster = TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch", device="cpu")
    print("TimesFM-3.0 loaded", flush=True)

    results = []
    for name, series in targets.items():
        entry = evaluate(series, forecaster, name)
        results.append(entry)
        print(json.dumps(entry, indent=1), flush=True)

    out = settings.SILVER_DIR / "timesfm_ppr_bcms_backtest.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
