#!/usr/bin/env python3
"""Model blending on the 80/20 protocol.

Fits V3SAME, E8020, and E8020-word13 (trigram TF-IDF) on train <2024, then
evaluates score blends (mean, rank-mean, weighted) with Platt + isotonic
calibration, plus tail diagnostics on the fat tail.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402
from build_v3_text_encoder_experiment import build_pipeline  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

CAL_CUTOFF = pd.Timestamp("2023-01-01", tz="UTC")


def paired_diff_ci(y: np.ndarray, p_a: np.ndarray, p_b: np.ndarray, metric, n_boot: int = 2000, seed: int = 11) -> list[float]:
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if np.unique(y[idx]).size < 2:
            continue
        diffs.append(metric(y[idx], p_a[idx]) - metric(y[idx], p_b[idx]))
    diffs = np.array(diffs)
    return [float(np.quantile(diffs, 0.025)), float(np.median(diffs)), float(np.quantile(diffs, 0.975))]


def rank_normalise(p: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata

    return rankdata(p) / len(p)


def isotonic_fit(proba: np.ndarray, y: np.ndarray):
    from sklearn.isotonic import IsotonicRegression

    return IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(proba, y)


def platt_fit(proba: np.ndarray, y: np.ndarray):
    from sklearn.linear_model import LogisticRegression

    p = np.clip(proba, 1e-6, 1 - 1e-6)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    return LogisticRegression(C=1_000_000, solver="lbfgs", max_iter=1000).fit(logit, y)


def platt_apply(cal, proba: np.ndarray) -> np.ndarray:
    p = np.clip(proba, 1e-6, 1 - 1e-6)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    return cal.predict_proba(logit)[:, 1]


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
    e_extras = base_extras + policy_extras + ratio_extras + context_extras

    print("fitting V3SAME...", flush=True)
    v3_pipe = build_scaled_pipeline(V3_FEATURES[3:])
    v3_pipe.fit(train[V3_FEATURES], train["target_refused"])
    v3_test = v3_pipe.predict_proba(test[V3_FEATURES])[:, 1]
    v3_cal = v3_pipe.predict_proba(cal_window[V3_FEATURES])[:, 1]

    print("fitting E8020...", flush=True)
    e_pipe = build_scaled_pipeline(V3_FEATURES[3:] + e_extras)
    e_features = V3_FEATURES + e_extras
    e_pipe.fit(train[e_features], train["target_refused"])
    e_test = e_pipe.predict_proba(test[e_features])[:, 1]
    e_cal = e_pipe.predict_proba(cal_window[e_features])[:, 1]

    print("fitting E8020-word13...", flush=True)
    w13_steps = [("w13", TfidfVectorizer(stop_words="english", ngram_range=(1, 3), max_features=50000, min_df=2))]
    w13_pipe = build_pipeline(V3_FEATURES[3:] + e_extras, w13_steps)
    w13_pipe.fit(train[e_features], train["target_refused"])
    w13_test = w13_pipe.predict_proba(test[e_features])[:, 1]
    w13_cal = w13_pipe.predict_proba(cal_window[e_features])[:, 1]

    members = {
        "V3SAME": (v3_test, v3_cal),
        "E8020": (e_test, e_cal),
        "E8020_word13": (w13_test, w13_cal),
    }

    def blend(keys: list[str], weights: list[float], use_ranks: bool = False) -> tuple[np.ndarray, np.ndarray]:
        test_parts = []
        cal_parts = []
        for key, weight in zip(keys, weights):
            t, c = members[key]
            if use_ranks:
                t = rank_normalise(t)
                c = rank_normalise(c)
            test_parts.append(weight * t)
            cal_parts.append(weight * c)
        return np.sum(test_parts, axis=0), np.sum(cal_parts, axis=0)

    blend_specs = {
        "blend_V3_E": (["V3SAME", "E8020"], [0.5, 0.5], False),
        "blend_V3_E_w13": (["V3SAME", "E8020", "E8020_word13"], [1 / 3, 1 / 3, 1 / 3], False),
        "blend_rank_V3_E_w13": (["V3SAME", "E8020", "E8020_word13"], [1 / 3, 1 / 3, 1 / 3], True),
        "blend_V3_35_E_65": (["V3SAME", "E8020"], [0.35, 0.65], False),
    }
    results: dict[str, object] = {"protocol": "80/20 blending"}
    y_arr = y.to_numpy()
    for key, (t, _) in members.items():
        results[key] = {
            "roc_auc": round(float(roc_auc_score(y_arr, t)), 4),
            "average_precision": round(float(average_precision_score(y_arr, t)), 4),
        }
    for name, (keys, weights, use_ranks) in blend_specs.items():
        t, c = blend(keys, weights, use_ranks)
        cal_iso = isotonic_fit(c, cal_window["target_refused"].to_numpy())
        cal_platt = platt_fit(c, cal_window["target_refused"].to_numpy())
        iso = cal_iso.predict(t)
        plat = platt_apply(cal_platt, t)
        results[name] = {
            "roc_auc": round(float(roc_auc_score(y_arr, t)), 4),
            "average_precision": round(float(average_precision_score(y_arr, t)), 4),
            "brier_isotonic": round(float(brier_score_loss(y_arr, np.clip(iso, 1e-6, 1 - 1e-6))), 4),
            "brier_platt": round(float(brier_score_loss(y_arr, np.clip(plat, 1e-6, 1 - 1e-6))), 4),
            "log_loss_isotonic": round(float(log_loss(y_arr, np.clip(iso, 1e-6, 1 - 1e-6))), 4),
            "tail_share_gt90": round(float((iso > 0.9).mean()), 5),
            "tail_obs_rate_gt90": round(float(y_arr[iso > 0.9].mean()), 4) if (iso > 0.9).any() else None,
            "tail_n_gt90": int((iso > 0.9).sum()),
        }

    best_blend = "blend_V3_E_w13"
    _, best_c = blend(*[blend_specs[best_blend][i] for i in (0, 1, 2)])
    cal_iso_best = isotonic_fit(best_c, cal_window["target_refused"].to_numpy())
    best_t = np.sum([(rank_normalise(members[k][0]) if False else members[k][0]) / 3 for k in ["V3SAME", "E8020", "E8020_word13"]], axis=0)
    best_iso = cal_iso_best.predict(best_t)
    results["paired_vs_best_single"] = {
        "blend_V3_E_w13_minus_E8020_auc": [round(x, 4) for x in paired_diff_ci(y_arr, best_t, e_test, roc_auc_score)],
        "blend_V3_E_w13_minus_E8020_ap": [round(x, 4) for x in paired_diff_ci(y_arr, best_t, e_test, average_precision_score)],
    }

    for key in ("E8020", "V3SAME", "blend_V3_E_w13"):
        t, c = members.get(key, (None, None))
        if t is None:
            t, c = blend(["V3SAME", "E8020", "E8020_word13"], [1 / 3, 1 / 3, 1 / 3], False)
        cal_iso = isotonic_fit(c, cal_window["target_refused"].to_numpy())
        iso = cal_iso.predict(t)
        edges = np.linspace(0, 1, 11)
        print(f"--- tail/mid bands for {key} (isotonic) ---", flush=True)
        for i in range(10):
            mask = (iso >= edges[i]) & (iso < edges[i + 1])
            if mask.sum() >= 5:
                print(f"  {edges[i]:.1f}-{edges[i+1]:.1f}: n={mask.sum():5d} pred={iso[mask].mean():.3f} obs={y_arr[mask].mean():.3f}", flush=True)

    (OUTPUT_DIR / "raw_planning_8020_blending.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
