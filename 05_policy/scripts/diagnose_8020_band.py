#!/usr/bin/env python3
"""Diagnose the E8020 over-prediction band (pred ~0.55-0.85, obs lower).

Rebuilds E8020 on the 80/20 split, applies isotonic calibration (fitted on
2023), then profiles the applications whose calibrated probability lands in
the dipped band: who they are, when they applied, and how their outcomes
compare between the 2023 calibration window and the 2024+2025 test.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402
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
    e_extras = base_extras + policy_extras + ratio_extras + context_extras
    e_features = V3_FEATURES + e_extras

    print("fitting E8020 calibrated track...", flush=True)
    pipeline = build_scaled_pipeline(V3_FEATURES[3:] + e_extras)
    pipeline.fit(train_c[e_features], train_c["target_refused"])
    p_cal = pipeline.predict_proba(cal_window[e_features])[:, 1]
    p_test = pipeline.predict_proba(test[e_features])[:, 1]

    from sklearn.isotonic import IsotonicRegression  # noqa: E402

    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p_cal, cal_window["target_refused"].to_numpy())
    iso_test = isotonic.predict(p_test)
    iso_cal = isotonic.predict(p_cal)

    cal_window = cal_window.copy()
    cal_window["iso"] = iso_cal
    test = test.copy()
    test["iso"] = iso_test

    band = (test["iso"] >= 0.55) & (test["iso"] < 0.85)
    band_rows = test[band]
    band_cal = cal_window[(cal_window["iso"] >= 0.55) & (cal_window["iso"] < 0.85)]
    print(f"band 0.55-0.85: test n={len(band_rows)} obs={band_rows['target_refused'].mean():.3f} | cal n={len(band_cal)} obs={band_cal['target_refused'].mean():.3f}", flush=True)

    profile = {}
    for frame, label in ((band_cal, "2023_cal"), (band_rows, "2024_25_test")):
        profile[label] = {
            "n": int(len(frame)),
            "obs_rate": round(float(frame["target_refused"].mean()), 4),
            "by_year": {str(k): {"n": int(len(g)), "obs": round(float(g["target_refused"].mean()), 4)} for k, g in frame.groupby(frame["received_date_dt"].dt.year)},
            "bucket_mix": frame["application_bucket"].value_counts().head(8).to_dict(),
            "density_band": {k: int(v) for k, v in frame[["density_band_low", "density_band_mid", "density_band_high"]].sum().to_dict().items()},
            "density_missing": int(frame["density_missing"].sum()),
            "top_councils": frame["PlanningAuthority"].value_counts().head(8).to_dict(),
            "median_units": float(frame["units"].median()) if "units" in frame.columns else None,
            "mean_raw_score": round(float(np.mean(p_test[band])) if label == "2024_25_test" else float(np.mean(p_cal[(cal_window["iso"] >= 0.55) & (cal_window["iso"] < 0.85)])), 4),
        }
    sub_bands = []
    for lo, hi in ((0.55, 0.65), (0.65, 0.75), (0.75, 0.85)):
        m = (test["iso"] >= lo) & (test["iso"] < hi)
        if m.sum():
            sub_bands.append({"band": f"{lo}-{hi}", "n": int(m.sum()), "obs": round(float(test.loc[m, "target_refused"].mean()), 4)})
    profile["test_sub_bands"] = sub_bands

    unit_ge10 = test[band & (test["units"] >= 10)]
    profile["ge10_in_band"] = {"n": int(len(unit_ge10)), "obs": round(float(unit_ge10["target_refused"].mean()), 4)} if len(unit_ge10) else None

    (OUTPUT_DIR / "raw_planning_8020_band_diagnosis.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    main()
