#!/usr/bin/env python3
"""Type-code challenger: does parsing SHD house-type structure help?

Adds type-code/bedroom/storey/form parsing features to v4-full and measures:
  - overall + GE10 AUC vs the frozen full model
  - what happens to the 12 'missed refusals' (refused, bottom two quintiles)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_description_lexicon import lexicon_features, type_code_features  # noqa: E402
from build_v3_text_encoder_experiment import build_pipeline  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


def main() -> None:
    data, train, test, y = build_data()
    lex = lexicon_features(data["description_stripped"].fillna(""))
    tparse = type_code_features(data["description_stripped"].fillna(""))
    extra_frame = lex.join(tparse)
    train = train.join(extra_frame)
    test = test.join(extra_frame)

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
    extras = base_extras + policy_extras + ratio_extras + context_extras + list(extra_frame.columns)
    numeric = V3_FEATURES[3:] + extras
    features = V3_FEATURES + extras

    artifact = joblib.load(ARTIFACT)
    full_model = artifact["ranking_model"]
    ge10_test = test[test["units"] >= 10].copy()
    p_full = full_model.predict_proba(ge10_test[artifact["feature_columns"]])[:, 1]
    ge10_test["p_full"] = p_full

    w13_steps = [("w13", TfidfVectorizer(stop_words="english", ngram_range=(1, 3), max_features=50000, min_df=2))]
    print("fitting type-code challenger...", flush=True)
    pipeline = build_pipeline(numeric, w13_steps)
    pipeline.fit(train[features], train["target_refused"])
    p_test = pipeline.predict_proba(test[features])[:, 1]
    p_ge10 = p_test[(test["units"] >= 10).to_numpy()]

    y_ge10 = ge10_test["target_refused"]
    results: dict[str, object] = {
        "full_model": {"holdout_auc": 0.7920, "ge10_auc": round(float(roc_auc_score(y_ge10, p_full)), 4)},
        "typecode_challenger": {
            "holdout_auc": round(float(roc_auc_score(y, p_test)), 4),
            "holdout_ap": round(float(average_precision_score(y, p_test)), 4),
            "ge10_auc": round(float(roc_auc_score(y_ge10, p_ge10)), 4),
            "ge10_ap": round(float(average_precision_score(y_ge10, p_ge10)), 4),
        },
    }

    ge10_test["p_new"] = p_ge10
    ge10_test["q_old"] = pd.qcut(ge10_test["p_full"], 5, labels=False)
    ge10_test["q_new"] = pd.qcut(ge10_test["p_new"], 5, labels=False)
    missed = ge10_test[(ge10_test["target_refused"] == 1) & (ge10_test["q_old"] <= 1)]
    results["missed_refusals"] = {
        "n": int(len(missed)),
        "with_type_codes": int(missed["tparse_has_type_codes"].sum()),
        "quintile_after": missed["q_new"].value_counts().sort_index().to_dict(),
        "rescued_to_quintile3plus": int((missed["q_new"] >= 2).sum()),
        "cases": [
            {"key": str(r["case_key"]), "units": float(r["units"]), "risk_before": round(float(r["p_full"]), 3), "risk_after": round(float(r["p_new"]), 3), "has_type_codes": int(r["tparse_has_type_codes"])}
            for _, r in missed.iterrows()
        ],
    }
    (OUT / "typecode_challenger_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
