#!/usr/bin/env python3
"""Structured-feature breakdown: leave-one-group-out ablations on the 80/20 protocol.

Reference = v4-full (0.7920). Each structured group is removed in turn and the
AUC drop shows that group's contribution (approx - groups interact through the
logit, so shares are indicative, not exactly additive).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_national_residential_model_v2 import V2_NUMERIC  # noqa: E402
import build_v3_text_encoder_experiment as te  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

GROUPS = {
    "history (prior counts/rates)": [
        "received_year",
        "log_national_prior_24m_count", "log_authority_prior_12m_count", "log_authority_prior_24m_count",
        "log_same_site_prior_count", "log_nearby_1km_prior_24m_count", "log_nearby_3km_prior_24m_count",
        "national_prior_24m_refusal_rate", "authority_prior_12m_refusal_rate", "authority_prior_24m_refusal_rate",
        "same_site_prior_refusal_rate", "nearby_1km_prior_24m_refusal_rate", "nearby_3km_prior_24m_refusal_rate",
    ],
    "comparable precedents": [
        "comp_top5_refusal_rate", "comp_top10_refusal_rate", "comp_top20_refusal_rate",
        "comp_top20_mean_similarity", "comp_top20_max_refused_similarity", "comp_top20_max_granted_similarity",
        "comp_top20_refused_similarity_gap", "comp_top20_same_authority_share",
        "comp_top20_same_authority_refusal_rate", "comp_top20_count",
    ],
    "register size/ratios": [
        "log_units", "log_site_area_sqm", "log_floor_area_sqm", "units_missing",
        "density_units_per_ha", "floor_area_ratio", "site_sqm_per_unit", "avg_unit_floor_sqm",
        "density_band_low", "density_band_mid", "density_band_high", "density_over_45", "density_missing",
        "landuse_new_house", "landuse_housing_new", "landuse_extension", "landuse_retention", "landuse_missing",
    ],
    "flood": [*pc.FLOOD_FEATURES, "flood_any"],
    "policy layer": [
        "log_plan_unique_codes", "log_plan_mentions", "policy_plan_covered",
        *[f"plan_theme_{t}" for t in pc.THEME_ORDER], "plan_theme_other",
        "log_plan_codes_match_desc",
    ],
    "census/context": [
        "log_pop_density", "owner_share", "private_rent_share", "la_rent_share",
        "septic_share", "cars_per_hh", "no_car_share",
        "log_national_road_dist", "national_roads_within_1km", "is_urban",
    ],
    "applicant history": ["applicant_prior_count", "applicant_prior_refusal_rate"],
}


def main() -> None:
    data, train, test, y = build_data()
    all_numeric = V2_NUMERIC + [c for c in data.columns if c.startswith("comp_")] + [
        "log_units", "log_site_area_sqm", "log_floor_area_sqm", "units_missing",
        "density_units_per_ha", "floor_area_ratio", "site_sqm_per_unit", "avg_unit_floor_sqm",
        "density_band_low", "density_band_mid", "density_band_high", "density_over_45", "density_missing",
        "landuse_new_house", "landuse_housing_new", "landuse_extension", "landuse_retention", "landuse_missing",
        *pc.FLOOD_FEATURES, "flood_any",
        "log_plan_unique_codes", "log_plan_mentions", "policy_plan_covered",
        *[f"plan_theme_{t}" for t in pc.THEME_ORDER], "plan_theme_other",
        "log_plan_codes_match_desc",
        "log_pop_density", "owner_share", "private_rent_share", "la_rent_share",
        "septic_share", "cars_per_hh", "no_car_share",
        "log_national_road_dist", "national_roads_within_1km", "is_urban",
        "applicant_prior_count", "applicant_prior_refusal_rate",
    ]
    all_numeric = [c for c in all_numeric if c in data.columns]
    features = ["PlanningAuthority", "application_bucket", "description_stripped"] + all_numeric
    w13_steps = [("w13", TfidfVectorizer(stop_words="english", ngram_range=(1, 3), max_features=50000, min_df=2))]

    def fit_score(numeric: list[str], cat_enabled: bool = True):
        saved_cat = te.CATEGORICAL
        if not cat_enabled:
            te.CATEGORICAL = []
        pipeline = te.build_pipeline(numeric, w13_steps)
        pipeline.fit(train[features], train["target_refused"])
        p = pipeline.predict_proba(test[features])[:, 1]
        te.CATEGORICAL = saved_cat
        return roc_auc_score(y, p), average_precision_score(y, p)

    results: dict[str, object] = {"protocol": "80/20 leave-one-group-out"}
    full_auc, full_ap = fit_score(all_numeric)
    results["full"] = {"auc": round(float(full_auc), 4), "ap": round(float(full_ap), 4)}

    breakdown = []
    for group, columns in GROUPS.items():
        remaining = [c for c in all_numeric if c not in columns]
        auc, ap = fit_score(remaining)
        breakdown.append({
            "group": group,
            "auc_without": round(float(auc), 4),
            "contribution_pp": round(float(full_auc - auc) * 100, 2),
        })
    breakdown.sort(key=lambda r: -r["contribution_pp"])
    results["groups"] = breakdown

    auc_nocat, _ = fit_score(all_numeric, cat_enabled=False)
    results["without_categoricals"] = {
        "auc": round(float(auc_nocat), 4),
        "contribution_pp": round(float(full_auc - auc_nocat) * 100, 2),
        "note": "council + application-bucket one-hots removed entirely",
    }
    (OUT / "structured_feature_breakdown.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
