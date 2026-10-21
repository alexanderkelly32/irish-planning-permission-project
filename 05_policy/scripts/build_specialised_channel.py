#!/usr/bin/env python3
"""Specialised-scheme channel: senior living, retirement villages, care homes.

1) Population: how many specialised GE10 schemes exist, their real refusal rate.
2) Current model errors on them.
3) Fix: a specialised recalibrator (isotonic fitted on 2023 specialised cases)
   + a challenger with an explicit specialised feature. Measured on the holdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_v3_text_encoder_experiment import build_pipeline  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"
CAL_CUTOFF = pd.Timestamp("2023-01-01", tz="UTC")

SPECIALISED_RE = r"(senior\s*living|retirement\s*village|nursing\s*home|care\s*home|assisted\s*living|sheltered|community\s*dwelling|residential\s*care|independent\s*living|retirement\s*home|elderly|continuing\s*care)"


def is_specialised(text: str) -> bool:
    return bool(pd.notna(text) and __import__("re").search(SPECIALISED_RE, str(text), __import__("re").IGNORECASE))


def main() -> None:
    data, train, test, y = build_data()
    train["specialised"] = train["description_stripped"].map(is_specialised).astype(int)
    test["specialised"] = test["description_stripped"].map(is_specialised).astype(int)

    ge10_train = train[train["units"] >= 10].copy()
    ge10_test = test[test["units"] >= 10].copy()
    spec_train = ge10_train[ge10_train["specialised"] == 1]
    spec_test = ge10_test[ge10_test["specialised"] == 1]
    print(f"specialised GE10: train {len(spec_train)} | test {len(spec_test)}", flush=True)
    if len(spec_test):
        print(f"specialised test refusal rate: {spec_test['target_refused'].mean():.3f} (n={len(spec_test)})", flush=True)

    artifact = joblib.load(ARTIFACT)
    ranking = artifact["ranking_model"]
    calibrated_base = artifact["calibrated_base_model"]
    global_iso = artifact["isotonic_calibrator"]

    spec_test = spec_test.copy()
    spec_test["risk_raw"] = ranking.predict_proba(spec_test[artifact["feature_columns"]])[:, 1]
    spec_test["risk_global_iso"] = global_iso.predict(calibrated_base.predict_proba(spec_test[artifact["feature_columns"]])[:, 1])

    cal_window = data[(data["received_date_dt"] >= CAL_CUTOFF) & (data["received_date_dt"] < CUTOFF)]
    cal_window["specialised"] = cal_window["description_stripped"].map(is_specialised).astype(int)
    spec_cal = cal_window[(cal_window["specialised"] == 1) & (cal_window["units"] >= 10)]
    print(f"specialised calibration window (2023, GE10): {len(spec_cal)}", flush=True)

    results: dict[str, object] = {
        "specialised_population": {"train_ge10": int(len(spec_train)), "test_ge10": int(len(spec_test)), "cal_window": int(len(spec_cal))},
    }

    if len(spec_test) >= 5 and spec_test["target_refused"].nunique() == 2:
        results["current_model_on_specialised"] = {
            "n": int(len(spec_test)),
            "refusal_rate": round(float(spec_test["target_refused"].mean()), 4),
            "ranking_auc": round(float(roc_auc_score(spec_test["target_refused"], spec_test["risk_raw"])), 4),
            "global_iso_brier": round(float(brier_score_loss(spec_test["target_refused"], np.clip(spec_test["risk_global_iso"], 1e-6, 1 - 1e-6))), 4),
        }

    spec_iso_brier = None
    spec_train_all = ge10_train[ge10_train["specialised"] == 1].copy()
    spec_train_all["base"] = calibrated_base.predict_proba(spec_train_all[artifact["feature_columns"]])[:, 1]
    spec_train_all["global_iso"] = global_iso.predict(spec_train_all["base"])
    obs = float(spec_train_all["target_refused"].mean())
    pred = float(np.clip(spec_train_all["global_iso"], 1e-6, 1 - 1e-6).mean())
    logit = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    raw_shift = logit(obs) - logit(pred)
    shrinkage = min(1.0, len(spec_train_all) / 200.0)
    shift = raw_shift * shrinkage
    results["specialised_prior_shift"] = {
        "n_pre_2024": int(len(spec_train_all)),
        "observed_rate": round(obs, 4),
        "global_model_mean": round(pred, 4),
        "raw_logit_shift": round(float(raw_shift), 4),
        "applied_logit_shift": round(float(shift), 4),
        "shrinkage": round(shrinkage, 3),
    }
    if len(spec_test) >= 5:
        spec_test["risk_spec_shifted"] = 1 / (1 + np.exp(-(logit(spec_test["risk_global_iso"]) + shift)))
        shifted_brier = float(brier_score_loss(spec_test["target_refused"], np.clip(spec_test["risk_spec_shifted"], 1e-6, 1 - 1e-6)))
        results["specialised_recalibrated"] = {
            "brier_after_shift": round(shifted_brier, 4),
            "brier_before_shift": round(results["current_model_on_specialised"]["global_iso_brier"], 4),
            "improvement": round(results["current_model_on_specialised"]["global_iso_brier"] - shifted_brier, 4),
            "mean_risk_after": round(float(spec_test["risk_spec_shifted"].mean()), 4),
        }
    joblib.dump({"logit_shift": float(shift), "n": int(len(spec_train_all)), "observed_rate": obs}, ROOT / "05_policy" / "current" / "model_v4" / "specialised_adjustment.joblib")

    base_extras = [
        "log_units", "log_site_area_sqm", "log_floor_area_sqm", "units_missing",
        "applicant_prior_count", "applicant_prior_refusal_rate",
        *pc.FLOOD_FEATURES, "flood_any",
    ]
    policy_extras = [
        "log_plan_unique_codes", "log_plan_mentions", "policy_plan_covered",
        *[f"plan_theme_{t}" for t in pc.THEME_ORDER], "plan_theme_other",
        "log_plan_codes_match_desc",
    ]
    ratio_extras = [
        "density_units_per_ha", "floor_area_ratio", "site_sqm_per_unit", "avg_unit_floor_sqm",
        "density_band_low", "density_band_mid", "density_band_high", "density_over_45", "density_missing",
        "landuse_new_house", "landuse_housing_new", "landuse_extension", "landuse_retention", "landuse_missing",
    ]
    context_extras = [
        "log_pop_density", "owner_share", "private_rent_share", "la_rent_share",
        "septic_share", "cars_per_hh", "no_car_share",
        "log_national_road_dist", "national_roads_within_1km", "is_urban",
    ]
    extras = base_extras + policy_extras + ratio_extras + context_extras + ["specialised"]
    numeric = V3_FEATURES[3:] + extras
    features = V3_FEATURES + extras

    from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402

    w13_steps = [("w13", TfidfVectorizer(stop_words="english", ngram_range=(1, 3), max_features=50000, min_df=2))]
    print("fitting challenger with specialised feature...", flush=True)
    pipeline = build_pipeline(numeric, w13_steps)
    pipeline.fit(train[features], train["target_refused"])
    p_test = pipeline.predict_proba(test[features])[:, 1]
    results["challenger_with_specialised_feature"] = {
        "holdout_auc": round(float(roc_auc_score(y, p_test)), 4),
    }
    ge10_mask = (test["units"] >= 10).to_numpy()
    if ge10_mask.sum() >= 20:
        results["challenger_with_specialised_feature"]["ge10_auc"] = round(float(roc_auc_score(y[ge10_mask], p_test[ge10_mask])), 4)
    spec_mask = (test["specialised"] == 1).to_numpy()
    if spec_mask.sum() >= 5 and y[spec_mask].nunique() == 2:
        results["challenger_with_specialised_feature"]["specialised_subset_auc"] = round(float(roc_auc_score(y[spec_mask], p_test[spec_mask])), 4)

    (OUT / "specialised_channel_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
