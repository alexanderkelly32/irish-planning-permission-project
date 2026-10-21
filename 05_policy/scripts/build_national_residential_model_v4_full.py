#!/usr/bin/env python3
"""Build national_residential_v4_full - the promoted all-features candidate.

Features: v3 core + flood + units/site/floor numerics + policy layer + register
ratios (density/FAR) + LandUseCode flags + CSO small-area context + trigram
TF-IDF text encoder.

Protocol (80/20 two-track):
  ranking: classifier trained < 2024-01-01, scored on 2024+2025
  calibrated: classifier trained < 2023-01-01, isotonic fitted on 2023

Writes 05_policy/current/model_v4/national_residential_v4_full.joblib + manifest.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
V4_DIR = OUTPUT_DIR / "model_v4"
V4_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_v3_text_encoder_experiment import build_pipeline  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

CAL_CUTOFF = pd.Timestamp("2023-01-01", tz="UTC")


def main() -> None:
    data, train, test, y = build_data()
    cal_window = data[(data["received_date_dt"] >= CAL_CUTOFF) & (data["received_date_dt"] < CUTOFF)].copy()
    train_c = data[data["received_date_dt"] < CAL_CUTOFF].copy()

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
    extras = base_extras + policy_extras + ratio_extras + context_extras
    numeric = V3_FEATURES[3:] + extras
    features = V3_FEATURES + extras
    w13_steps = [("w13", TfidfVectorizer(stop_words="english", ngram_range=(1, 3), max_features=50000, min_df=2))]

    print("fitting ranking model (<2024)...", flush=True)
    ranking = build_pipeline(numeric, w13_steps)
    ranking.fit(train[features], train["target_refused"])
    p_test = ranking.predict_proba(test[features])[:, 1]

    print("fitting calibrated track (<2023) + isotonic on 2023...", flush=True)
    calibrated_base = build_pipeline(numeric, w13_steps)
    calibrated_base.fit(train_c[features], train_c["target_refused"])
    p_cal = calibrated_base.predict_proba(cal_window[features])[:, 1]
    p_test_c = calibrated_base.predict_proba(test[features])[:, 1]
    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p_cal, cal_window["target_refused"].to_numpy())
    iso_cal = isotonic.predict(p_cal)
    iso_test = isotonic.predict(p_test_c)
    band_thresholds = tuple(float(x) for x in np.quantile(iso_cal, [1 / 3, 2 / 3]))

    ge10_mask = (test["units"] >= 10).to_numpy()
    manifest = {
        "model_version": "national_residential_v4_full",
        "status": "candidate",
        "prediction_time": "immediately before submission",
        "feature_columns": features,
        "numeric_features": numeric,
        "text_encoder": "tfidf_word13_stopwords_en_50k",
        "training_cutoff_exclusive": "2024-01-01",
        "calibration_classifier_cutoff_exclusive": "2023-01-01",
        "calibration_window": "2023 calendar year",
        "calibrator": "isotonic_clip_0_1",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "test_period": [str(test["received_date_dt"].min()), str(test["received_date_dt"].max())],
        "ranking_metrics": {
            "roc_auc": round(float(roc_auc_score(y, p_test)), 4),
            "average_precision": round(float(average_precision_score(y, p_test)), 4),
        },
        "calibrated_metrics": {
            "brier": round(float(brier_score_loss(y, np.clip(iso_test, 1e-6, 1 - 1e-6))), 4),
            "log_loss": round(float(log_loss(y, np.clip(iso_test, 1e-6, 1 - 1e-6))), 4),
        },
        "ge10_metrics": {
            "n": int(ge10_mask.sum()),
            "ranking_roc_auc": round(float(roc_auc_score(y[ge10_mask], p_test[ge10_mask])), 4),
            "ranking_ap": round(float(average_precision_score(y[ge10_mask], p_test[ge10_mask])), 4),
            "calibrated_brier": round(float(brier_score_loss(y[ge10_mask], np.clip(iso_test[ge10_mask], 1e-6, 1 - 1e-6))), 4),
        } if ge10_mask.sum() >= 20 else None,
        "by_year": {
            str(year): {
                "n": int(len(group)),
                "roc_auc": round(float(roc_auc_score(group["target_refused"], p_test[group.index])), 4),
                "average_precision": round(float(average_precision_score(group["target_refused"], p_test[group.index])), 4),
            }
            for year, group in test.groupby(test["received_date_dt"].dt.year)
        },
        "risk_band_thresholds": {"low_max": band_thresholds[0], "medium_max": band_thresholds[1]},
        "reference_tables": {
            "sa_reference": "07_context/current/sa_reference.parquet",
            "flood_points": "07_context/current/flood_points.parquet",
            "plan_summary": "07_context/current/plan_summary.parquet",
        },
        "frozen_v3_reference": {"roc_auc_2025": 0.7989, "average_precision_2025": 0.4202},
        "note": "v4-full is the 80/20 two-track candidate. Frozen v3 artifact remains untouched.",
    }
    artifact = {
        "model_version": "national_residential_v4_full",
        "prediction_time": "immediately before submission",
        "feature_columns": features,
        "numeric_features": numeric,
        "ranking_model": ranking,
        "calibrated_base_model": calibrated_base,
        "isotonic_calibrator": isotonic,
        "risk_band_thresholds": {"low_max": band_thresholds[0], "medium_max": band_thresholds[1]},
    }
    joblib.dump(artifact, V4_DIR / "national_residential_v4_full.joblib")
    (V4_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
