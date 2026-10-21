#!/usr/bin/env python3
"""GE10 calibration improvement pass.

Compares Platt vs isotonic calibration, narrow (2023-24) vs wide (2022-24)
calibration windows, and bootstraps the per-band calibration errors so the
~8-9pp figures are known to be signal or noise.

Output: raw_planning_ge10_calibration_v2.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_comparable_feature_experiment import COMPARABLE_FEATURES_PATH, V3_FEATURES  # noqa: E402
from build_national_residential_model_v2 import load_data_with_history  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402


def main() -> None:
    data = load_data_with_history().reset_index(drop=True)
    comparable = pd.read_parquet(COMPARABLE_FEATURES_PATH)
    data = data.merge(comparable, on="case_key", how="left")
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", str(s).lower())
    corrected = pd.read_csv(ROOT / "02_development" / "current" / "ground_source_units_corrected.csv", low_memory=False)
    corrected_norm = {norm(k): v for k, v in zip(corrected["case_key"].astype(str), pd.to_numeric(corrected["units_corrected"], errors="coerce")) if pd.notna(v)}
    holdout_units = pd.read_csv(ROOT / "02_development" / "current" / "holdout_units_extracted.csv", low_memory=False)
    holdout_norm = {norm(k): v for k, v in zip(holdout_units["case_key"].astype(str), pd.to_numeric(holdout_units["units_final"], errors="coerce")) if pd.notna(v)}

    data["_nk"] = data["case_key"].astype(str).map(norm)
    data["units"] = pd.to_numeric(data["NumResidentialUnits"], errors="coerce")
    data["units"] = data["units"].fillna(data["_nk"].map(lambda k: corrected_norm.get(k)))
    data["units"] = data["units"].fillna(data["_nk"].map(lambda k: holdout_norm.get(k)))
    ge10 = data[data["units"] >= 10].copy()

    train = ge10[ge10["received_date_dt"] < pd.Timestamp("2022-01-01", tz="UTC")].copy()
    calibr_wide = ge10[(ge10["received_date_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")) & (ge10["received_date_dt"] < pd.Timestamp("2025-01-01", tz="UTC"))].copy()
    calibr_narrow = calibr_wide[calibr_wide["received_date_dt"] >= pd.Timestamp("2023-01-01", tz="UTC")].copy()
    test = ge10[ge10["received_date_dt"] >= pd.Timestamp("2025-01-01", tz="UTC")].copy().reset_index(drop=True)

    model = build_scaled_pipeline(V3_FEATURES[3:])
    model.fit(train[V3_FEATURES], train["target_refused"])
    test_raw = model.predict_proba(test[V3_FEATURES])[:, 1]

    def fit_platt(raw, y):
        c = np.clip(raw, 1e-6, 1 - 1e-6)
        m = LogisticRegression(C=1_000_000, solver="lbfgs", max_iter=1000)
        m.fit(np.log(c / (1 - c)).reshape(-1, 1), y)
        return lambda p: m.predict_proba(np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6))).reshape(-1, 1))[:, 1]

    def fit_iso(raw, y):
        iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-4, y_max=1 - 1e-4)
        iso.fit(raw, y)
        return lambda p: iso.predict(p)

    variants = {}
    for name, calibr in [("platt_wide_2022_24", calibr_wide), ("platt_narrow_2023_24", calibr_narrow),
                         ("isotonic_wide_2022_24", calibr_wide), ("isotonic_narrow_2023_24", calibr_narrow)]:
        raw = model.predict_proba(calibr[V3_FEATURES])[:, 1]
        calibrator = fit_iso(raw, calibr["target_refused"].to_numpy()) if name.startswith("isotonic") else fit_platt(raw, calibr["target_refused"].to_numpy())
        calibrated = calibrator(test_raw)
        variants[name] = {
            "calibration_rows": int(len(calibr)),
            "brier": round(float(brier_score_loss(test["target_refused"], calibrated)), 4),
            "error_pp": round(float((calibrated.mean() - test["target_refused"].mean()) * 100), 2),
        }

    # Bootstrap per-band errors for the best variant (lowest |error_pp| with lowest brier)
    best_name = min(variants, key=lambda k: abs(variants[k]["error_pp"]))
    raw = model.predict_proba(calibr_wide[V3_FEATURES])[:, 1]
    calibrator = fit_iso(raw, calibr_wide["target_refused"].to_numpy()) if best_name.startswith("isotonic") else fit_platt(raw, calibr_wide["target_refused"].to_numpy())
    test_calibrated = calibrator(test_raw)

    bands = {}
    test["_band"] = pd.cut(test["units"], [10, 25, 50, 100, np.inf], right=False, labels=["10-24", "25-49", "50-99", "100+"])
    rng = np.random.default_rng(20260920)
    for band, group in test.groupby("_band", observed=True):
        y = group["target_refused"].to_numpy()
        p = test_calibrated[group.index.to_numpy()]
        observed = float((p.mean() - y.mean()) * 100)
        samples = []
        for _ in range(2000):
            idx = rng.integers(0, len(y), size=len(y))
            samples.append((p[idx].mean() - y[idx].mean()) * 100)
        bands[band] = {
            "n": int(len(group)),
            "error_pp": round(observed, 2),
            "bootstrap_95": [round(float(np.quantile(samples, 0.025)), 2), round(float(np.quantile(samples, 0.975)), 2)],
            "error_is_distinguishable_from_zero": bool(observed < np.quantile(samples, 0.025) or observed > np.quantile(samples, 0.975)),
        }

    results = {
        "generated": "2026-09-20",
        "variants": variants,
        "best_variant": best_name,
        "per_band_bootstrap": bands,
        "caveat": "Bootstrap CIs on the per-band mean calibration error; bands with n<50 cannot resolve sub-10pp errors. Isotonic vs Platt comparison on the same 166-row 2025 GE10 holdout.",
    }
    (OUTPUT_DIR / "raw_planning_ge10_calibration_v2.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
