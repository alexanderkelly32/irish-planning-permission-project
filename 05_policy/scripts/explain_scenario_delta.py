#!/usr/bin/env python3
"""Explain scenario deltas: exact per-feature decomposition of probability moves.

Linear-model auditability: for a baseline and a mutated proposal, compute the
change in each transformed feature and its contribution to the logit
(contribution = delta_feature * coefficient), grouped by feature family.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from model_feature_builder import build_feature_row  # noqa: E402

MODEL_PATH = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"

GROUP_LABELS = {
    "num__log_units": "units count",
    "num__log_site_area_sqm": "site area",
    "num__log_floor_area_sqm": "floor area",
    "num__units_missing": "units missing flag",
    "num__density_units_per_ha": "density (units/ha)",
    "num__floor_area_ratio": "floor area ratio",
    "num__site_sqm_per_unit": "site per unit",
    "num__avg_unit_floor_sqm": "avg unit floor area",
    "num__density_band_low": "density band <35/ha",
    "num__density_band_mid": "density band 35-50/ha",
    "num__density_band_high": "density band >50/ha",
    "num__density_over_45": "density >45/ha",
    "num__density_missing": "density missing flag",
    "num__flood_any": "flood hit",
    "num__log_pop_density": "area population density",
    "num__is_urban": "urban location",
    "num__log_plan_unique_codes": "plan objective count",
    "num__plan_theme_design": "plan design codes",
    "num__plan_theme_zoning": "plan zoning codes",
    "num__plan_theme_housing": "plan housing codes",
    "num__received_year": "submission year",
    "num__log_national_prior_24m_count": "national prior volume",
    "num__log_authority_prior_12m_count": "council prior volume",
    "num__log_same_site_prior_count": "same-site prior volume",
    "num__national_prior_24m_refusal_rate": "national refusal rate",
    "num__authority_prior_12m_refusal_rate": "council refusal rate",
    "num__same_site_prior_refusal_rate": "same-site refusal rate",
    "num__nearby_1km_prior_24m_refusal_rate": "nearby 1km refusal rate",
    "num__nearby_3km_prior_24m_refusal_rate": "nearby 3km refusal rate",
    "num__comp_top5_refusal_rate": "comparable top-5 rate",
    "num__comp_top10_refusal_rate": "comparable top-10 rate",
    "num__comp_top20_refusal_rate": "comparable top-20 rate",
    "num__comp_top20_mean_similarity": "comparable similarity",
    "num__comp_top20_refused_similarity_gap": "comparable refused-granted gap",
    "num__comp_top20_same_authority_refusal_rate": "comparable same-council rate",
    "num__septic_share": "septic tank share",
    "num__cars_per_hh": "cars per household",
    "num__log_national_road_dist": "distance to national road",
}


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def explain_delta(artifact, baseline: dict, mutated: dict) -> dict:
    frame0 = build_feature_row(baseline)
    frame1 = build_feature_row(mutated)
    pre = artifact["ranking_model"].named_steps["preprocessor"]
    model = artifact["ranking_model"].named_steps["model"]
    x0 = pre.transform(frame0)
    x1 = pre.transform(frame1)
    names = pre.get_feature_names_out()
    coefs = model.coef_[0]

    if sparse.issparse(x0):
        delta = (x1 - x0).toarray()[0]
    else:
        delta = x1[0] - x0[0]
    contributions = delta * coefs
    total_logit = float(contributions.sum())
    logit0 = float(model.decision_function(x0)[0])
    p0 = float(sigmoid(np.array([logit0]))[0])
    p1 = float(sigmoid(np.array([logit0 + total_logit]))[0])

    groups: dict[str, float] = {}
    detail_rows = []
    for name, contrib in zip(names, contributions):
        if abs(contrib) < 1e-9:
            continue
        prefix = name.split("__")[0]
        raw = name.split("__", 1)[1]
        if prefix == "num":
            label = GROUP_LABELS.get(name, raw)
            group = f"numeric: {label}"
        elif prefix == "cat":
            if "application_bucket" in name:
                group = "application type bucket"
            else:
                group = "council category"
        else:
            group = "description text"
            detail_rows.append({"term": raw, "logit_contribution": round(float(contrib), 4)})
            groups[group] = groups.get(group, 0.0) + float(contrib)
            continue
        groups[group] = groups.get(group, 0.0) + float(contrib)
        detail_rows.append({"feature": name, "logit_contribution": round(float(contrib), 4)})

    top_text = sorted((r for r in detail_rows if "term" in r), key=lambda r: -abs(r["logit_contribution"]))[:10]
    top_features = sorted((r for r in detail_rows if "feature" in r), key=lambda r: -abs(r["logit_contribution"]))[:12]
    group_list = sorted(groups.items(), key=lambda kv: -abs(kv[1]))
    return {
        "baseline_probability": round(p0, 4),
        "mutated_probability": round(p1, 4),
        "delta_probability_pp": round((p1 - p0) * 100, 2),
        "total_logit_change": round(total_logit, 4),
        "group_contributions_logit": {k: round(v, 4) for k, v in group_list},
        "top_feature_contributions": top_features,
        "top_text_terms": top_text,
    }


def main() -> None:
    artifact = joblib.load(MODEL_PATH)
    baseline = {
        "authority": "Dun Laoghaire Rathdown County Council",
        "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
        "units": 12,
        "site_area_sqm": 4000,
        "floor_area_sqm": 2400,
        "itm_easting": 722000,
        "itm_northing": 726500,
        "submission_year": 2026,
    }
    scenarios = {
        "fewer_units_8": {**baseline, "units": 8, "floor_area_sqm": 1600},
        "more_units_16": {**baseline, "units": 16, "floor_area_sqm": 3200},
        "smaller_site": {**baseline, "site_area_sqm": 2500},
        "one_off_house": {**baseline, "units": 1, "floor_area_sqm": 250, "description": "construction of a single dwelling house with garage"},
    }
    out: dict[str, object] = {}
    for name, mutated in scenarios.items():
        out[name] = explain_delta(artifact, baseline, mutated)
        print(f"===== {name}", flush=True)
        print(json.dumps(out[name], indent=2), flush=True)
    (OUT / "scenario_explanation_v4.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("saved -> scenario_explanation_v4.json", flush=True)


if __name__ == "__main__":
    main()
