#!/usr/bin/env python3
"""GE10 deep-dive: granted-thresholds, what refusals share, specialist model.

1) Thresholds: raw score + calibrated cutoffs for the 'cleared' framing.
2) Profile: how the 88 refused 2024+2025 GE10 schemes differ from the 376 granted.
3) Specialist: retrain the v4 feature set on GE10-only pre-2024 rows and
   compare with the full model on the same 464 out-of-sample schemes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_description_lexicon import lexicon_features  # noqa: E402
from build_v3_text_encoder_experiment import build_pipeline  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


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
    lex = lexicon_features(data["description_stripped"].fillna(""))
    train = train.join(lex)
    test = test.join(lex)

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
    extras = base_extras + policy_extras + ratio_extras + context_extras + [c for c in lex.columns]
    numeric = V3_FEATURES[3:] + extras
    features = V3_FEATURES + extras

    ge10_test = test[test["units"] >= 10].copy()
    ge10_train = train[train["units"] >= 10].copy()
    print(f"GE10 train: {len(ge10_train)} | GE10 test: {len(ge10_test)}", flush=True)

    artifact = joblib.load(ARTIFACT)
    full_model = artifact["ranking_model"]
    p_full = full_model.predict_proba(ge10_test[artifact["feature_columns"]])[:, 1]
    ge10_test["p_full"] = p_full
    ge10_test["refused"] = ge10_test["target_refused"].astype(int)

    results: dict[str, object] = {}
    results["full_model_ge10"] = {
        "auc": round(float(roc_auc_score(ge10_test["target_refused"], p_full)), 4),
        "ap": round(float(average_precision_score(ge10_test["target_refused"], p_full)), 4),
    }

    safest = ge10_test.nsmallest(47, "p_full")
    riskiest = ge10_test.nlargest(47, "p_full")
    thresholds = {
        "cleared_granted_framing": {
            "n": int(len(safest)),
            "raw_score_cutoff": round(float(safest["p_full"].max()), 4),
            "refusals": int(safest["refused"].sum()),
        },
        "flagged_refusal_framing": {
            "n": int(len(riskiest)),
            "raw_score_cutoff": round(float(riskiest["p_full"].min()), 4),
            "refusals": int(riskiest["refused"].sum()),
        },
        "calibrated_risk_bands": artifact["risk_band_thresholds"],
    }
    results["thresholds"] = thresholds

    refused = ge10_test[ge10_test["target_refused"] == 1]
    granted = ge10_test[ge10_test["target_refused"] == 0]
    def profile(sel) -> dict:
        return {
            "n": int(len(sel)),
            "median_units": round(float(sel["units"].median()), 1),
            "median_density_ha": round(float(sel["density_units_per_ha"].median()), 1),
            "median_site_ha": round(float(sel["site_sqm_per_unit"].median() * sel["units"].median() / 10000), 2),
            "apartment_wording_share": round(float((sel["lex_apartment"] > 0).mean()), 3),
            "extension_wording_share": round(float((sel["lex_extension"] > 0).mean()), 3),
            "flood_hit_share": round(float(sel["flood_any"].fillna(0).gt(0).mean()), 3),
            "comp_top5_rate_median": round(float(sel["comp_top5_refusal_rate"].median()), 3),
            "desc_words_median": round(float(sel["description_stripped"].fillna("").str.split().str.len().median()), 1),
            "top_councils": sel["PlanningAuthority"].value_counts().head(5).to_dict(),
        }
    results["profile"] = {
        "refused": profile(refused),
        "granted": profile(granted),
    }

    from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402

    w13_steps = [("w13", TfidfVectorizer(stop_words="english", ngram_range=(1, 3), max_features=50000, min_df=2))]
    print("fitting GE10 specialist (structured only)...", flush=True)
    spec_struct = build_pipeline(numeric, [])
    spec_struct.fit(ge10_train[features], ge10_train["target_refused"])
    p_spec_struct = spec_struct.predict_proba(ge10_test[features])[:, 1]
    results["ge10_specialist_structured_only"] = {
        "train_n": int(len(ge10_train)),
        "auc": round(float(roc_auc_score(ge10_test["target_refused"], p_spec_struct)), 4),
        "ap": round(float(average_precision_score(ge10_test["target_refused"], p_spec_struct)), 4),
    }

    print("fitting GE10 specialist (structured + text)...", flush=True)
    spec_full = build_pipeline(numeric, w13_steps)
    spec_full.fit(ge10_train[features], ge10_train["target_refused"])
    p_spec_full = spec_full.predict_proba(ge10_test[features])[:, 1]
    results["ge10_specialist_full"] = {
        "train_n": int(len(ge10_train)),
        "auc": round(float(roc_auc_score(ge10_test["target_refused"], p_spec_full)), 4),
        "ap": round(float(average_precision_score(ge10_test["target_refused"], p_spec_full)), 4),
    }

    y_ge10 = ge10_test["target_refused"].to_numpy()
    results["paired_specialist_full_minus_full_model"] = {
        "auc_95ci": paired_diff_ci(y_ge10, p_spec_full, p_full, roc_auc_score),
        "ap_95ci": paired_diff_ci(y_ge10, p_spec_full, p_full, average_precision_score),
    }
    results["paired_specialist_struct_minus_full_model"] = {
        "auc_95ci": paired_diff_ci(y_ge10, p_spec_struct, p_full, roc_auc_score),
    }

    (OUT / "ge10_deep_dive.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
