#!/usr/bin/env python3
"""Activate Capital portfolio backtest - time-safe, per-scheme retraining.

Protocol (per the requested design):
  1. For each of the 11 register-matched schemes, t0 = its submission date.
  2. A v4-faithful pipeline (TF-IDF (1,3) 50k + balanced liblinear C=0.5 +
     numeric/categorical preprocessing, exactly build_scaled_pipeline) is
     retrained on rows received strictly before t0, EXCLUDING the scheme and
     obvious site variants (same authority, description cosine >= 0.5 within
     +-2 years of t0).
  3. An isotonic calibrator is fit on the 12 months of training rows
     immediately before t0 (the same windowed-calibration design as v4-full).
  4. The scheme is scored with the calibrated t0 model; outcome, decision
     date, FI and appeal flags are recorded.
  5. Matched controls: same authority, 10+ units, received within +-365 days
     of t0, excluding site variants - scored with the same t0 model.
  6. Headline: sum of predicted probabilities across the funded cohort vs
     actual refusals, plus control discrimination (mean predicted risk for
     refused vs granted controls).

Caveat: the register under-covers Activate's SHD-era portfolio; this run
covers the 11 schemes that matched cleanly (state the unmatched ones).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import build_data  # noqa: E402
from build_comparable_feature_experiment import V3_FEATURES  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

SCHEMES = [
    {"name": "Grand Canal Harbour", "case_key": "Dublin City Council__3209/19", "portfolio_units": 596, "note": "original scheme (550 in register; portfolio 596 under 2765/20 - variant excluded)"},
    {"name": "Vartry Wood", "case_key": "Wicklow County Council__SH202003", "portfolio_units": 133, "note": "117 houses + 16 duplexes = 133 (register match)"},
    {"name": "Churchlands", "case_key": "Wicklow County Council__20488", "portfolio_units": 140, "note": "portfolio says 140 homes; register phase is 66 dwellings"},
    {"name": "Trinity Collection", "case_key": "Dublin City Council__3894/19", "portfolio_units": 372, "note": "register phase 420 units"},
    {"name": "The Willows", "case_key": "Meath County Council__SH307244", "portfolio_units": 1000, "note": "211-unit phase of the 1,000-home masterplan"},
    {"name": "Millerstown", "case_key": "Kildare County Council__19304632", "portfolio_units": 203, "note": "portfolio says 203; register SHD phase 268"},
    {"name": "Usher's Mill", "case_key": "Louth County Council__22713", "portfolio_units": 270, "note": "99-unit phase (+ creche) of 270"},
    {"name": "Barnhill Place", "case_key": "Dun Laoghaire Rathdown County Council__D18A/0418", "portfolio_units": 36, "note": "23 apartments + 13 houses"},
    {"name": "Charlemont Square", "case_key": "Dublin City Council__4088/18", "portfolio_units": 300, "note": "portfolio says 300; register phase 86 units"},
    {"name": "Ballymakenny Park", "case_key": "Louth County Council__221021", "portfolio_units": 300, "note": "94-unit phase"},
    {"name": "Aderrig", "case_key": "South Dublin County Council__SDZ22A/0014", "portfolio_units": 227, "note": "portfolio says 227; register SDZ phase 207"},
]

EXTRAS = (
    ["log_units", "log_site_area_sqm", "log_floor_area_sqm", "units_missing",
     "applicant_prior_count", "applicant_prior_refusal_rate",
     *pc.FLOOD_FEATURES, "flood_any"]
    + ["log_plan_unique_codes", "log_plan_mentions", "policy_plan_covered",
       *[f"plan_theme_{t}" for t in pc.THEME_ORDER], "plan_theme_other", "log_plan_codes_match_desc"]
    + ["density_units_per_ha", "floor_area_ratio", "site_sqm_per_unit", "avg_unit_floor_sqm",
       "density_band_low", "density_band_mid", "density_band_high", "density_over_45", "density_missing",
       "landuse_new_house", "landuse_housing_new", "landuse_extension", "landuse_retention", "landuse_missing"]
    + ["log_pop_density", "owner_share", "private_rent_share", "la_rent_share", "septic_share",
       "cars_per_hh", "no_car_share", "log_national_road_dist", "national_roads_within_1km", "is_urban"]
)
FEATURES = V3_FEATURES + EXTRAS


def main() -> None:
    data, train, test, y = build_data()
    reg = data.reset_index(drop=True)
    reg = reg[reg["received_date_dt"].notna()].copy()

    frozen = joblib.load(ROOT / "05_policy" / "current" / "model_v4" / "comparable_reference.joblib")
    sim_vectorizer = frozen["vectorizer"]

    rows: list[dict] = []
    control_rows: list[dict] = []
    for scheme in SCHEMES:
        scheme_rows = reg[reg["case_key"] == scheme["case_key"]]
        if len(scheme_rows) == 0:
            rows.append({**scheme, "status": "NOT IN REGISTER", "predicted": None})
            print(f"{scheme['name']}: NOT IN REGISTER", flush=True)
            continue
        row = scheme_rows.iloc[0]
        t0 = row["received_date_dt"]
        authority = row["PlanningAuthority"]
        desc = str(row["description_stripped"] or "")

        variants = reg[
            (reg["PlanningAuthority"] == authority)
            & ((reg["received_date_dt"] - t0).dt.days.abs() <= 730)
            & (reg["case_key"] != scheme["case_key"])
        ].copy()
        if len(variants):
            vq = sim_vectorizer.transform([desc])
            vm = sim_vectorizer.transform(variants["description_stripped"].fillna("").astype(str))
            sims = np.asarray(cosine_similarity(vq, vm)).ravel()
            variant_keys = set(variants.loc[sims >= 0.5, "case_key"])
        else:
            variant_keys = set()

        train_mask = (reg["received_date_dt"] < t0) & (~reg["case_key"].isin(variant_keys)) & (reg["case_key"] != scheme["case_key"])
        fit = reg[train_mask].copy()
        cal_mask = (reg["received_date_dt"] >= t0 - pd.DateOffset(months=12)) & (reg["received_date_dt"] < t0) & (~reg["case_key"].isin(variant_keys))
        cal = reg[cal_mask].copy()

        pipeline = build_scaled_pipeline(V3_FEATURES[3:] + EXTRAS)
        pipeline.fit(fit[FEATURES], fit["target_refused"])
        raw_cal = pipeline.predict_proba(cal[FEATURES])[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(raw_cal, cal["target_refused"])

        scheme_raw = pipeline.predict_proba(scheme_rows[FEATURES])[:, 1][0]
        predicted = float(np.clip(iso.predict([scheme_raw])[0], 0.0, 1.0))

        fi_flag = bool(pd.notna(row.get("FIRequestDate")))
        appeal_flag = bool(pd.notna(row.get("AppealRefNumber")) and str(row.get("AppealRefNumber")).strip())

        controls = reg[
            (reg["PlanningAuthority"] == authority)
            & (reg["units"] >= 10)
            & ((reg["received_date_dt"] - t0).dt.days.abs() <= 365)
            & (~reg["case_key"].isin(variant_keys))
            & (reg["case_key"] != scheme["case_key"])
        ].copy()
        if len(controls):
            controls["p"] = iso.predict(pipeline.predict_proba(controls[FEATURES])[:, 1])
            refused = controls[controls["target_refused"] == 1]
            granted = controls[controls["target_refused"] == 0]
            for label, frame in (("refused", refused), ("granted", granted)):
                if len(frame):
                    control_rows.append({
                        "scheme": scheme["name"], "authority": authority, "t0": str(t0.date()),
                        "control_group": label, "n": int(len(frame)),
                        "mean_predicted": round(float(frame["p"].mean()), 4),
                    })

        rows.append({
            **scheme,
            "status": "scored",
            "t0": str(t0.date()),
            "authority": authority,
            "units_register": float(row["units"]) if pd.notna(row["units"]) else None,
            "outcome": "Refused" if int(row["target_refused"]) == 1 else "Granted",
            "decision_date": str(row["DecisionDate"].date()) if pd.notna(row["DecisionDate"]) else None,
            "predicted_refusal": round(predicted, 4),
            "fi_flag": fi_flag,
            "appeal_flag": appeal_flag,
            "train_n": int(len(fit)),
            "cal_n": int(len(cal)),
            "variants_excluded": int(len(variant_keys)),
            "controls_n": int(len(controls)),
        })
        print(f"{scheme['name']}: t0={t0.date()} pred={predicted*100:.1f}% outcome={rows[-1]['outcome']} "
              f"train={len(fit)} cal={len(cal)} variants_excl={len(variant_keys)} controls={len(controls)}", flush=True)

    frame = pd.DataFrame(rows)
    scored = frame[frame["status"] == "scored"]
    expected_refusals = float(scored["predicted_refusal"].sum())
    actual_refusals = int((scored["outcome"] == "Refused").sum())
    control_frame = pd.DataFrame(control_rows)
    summary = {
        "protocol": "per-t0 retrain of the v4-faithful pipeline; windowed isotonic on the 12 months pre-t0; site variants excluded",
        "cohort": {"funded_matched": int(len(scored)), "unmatched_from_portfolio": int((frame["status"] != "scored").sum())},
        "headline": {
            "expected_refusals_sum_p": round(expected_refusals, 3),
            "actual_refusals": actual_refusals,
            "note": "All matched funded schemes were granted. Sum(p) is the model's expected refusal count under perfect calibration - compare against 0 observed.",
        },
        "per_scheme": json.loads(scored.to_json(orient="records")),
        "controls": json.loads(control_frame.to_json(orient="records")),
    }
    if len(control_frame):
        agg = control_frame.groupby("control_group")["mean_predicted"].mean().to_dict()
        refused_mean = agg.get("refused")
        granted_mean = agg.get("granted")
        summary["control_discrimination"] = {
            "mean_predicted_refused_controls": refused_mean,
            "mean_predicted_granted_controls": granted_mean,
            "gap_pp": round((refused_mean - granted_mean) * 100, 2) if refused_mean is not None and granted_mean is not None else None,
        }
    (OUT_DIR / "activate_backtest_2026-09-24.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    scored.to_csv(OUT_DIR / "activate_backtest_2026-09-24.csv", index=False)
    if len(control_frame):
        control_frame.to_csv(OUT_DIR / "activate_backtest_controls_2026-09-24.csv", index=False)
    print("\nHEADLINE: expected refusals (sum p) =", round(expected_refusals, 3), "| actual =", actual_refusals)
    if "control_discrimination" in summary:
        print("CONTROL DISCRIMINATION:", summary["control_discrimination"])
    print("saved ->", OUT_DIR / "activate_backtest_2026-09-24.json")


if __name__ == "__main__":
    main()
