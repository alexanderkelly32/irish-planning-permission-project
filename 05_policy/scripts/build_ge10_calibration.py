#!/usr/bin/env python3
"""GE10-specific calibration.

Mirrors v3's two-stage discipline but on the >=10-unit universe:
- classifier trained on pre-2023 GE10 rows (same feature matrix as v3)
- Platt calibrator fit on 2023-2024 GE10 raw scores
- applied to the 2025 GE10 holdout

Reports Brier, log loss and calibration error before/after, per band, so the
GE10 probabilities (the number a developer reads) are honest.

Output: raw_planning_ge10_calibration.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

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

    import re
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

    train = ge10[ge10["received_date_dt"] < pd.Timestamp("2023-01-01", tz="UTC")].copy()
    calibr = ge10[(ge10["received_date_dt"] >= pd.Timestamp("2023-01-01", tz="UTC")) & (ge10["received_date_dt"] < pd.Timestamp("2025-01-01", tz="UTC"))].copy()
    test = ge10[ge10["received_date_dt"] >= pd.Timestamp("2025-01-01", tz="UTC")].copy()
    print(f"GE10: train<2023 {len(train)} | calibr 2023-24 {len(calibr)} | test 2025 {len(test)}", flush=True)

    if len(calibr) < 50 or len(test) < 20:
        print(json.dumps({"status": "insufficient_slices", "calibr": len(calibr), "test": len(test)}, indent=2))
        return

    model = build_scaled_pipeline(V3_FEATURES[3:])
    model.fit(train[V3_FEATURES], train["target_refused"])
    calibr_raw = model.predict_proba(calibr[V3_FEATURES])[:, 1]
    test_raw = model.predict_proba(test[V3_FEATURES])[:, 1]

    clipped = np.clip(calibr_raw, 1e-6, 1 - 1e-6)
    platt = LogisticRegression(C=1_000_000, solver="lbfgs", max_iter=1000)
    platt.fit(np.log(clipped / (1 - clipped)).reshape(-1, 1), calibr["target_refused"].to_numpy())

    def apply_platt(p):
        c = np.clip(p, 1e-6, 1 - 1e-6)
        return platt.predict_proba(np.log(c / (1 - c)).reshape(-1, 1))[:, 1]

    test_calibrated = apply_platt(test_raw)
    y = test["target_refused"].to_numpy()
    test = test.reset_index(drop=True)
    test_raw = model.predict_proba(test[V3_FEATURES])[:, 1]
    test_calibrated = apply_platt(test_raw)
    y = test["target_refused"].to_numpy()

    def block(p):
        return {
            "n": int(len(p)),
            "refusal_rate": round(float(y.mean()), 4),
            "brier": round(float(brier_score_loss(y, p)), 4),
            "log_loss": round(float(log_loss(y, p)), 4),
            "calibration_error_pp": round(float((p.mean() - y.mean()) * 100), 2),
        }

    bands = {}
    test = test.copy()
    test["_band"] = pd.cut(test["units"], [10, 25, 50, 100, np.inf], right=False, labels=["10-24", "25-49", "50-99", "100+"])
    for band, group in test.groupby("_band", observed=True):
        if len(group) < 10:
            continue
        bands[band] = {
            "n": int(len(group)),
            "raw_error_pp": round(float((test_raw[group.index].mean() - group["target_refused"].mean()) * 100), 2),
            "calibrated_error_pp": round(float((test_calibrated[group.index].mean() - group["target_refused"].mean()) * 100), 2),
        }

    results = {
        "generated": "2026-09-20",
        "train_early_rows": int(len(train)),
        "calibration_rows_2023_24": int(len(calibr)),
        "test_rows_2025": int(len(test)),
        "raw_scores": block(test_raw),
        "ge10_platt_calibrated": block(test_calibrated),
        "per_band_calibration_error_pp": bands,
        "caveat": "Classifier pre-2023, Platt on 2023-24 GE10, applied to the 2025 GE10 holdout (~166 rows). Small holdout - the calibrated per-band errors are directional.",
    }
    (OUTPUT_DIR / "raw_planning_ge10_calibration.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
