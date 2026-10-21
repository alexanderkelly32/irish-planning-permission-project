#!/usr/bin/env python3
"""Evaluate the reason/theme-transfer accuracy of the precedent evidence engine.

Important framing: national_residential_v4_full predicts REFUSAL PROBABILITY,
not reasons. The product surfaces "reasons" by transferring the extracted
refusal themes of matched historical refusals. This script measures how well
that transfer predicts the ACTUAL primary theme of refused large schemes on
the 2024-2025 holdout.

Protocol (leakage-free):
- cohort: refused GE10 (10+ units) holdout cases with an extracted top theme
- for each case, precedents = the same scheme type, received STRICTLY BEFORE
  the case's received date, refused, with an extracted theme
- precedent ranking: the display matcher (wording + units + density + council
  + recency) restricted to that time-safe pool
- prediction: similarity-weighted theme vote over the top-10 precedents
- metrics: top-1 / top-2 / top-3 agreement vs the actual top theme, against
  the "always predict the most common theme" baseline
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current" / "raw_planning_reason_prediction_eval.json"
RECENT = ROOT / "05_policy" / "current" / "model_v4" / "recent_precedents_reference.joblib"
GE10_SCORED = ROOT / "05_policy" / "current" / "ge10_scored_2024_25.csv"

WEIGHTS = {"text": 0.45, "units": 0.20, "density": 0.10, "recency": 0.15, "council": 0.10}
TOP_K = 10


def _tag_share_rank(bucket: dict, mask: np.ndarray) -> str:
    tags = bucket["top_primary_tag"][mask]
    tags = tags[tags != ""]
    if len(tags) == 0:
        return ""
    values, counts = np.unique(tags, return_counts=True)
    return str(values[np.argmax(counts)])


def main() -> None:
    recent = joblib.load(RECENT)
    frozen = joblib.load(ROOT / "05_policy" / "current" / "model_v4" / "comparable_reference.joblib")
    vectorizer = frozen["vectorizer"]
    bucket = recent["buckets"]["10+ units"]
    matrix = bucket["matrix"]
    years = bucket["received_year"]
    authorities = bucket["authority"]
    units_arr = bucket["units"].astype(float)
    site_arr = bucket["site_sqm"].astype(float)
    tags = bucket["top_primary_tag"]
    targets = bucket["target"]
    case_keys = np.array([str(k) for k in bucket["case_key"]])
    received_dates = np.array([str(d) for d in bucket["received_date"]])

    ge10 = pd.read_csv(GE10_SCORED, low_memory=False)
    refused = ge10[ge10["outcome"].astype(str).str.upper().str.contains("REFUS")].copy()
    key_to_index = {key: i for i, key in enumerate(case_keys)}

    evaluable = 0
    no_tag = 0
    no_precedents = 0
    top1_hits = 0
    top2_hits = 0
    top3_hits = 0
    baseline_hits = 0
    detail: list[dict] = []

    for _, row in refused.iterrows():
        index = key_to_index.get(str(row["case_key"]))
        if index is None:
            continue
        actual_tag = str(tags[index])
        if not actual_tag:
            no_tag += 1
            continue

        query_text = str(bucket["description"][index])
        if not query_text.strip():
            continue
        own_received = received_dates[index]
        eligible = (
            (received_dates < own_received)
            & (targets == 1)
            & (tags != "")
            & (case_keys != case_keys[index])
        )
        if not eligible.any():
            no_precedents += 1
            continue

        query_vec = vectorizer.transform([query_text])
        text_sims = np.asarray(cosine_similarity(query_vec, matrix)).ravel()

        query_units = units_arr[index]
        known = ~np.isnan(units_arr) & (units_arr > 0)
        unit_close = np.where(known, np.exp(-0.6 * np.abs(np.log1p(np.where(known, units_arr, 1.0)) - np.log1p(query_units))), 0.5)

        query_density = np.log(units_arr[index] / site_arr[index]) if not np.isnan(site_arr[index]) and site_arr[index] > 0 else np.nan
        if not np.isnan(query_density):
            known_d = ~np.isnan(site_arr) & (site_arr > 0) & known
            density_close = np.where(known_d, np.exp(-0.6 * np.abs(np.log(np.where(known_d, units_arr / np.where(known_d, site_arr, 1.0), 1.0)) - query_density)), 0.5)
        else:
            density_close = np.full(len(text_sims), 0.5)

        age = np.clip(years[index] - years, 0, 5)
        recency = np.exp(-age / 2.5)
        council_boost = (authorities == authorities[index]).astype(float)
        combined = (WEIGHTS["text"] * text_sims + WEIGHTS["units"] * unit_close
                    + WEIGHTS["density"] * density_close + WEIGHTS["recency"] * recency
                    + WEIGHTS["council"] * council_boost) * eligible

        order = np.argsort(-combined)
        chosen = []
        votes: dict[str, float] = {}
        for candidate in order:
            if len(chosen) >= TOP_K or combined[candidate] <= 0:
                break
            chosen.append(candidate)
            theme = str(tags[candidate])
            votes[theme] = votes.get(theme, 0.0) + combined[candidate]
        if not votes:
            no_precedents += 1
            continue

        ranked = sorted(votes.items(), key=lambda pair: -pair[1])
        top1 = ranked[0][0]
        top2 = {theme for theme, _ in ranked[:2]}
        top3 = {theme for theme, _ in ranked[:3]}

        baseline_theme = _tag_share_rank(bucket, eligible)
        evaluable += 1
        if top1 == actual_tag:
            top1_hits += 1
        if actual_tag in top2:
            top2_hits += 1
        if actual_tag in top3:
            top3_hits += 1
        if baseline_theme == actual_tag:
            baseline_hits += 1
        detail.append({
            "case_key": str(row["case_key"]),
            "actual_tag": actual_tag,
            "predicted_top1": top1,
            "predicted_top3": sorted(top3),
            "n_precedents": len(chosen),
            "mean_precedent_sim": round(float(np.mean(text_sims[chosen])), 3),
            "baseline_tag": baseline_theme,
        })

    payload = {
        "protocol": "theme transfer from time-safe matched refused precedents (display engine), refused GE10 holdout 2024-2025",
        "cohort": {
            "refused_holdout": int(len(refused)),
            "evaluable": evaluable,
            "missing_extracted_tag": no_tag,
            "no_tagged_precedents_before_case": no_precedents,
        },
        "metrics": {
            "top1_agreement": round(top1_hits / evaluable, 3) if evaluable else None,
            "top2_agreement": round(top2_hits / evaluable, 3) if evaluable else None,
            "top3_agreement": round(top3_hits / evaluable, 3) if evaluable else None,
            "baseline_most_common_tag_agreement": round(baseline_hits / evaluable, 3) if evaluable else None,
        },
        "detail": detail,
        "caveats": [
            "The v4-full model predicts refusal probability; this measures the theme-transfer accuracy of the precedent evidence engine only.",
            "Themes come from inspector documents; multi-theme cases are reduced to their single primary tag.",
            "Sample is the refused subset of the 464-scheme GE10 holdout with extracted reasons - small n, wide confidence.",
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "detail"}, indent=2))
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
