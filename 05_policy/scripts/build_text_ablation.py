#!/usr/bin/env python3
"""Text ablation: how much does the free-text description actually help?

Variants on the 80/20 protocol (train <2024, test 2024+2025):
  full        v4-full (TF-IDF 1-3 grams + all structured)
  no_tfidf    structured features only (comparable text-similarity features kept)
  structured_only  no TF-IDF and no comparable features (pure register/policy/context)

Reports AUC/AP + GE10 subset with paired differences vs full.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_v3_text_encoder_experiment import build_pipeline  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402

COMP_FEATURES = [
    "comp_top5_refusal_rate", "comp_top10_refusal_rate", "comp_top20_refusal_rate",
    "comp_top20_mean_similarity", "comp_top20_max_refused_similarity",
    "comp_top20_max_granted_similarity", "comp_top20_refused_similarity_gap",
    "comp_top20_same_authority_share", "comp_top20_same_authority_refusal_rate",
    "comp_top20_count",
]


def paired_diff_ci(y, p_a, p_b, metric, n_boot=2000, seed=11):
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if np.unique(y[idx]).size < 2:
            continue
        diffs.append(metric(y[idx], p_a[idx]) - metric(y[idx], p_b[idx]))
    diffs = np.array(diffs)
    return [round(float(np.quantile(diffs, q)), 4) for q in (0.025, 0.5, 0.975)]


def main() -> None:
    data, train, test, y = build_data()
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

    variants = {
        "full": (numeric, [], None),
        "no_tfidf": (numeric, [], None),
        "structured_only": ([c for c in numeric if c not in COMP_FEATURES], [], None),
    }
    results: dict[str, object] = {"protocol": "80/20 text ablation"}
    scores = {}
    for name, (num, text_steps, _) in variants.items():
        if name == "full":
            num = numeric
            text_steps = w13_steps
        print(f"fitting {name}...", flush=True)
        pipeline = build_pipeline(num, text_steps)
        pipeline.fit(train[features], train["target_refused"])
        p = pipeline.predict_proba(test[features])[:, 1]
        scores[name] = p
        results[name] = {
            "roc_auc": round(float(roc_auc_score(y, p)), 4),
            "average_precision": round(float(average_precision_score(y, p)), 4),
        }
        ge10_mask = (test["units"] >= 10).to_numpy()
        if ge10_mask.sum() >= 20 and y[ge10_mask].nunique() == 2:
            results[name]["ge10"] = {
                "n": int(ge10_mask.sum()),
                "roc_auc": round(float(roc_auc_score(y[ge10_mask], p[ge10_mask])), 4),
                "ap": round(float(average_precision_score(y[ge10_mask], p[ge10_mask])), 4),
            }
    y_arr = y.to_numpy()
    for ablated in ("no_tfidf", "structured_only"):
        results[f"paired_{ablated}_minus_full"] = {
            "roc_auc_95ci": paired_diff_ci(y_arr, scores[ablated], scores["full"], roc_auc_score),
            "average_precision_95ci": paired_diff_ci(y_arr, scores[ablated], scores["full"], average_precision_score),
        }
    (OUTPUT_DIR / "raw_planning_8020_text_ablation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
