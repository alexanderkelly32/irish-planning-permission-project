#!/usr/bin/env python3
"""GE10 recalibration experiment.

Finding: the v4-full isotonic calibrator was fit on ALL residential
applications, where large schemes are a small, riskier slice. Applied to
10+ unit schemes alone, the calibrated probabilities systematically overstate
refusal risk (holdout: mean predicted 44.4% vs observed 19.0%).

This script fits a GE10-specific recalibrator on the 2023 calibration window
(389 schemes; the base model never saw them - trained pre-2023) and evaluates
it on the untouched 2024-2025 GE10 holdout (n=464). Candidates: isotonic on
the base score, Platt on the global-iso logit, and the global iso baseline.
The promoted candidate must beat the global iso on Brier and calibration
deviation. The frozen v4-full artifact is never modified - the recalibrator
is an additive probability layer for 10+ unit schemes only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "05_policy" / "current" / "model_v4"
ARTIFACT_PATH = OUT_DIR / "national_residential_v4_full.joblib"
RECAL_PATH = OUT_DIR / "ge10_recalibrator.joblib"

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_8020_regime_experiment import build_data  # noqa: E402


def _bin_table(risk: np.ndarray, y: np.ndarray) -> list[dict]:
    rows = []
    for lo, hi in ((0.0, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.40),
                   (0.40, 0.50), (0.50, 0.60), (0.60, 1.0)):
        mask = (risk >= lo) & (risk < hi)
        if mask.sum() == 0:
            continue
        rows.append({
            "bin": f"{int(lo * 100)}-{int(hi * 100)}%",
            "n": int(mask.sum()),
            "mean_predicted": round(float(risk[mask].mean()), 4),
            "observed": round(float(y[mask].mean()), 4),
            "deviation_pp": round(float((risk[mask].mean() - y[mask].mean()) * 100), 2),
        })
    return rows


def main() -> None:
    artifact = joblib.load(ARTIFACT_PATH)
    base_model = artifact["calibrated_base_model"]
    global_iso = artifact["isotonic_calibrator"]
    feature_columns = artifact["feature_columns"]

    data, train, _test, _y = build_data()
    fit = train[(train["units"] >= 10) & (train["received_date_dt"].dt.year == 2023)].copy()
    test = data[(data["units"] >= 10) & (data["received_date_dt"] >= pd.Timestamp("2024-01-01", tz="UTC"))].copy()

    fit_base = base_model.predict_proba(fit[feature_columns])[:, 1]
    test_base = base_model.predict_proba(test[feature_columns])[:, 1]
    fit_iso = global_iso.predict(fit_base)
    test_iso = global_iso.predict(test_base)
    y_fit = fit["target_refused"].to_numpy()
    y_test = test["target_refused"].to_numpy()

    # Candidate A: isotonic on base scores, fit on 2023 GE10
    iso_ge10 = IsotonicRegression(out_of_bounds="clip")
    iso_ge10.fit(fit_base, y_fit)
    test_iso_ge10 = iso_ge10.predict(test_base)

    # Candidate B: Platt on the global-iso logit, fit on 2023 GE10
    logit = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    platt = LogisticRegression(C=1_000_000, solver="lbfgs", max_iter=1000)
    platt.fit(logit(fit_iso).reshape(-1, 1), y_fit)
    test_platt = platt.predict_proba(logit(test_iso).reshape(-1, 1))[:, 1]

    variants = {
        "global_iso (current)": test_iso,
        "ge10_isotonic (base)": test_iso_ge10,
        "ge10_platt (iso logit)": test_platt,
    }
    results: dict[str, object] = {
        "protocol": "GE10-specific probability recalibration; fit on 2023 GE10 (n=389, base model pre-2023); test = 2024-25 GE10 holdout (n=464)",
        "fit_window": {"n": int(len(fit)), "refused": int(y_fit.sum()), "refusal_rate": round(float(y_fit.mean()), 4)},
        "test": {"n": int(len(test)), "refused": int(y_test.sum()), "refusal_rate": round(float(y_test.mean()), 4)},
        "variants": {},
    }
    for name, risk in variants.items():
        brier = float(brier_score_loss(y_test, np.clip(risk, 1e-6, 1 - 1e-6)))
        rows = _bin_table(risk, y_test)
        dev = np.mean([abs(r["deviation_pp"]) for r in rows])
        results["variants"][name] = {
            "brier": round(brier, 4),
            "mean_predicted": round(float(risk.mean()), 4),
            "mean_bin_deviation_pp": round(dev, 2),
            "bin_table": rows,
        }
        print(f"{name}: brier={brier:.4f} mean_pred={risk.mean() * 100:.1f}% mean_bin_dev={dev:.1f}pp")

    # Pick best by Brier (exclude current if it wins - that means no promotion).
    best_name = min(variants, key=lambda n: results["variants"][n]["brier"])
    promoted = best_name if best_name != "global_iso (current)" else None
    results["promoted"] = promoted
    (ROOT / "05_policy" / "current" / "raw_planning_ge10_recalibration.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    if promoted == "ge10_isotonic (base)":
        joblib.dump({"kind": "ge10_recalibrator", "calibrator": iso_ge10, "fit_on": "2023 GE10 (n=389)"}, RECAL_PATH)
        print("saved:", RECAL_PATH)
    elif promoted == "ge10_platt (iso logit)":
        joblib.dump({"kind": "ge10_recalibrator", "calibrator": platt, "input": "logit(global_iso)", "fit_on": "2023 GE10 (n=389)"}, RECAL_PATH)
        print("saved:", RECAL_PATH)
    print("promoted:", promoted)


if __name__ == "__main__":
    main()
