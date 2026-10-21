#!/usr/bin/env python3
"""Calibration + tight paired CIs for the 80/20 regime experiment.

Mirrors the frozen-v3 two-track protocol:
  ranking track: classifier trained < 2024-01-01, raw scores on 2024+2025
  calibrated track: classifier trained < 2023-01-01, Platt fitted on the 2023
  calendar year, applied to 2024+2025

Also reports PAIRED bootstrap differences between V3SAME and E8020 (same test
rows), which is the tightest honest way to read the gap.
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
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

CAL_CUTOFF = pd.Timestamp("2023-01-01", tz="UTC")


def platt_fit(proba: np.ndarray, y: np.ndarray) -> LogisticRegression:
    p = np.clip(proba, 1e-6, 1 - 1e-6)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    return LogisticRegression(C=1_000_000, solver="lbfgs", max_iter=1000).fit(logit, y)


def platt_apply(calibrator: LogisticRegression, proba: np.ndarray) -> np.ndarray:
    p = np.clip(proba, 1e-6, 1 - 1e-6)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    return calibrator.predict_proba(logit)[:, 1]


def isotonic_fit(proba: np.ndarray, y: np.ndarray) -> IsotonicRegression:
    return IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(proba, y)


def isotonic_apply(calibrator: IsotonicRegression, proba: np.ndarray) -> np.ndarray:
    return calibrator.predict(proba)


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


def reliability(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray]:
    edges = np.linspace(0, 1, n_bins + 1)
    mids = (edges[:-1] + edges[1:]) / 2
    predicted = np.zeros(n_bins)
    observed = np.zeros(n_bins)
    counts = np.zeros(n_bins, dtype=int)
    for i in range(n_bins):
        mask = (p >= edges[i]) & (p < edges[i + 1])
        counts[i] = int(mask.sum())
        if counts[i]:
            predicted[i] = p[mask].mean()
            observed[i] = y[mask].mean()
    ece = float(np.sum(counts * np.abs(predicted - observed)) / max(1, counts.sum()))
    max_gap = float(np.max(np.abs(predicted - observed))) if counts.sum() else 0.0
    bins = [{"bin": i, "lo": round(float(edges[i]), 3), "hi": round(float(edges[i + 1]), 3), "n": int(counts[i]), "pred": round(float(predicted[i]), 4), "obs": round(float(observed[i]), 4)} for i in range(n_bins)]
    return bins, ece, max_gap, counts


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
    variants = {
        "V3SAME": [],
        "E8020": base_extras + policy_extras + ratio_extras + context_extras,
    }

    results: dict[str, object] = {"protocol": "80/20 two-track (ranking + calibrated)"}
    scores: dict[str, dict[str, np.ndarray]] = {}
    calibrated: dict[str, dict[str, np.ndarray]] = {}
    for name, extras in variants.items():
        features = V3_FEATURES + extras
        print(f"fitting {name} ranking...", flush=True)
        pipeline = build_scaled_pipeline(V3_FEATURES[3:] + extras)
        pipeline.fit(train[features], train["target_refused"])
        p_test = pipeline.predict_proba(test[features])[:, 1]
        scores[name] = {"test": p_test}

        print(f"fitting {name} calibrated track...", flush=True)
        pipeline_c = build_scaled_pipeline(V3_FEATURES[3:] + extras)
        pipeline_c.fit(train_c[features], train_c["target_refused"])
        p_cal = pipeline_c.predict_proba(cal_window[features])[:, 1]
        p_test_c = pipeline_c.predict_proba(test[features])[:, 1]
        platt = platt_fit(p_cal, cal_window["target_refused"].to_numpy())
        cal_test = platt_apply(platt, p_test_c)
        isotonic = isotonic_fit(p_cal, cal_window["target_refused"].to_numpy())
        iso_test = isotonic_apply(isotonic, p_test_c)
        calibrated[name] = {"test": cal_test, "iso": iso_test}

        ci = paired_diff_ci(y.to_numpy(), p_test, np.zeros(len(p_test)), roc_auc_score, n_boot=2000)
        bins, ece, max_gap, counts = reliability(y.to_numpy(), cal_test)
        iso_bins, iso_ece, iso_max_gap, _ = reliability(y.to_numpy(), iso_test)
        results[name] = {
            "ranking": {
                "roc_auc": round(float(roc_auc_score(y, p_test)), 4),
                "roc_auc_bootstrap95_median": [round(x, 4) for x in ci],
                "average_precision": round(float(average_precision_score(y, p_test)), 4),
            },
            "calibrated_platt": {
                "brier": round(float(brier_score_loss(y, np.clip(cal_test, 1e-6, 1 - 1e-6))), 4),
                "log_loss": round(float(log_loss(y, np.clip(cal_test, 1e-6, 1 - 1e-6))), 4),
                "ece_weighted": round(float(ece), 4),
                "max_gap": round(float(max_gap), 4),
                "reliability_bins": bins,
                "mean_pred": round(float(cal_test.mean()), 4),
            },
            "calibrated_isotonic": {
                "brier": round(float(brier_score_loss(y, np.clip(iso_test, 1e-6, 1 - 1e-6))), 4),
                "log_loss": round(float(log_loss(y, np.clip(iso_test, 1e-6, 1 - 1e-6))), 4),
                "ece_weighted": round(float(iso_ece), 4),
                "max_gap": round(float(iso_max_gap), 4),
                "reliability_bins": iso_bins,
                "mean_pred": round(float(iso_test.mean()), 4),
            },
        }
        ge10_mask = (test["units"] >= 10).to_numpy()
        if ge10_mask.sum() >= 20 and y[ge10_mask].nunique() == 2:
            p_g = p_test[ge10_mask]
            results[name]["ge10"] = {
                "n": int(ge10_mask.sum()),
                "ranking_roc_auc": round(float(roc_auc_score(y[ge10_mask], p_g)), 4),
                "ranking_ap": round(float(average_precision_score(y[ge10_mask], p_g)), 4),
                "calibrated_platt_brier": round(float(brier_score_loss(y[ge10_mask], np.clip(cal_test[ge10_mask], 1e-6, 1 - 1e-6))), 4),
                "calibrated_isotonic_brier": round(float(brier_score_loss(y[ge10_mask], np.clip(iso_test[ge10_mask], 1e-6, 1 - 1e-6))), 4),
            }

    diff_auc = paired_diff_ci(y.to_numpy(), scores["E8020"]["test"], scores["V3SAME"]["test"], roc_auc_score, n_boot=2000)
    diff_ap = paired_diff_ci(y.to_numpy(), scores["E8020"]["test"], scores["V3SAME"]["test"], average_precision_score, n_boot=2000)
    diff_brier_platt = paired_diff_ci(y.to_numpy(), calibrated["V3SAME"]["test"], calibrated["E8020"]["test"], lambda yy, pp: brier_score_loss(yy, np.clip(pp, 1e-6, 1 - 1e-6)), n_boot=2000)
    diff_brier_iso = paired_diff_ci(y.to_numpy(), calibrated["V3SAME"]["iso"], calibrated["E8020"]["iso"], lambda yy, pp: brier_score_loss(yy, np.clip(pp, 1e-6, 1 - 1e-6)), n_boot=2000)
    results["paired_differences_E_minus_V3"] = {
        "roc_auc_95ci": [round(x, 4) for x in diff_auc],
        "average_precision_95ci": [round(x, 4) for x in diff_ap],
        "brier_platt_95ci": [round(x, 4) for x in diff_brier_platt],
        "brier_isotonic_95ci": [round(x, 4) for x in diff_brier_iso],
    }
    ge10_mask = (test["units"] >= 10).to_numpy()
    if ge10_mask.sum() >= 20:
        diff_ge10 = paired_diff_ci(y[ge10_mask].to_numpy(), scores["E8020"]["test"][ge10_mask], scores["V3SAME"]["test"][ge10_mask], roc_auc_score, n_boot=2000)
        results["paired_differences_E_minus_V3"]["ge10_roc_auc_95ci"] = [round(x, 4) for x in diff_ge10]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for ax, name in zip(axes, ("V3SAME", "E8020")):
        for bins, style, label in (
            (results[name]["calibrated_platt"]["reliability_bins"], "o--", "platt"),
            (results[name]["calibrated_isotonic"]["reliability_bins"], "s-", "isotonic"),
        ):
            preds = [b["pred"] for b in bins]
            obs = [b["obs"] for b in bins]
            ns = [b["n"] for b in bins]
            ax.plot(preds, obs, marker=style[0], linestyle=style[1:], color="#c0392b" if label == "platt" else "#2471a3", label=label)
        ax.plot([0, 1], [0, 1], "-", color="grey", alpha=0.5)
        platt_brier = results[name]["calibrated_platt"]["brier"]
        iso_brier = results[name]["calibrated_isotonic"]["brier"]
        ax.set_title(f"{name} reliability 2024+2025 (platt {platt_brier} / isotonic {iso_brier})")
        ax.set_xlabel("predicted probability")
        ax.set_ylabel("observed refusal rate")
        ax.legend()
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "reliability_8020.png", dpi=110)
    print("saved reliability_8020.png", flush=True)

    (OUTPUT_DIR / "raw_planning_8020_calibration.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
