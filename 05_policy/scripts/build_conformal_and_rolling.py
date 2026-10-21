#!/usr/bin/env python3
"""Mondrian conformal per-development intervals + rolling-calibration test.

- Mondrian: split the 2023 window into 10 bands by predicted p; per band take
  the 90% quantile of |y - p|; at query use the scheme's own band quantile.
- Rolling: calibrate on trailing 12 months, evaluate on the following 6 months,
  walked through 2024-2025 (time-series validation of a fresher calibrator).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


def band_index(p) -> np.ndarray:
    return np.minimum(9, (p * 10).astype(int))


def main() -> None:
    data, train, test, y = build_data()
    artifact = joblib.load(ARTIFACT)
    calibrated_base = artifact["calibrated_base_model"]
    cal = data[(data["received_date_dt"] >= "2023-01-01") & (data["received_date_dt"] < CUTOFF)].copy()
    test = test.copy()
    s_cal = calibrated_base.predict_proba(cal[artifact["feature_columns"]])[:, 1]
    y_cal = cal["target_refused"].to_numpy()
    s_test = calibrated_base.predict_proba(test[artifact["feature_columns"]])[:, 1]
    y_test = test["target_refused"].to_numpy()

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(s_cal, y_cal)
    p_cal = iso.predict(s_cal)
    p_test = iso.predict(s_test)

    band_quantiles = {}
    for b in range(10):
        mask = (band_index(p_cal) == b)
        if mask.sum() >= 20:
            band_quantiles[b] = float(np.quantile(np.abs(p_cal[mask] - y_cal[mask]), 0.90))
        else:
            band_quantiles[b] = float(np.quantile(np.abs(p_cal - y_cal), 0.90))
    intervals = np.array([[max(0.0, p - band_quantiles[band_index(p)]), min(1.0, p + band_quantiles[band_index(p)])] for p in p_test])
    widths = intervals[:, 1] - intervals[:, 0]
    coverage = np.mean((y_test >= intervals[:, 0]) & (y_test <= intervals[:, 1]))
    print(f"mondrian 90% conformal: coverage={coverage:.3f}, median width={np.median(widths) * 100:.1f}pp", flush=True)
    width_by_band = {}
    for b in range(10):
        mask = np.array([band_index(p) for p in p_test]) == b
        if mask.sum() >= 20:
            width_by_band[f"{b*10}-{(b+1)*10}%"] = {"n": int(mask.sum()), "median_width_pp": round(float(np.median(widths[mask]) * 100), 1), "q": round(band_quantiles[b] * 100, 1)}

    rolling = []
    for start in pd.date_range("2024-01-01", "2025-01-01", freq="6MS", tz="UTC"):
        cal_window = data[(data["received_date_dt"] >= start - pd.DateOffset(months=12)) & (data["received_date_dt"] < start)]
        eval_window = data[(data["received_date_dt"] >= start) & (data["received_date_dt"] < start + pd.DateOffset(months=6))]
        if len(cal_window) < 500 or len(eval_window) < 300:
            continue
        s_c = calibrated_base.predict_proba(cal_window[artifact["feature_columns"]])[:, 1]
        y_c = cal_window["target_refused"].to_numpy()
        s_e = calibrated_base.predict_proba(eval_window[artifact["feature_columns"]])[:, 1]
        y_e = eval_window["target_refused"].to_numpy()
        rolling_iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(s_c, y_c)
        p_e = rolling_iso.predict(s_e)
        frozen = iso.predict(s_e)
        rolling.append({
            "eval_period": f"{start:%Y-%m} to {start + pd.DateOffset(months=6):%Y-%m}",
            "n": int(len(y_e)),
            "frozen_2023_brier": round(float(brier_score_loss(y_e, np.clip(frozen, 1e-6, 1 - 1e-6))), 5),
            "rolling_12m_brier": round(float(brier_score_loss(y_e, np.clip(p_e, 1e-6, 1 - 1e-6))), 5),
        })
    payload = {
        "mondrian_conformal": {"coverage": round(float(coverage), 4), "width_by_band": width_by_band},
        "rolling_vs_frozen": rolling,
    }
    (OUT / "conformal_and_rolling.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
