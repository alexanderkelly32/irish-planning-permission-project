#!/usr/bin/env python3
"""Calibration shootout + conformal per-development intervals.

Variants fitted on the 2023 calibration window (or 2022-2023), evaluated on
2024-2025:
  platt, isotonic (current), isotonic 2022-23, binned-isotonic (50 bins),
  beta calibration, platt+isotonic average.

Also builds a split-conformal 90% interval for individual developments
(nonconformity = |y - p_hat| on the calibration window; finite-sample coverage).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"
CAL_CUTOFF = pd.Timestamp("2023-01-01", tz="UTC")
CAL_CUTOFF_2Y = pd.Timestamp("2022-01-01", tz="UTC")


def platt_fit(p: np.ndarray, y: np.ndarray) -> LogisticRegression:
    s = np.clip(p, 1e-6, 1 - 1e-6)
    return LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000).fit(np.log(s / (1 - s)).reshape(-1, 1), y)


def platt_apply(cal, p: np.ndarray) -> np.ndarray:
    s = np.clip(p, 1e-6, 1 - 1e-6)
    return cal.predict_proba(np.log(s / (1 - s)).reshape(-1, 1))[:, 1]


def beta_fit(p: np.ndarray, y: np.ndarray):
    s = np.clip(p, 1e-6, 1 - 1e-6)

    def nll(params):
        a, b, m = np.exp(params)
        t = m * (s ** a) / ((1 - s) ** b)
        q = t / (1 + t)
        q = np.clip(q, 1e-6, 1 - 1e-6)
        return -np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))

    best = minimize(nll, np.zeros(3), method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-6})
    return best


def beta_apply(fit, p: np.ndarray) -> np.ndarray:
    s = np.clip(p, 1e-6, 1 - 1e-6)
    a, b, m = np.exp(fit.x)
    t = m * (s ** a) / ((1 - s) ** b)
    q = t / (1 + t)
    return np.clip(q, 1e-6, 1 - 1e-6)


def binned_isotonic_fit(p: np.ndarray, y: np.ndarray, n_bins: int = 50):
    quantiles = np.quantile(p, np.linspace(0, 1, n_bins + 1))
    centres = []
    rates = []
    counts = []
    for i in range(n_bins):
        mask = (p >= quantiles[i]) & (p <= quantiles[i + 1])
        if mask.sum() < 5:
            continue
        centres.append(p[mask].mean())
        rates.append(y[mask].mean())
        counts.append(mask.sum())
    centres = np.array(centres)
    rates = np.array(rates)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(centres, rates, sample_weight=np.array(counts))
    return iso


def band_table(p: np.ndarray, y: np.ndarray) -> dict:
    edges = np.linspace(0, 1, 11)
    rows = []
    for i in range(10):
        mask = (p >= edges[i]) & (p < edges[i + 1])
        n = int(mask.sum())
        if n == 0:
            continue
        rows.append({"band": f"{edges[i]:.1f}-{edges[i+1]:.1f}", "n": n, "pred": round(float(p[mask].mean()), 4), "obs": round(float(y[mask].mean()), 4), "error_pp": round(float((p[mask].mean() - y[mask].mean()) * 100), 2)})
    return rows


def main() -> None:
    data, train, test, y = build_data()
    artifact = joblib.load(ARTIFACT)
    calibrated_base = artifact["calibrated_base_model"]
    cal1 = data[(data["received_date_dt"] >= CAL_CUTOFF) & (data["received_date_dt"] < CUTOFF)].copy()
    cal2 = data[(data["received_date_dt"] >= CAL_CUTOFF_2Y) & (data["received_date_dt"] < CUTOFF)].copy()
    test = test.copy()

    s1 = calibrated_base.predict_proba(cal1[artifact["feature_columns"]])[:, 1]
    y1 = cal1["target_refused"].to_numpy()
    s2 = calibrated_base.predict_proba(cal2[artifact["feature_columns"]])[:, 1]
    y2 = cal2["target_refused"].to_numpy()
    st = calibrated_base.predict_proba(test[artifact["feature_columns"]])[:, 1]
    yt = test["target_refused"].to_numpy()

    variants = {}
    platt1 = platt_fit(s1, y1)
    variants["platt_2023"] = platt_apply(platt1, st)
    iso1 = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(s1, y1)
    variants["isotonic_2023_current"] = iso1.predict(st)
    iso2 = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(s2, y2)
    variants["isotonic_2022_23"] = iso2.predict(st)
    bin_iso = binned_isotonic_fit(s1, y1)
    variants["binned_isotonic_50"] = bin_iso.predict(st)
    beta = beta_fit(s1, y1)
    variants["beta"] = beta_apply(beta, st)
    variants["platt_iso_avg"] = 0.5 * variants["platt_2023"] + 0.5 * variants["isotonic_2023_current"]

    results: dict[str, object] = {}
    for name, p in variants.items():
        rows = band_table(p, yt)
        ece = float(np.sum([r["n"] * abs(r["error_pp"]) for r in rows]) / len(yt))
        max_error = max((abs(r["error_pp"]) for r in rows if r["n"] >= 100), default=0.0)
        results[name] = {
            "brier": round(float(brier_score_loss(yt, np.clip(p, 1e-6, 1 - 1e-6))), 5),
            "log_loss": round(float(log_loss(yt, np.clip(p, 1e-6, 1 - 1e-6))), 5),
            "ece_pp": round(ece, 3),
            "max_band_error_pp_n100": round(max_error, 2),
        }

    conformal_q90 = float(np.quantile(np.abs(iso1.predict(s1) - y1), 0.90))
    conformal_q95 = float(np.quantile(np.abs(iso1.predict(s1) - y1), 0.95))

    best_name = min(results, key=lambda k: results[k]["ece_pp"])
    (OUT / "calibration_shootout.json").write_text(json.dumps({
        "variants": results,
        "best_by_ece": best_name,
        "conformal": {"q90": round(conformal_q90, 4), "q95": round(conformal_q95, 4), "method": "split-conformal, |y-p| nonconformity, fitted on 2023"},
        "bands_current": band_table(variants["isotonic_2023_current"], yt),
        "bands_best": band_table(variants[best_name], yt),
    }, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print("best:", best_name)
    print("conformal q90:", round(conformal_q90, 4), "q95:", round(conformal_q95, 4))
    print("best band table:")
    for r in band_table(variants[best_name], yt):
        print(f"  {r['band']:>8} n={r['n']:>6} pred {r['pred']*100:5.1f}% obs {r['obs']*100:5.1f}% err {r['error_pp']:+.1f}pp")


if __name__ == "__main__":
    main()
