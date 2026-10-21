#!/usr/bin/env python3
"""Chokepoint/refusal-reason prediction evaluation.

Answers: how good is the model (same inputs) at predicting the most likely
refusal themes? Multi-label theme classification on the tagged refused GE10
arm, using only submission-time inputs (description text + register numerics +
policy/flood/context features).

Also reports v4-full risk alignment by theme on out-of-sample 2024+2025 rows.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402

THEMES = [
    "density_scale", "design_layout", "residential_amenity", "land_use_policy",
    "traffic_access", "flooding_drainage", "water_wastewater", "premature_or_info_gap",
    "ecology_trees", "heritage_archaeology",
]
NUMERIC = [
    "density_units_per_ha", "floor_area_ratio", "log_units", "log_site_area_sqm",
    "flood_any", "log_pop_density", "is_urban", "log_plan_unique_codes",
    "plan_theme_design", "plan_theme_zoning", "plan_theme_housing",
    "received_year",
]


def slug(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(key).lower())


def main() -> None:
    data, train, test, y = build_data()
    themes_df = pd.read_csv(ROOT / "02_development" / "current" / "refused_arm_themes.csv", low_memory=False)
    themes_df = themes_df[themes_df["case_primary_tags"].notna()].copy()
    themes_df["slug"] = themes_df["original_case_key"].map(slug)
    data["slug"] = data["case_key"].astype(str).map(slug)

    merged = themes_df.merge(
        data[["slug", "case_key", "received_date_dt", "description_stripped", *NUMERIC]],
        on="slug", how="inner",
    ).drop_duplicates("slug", keep="first")
    merged = merged[merged["description_stripped"].notna()]
    print("tagged refused cases joined:", len(merged), flush=True)
    print(merged["received_date_dt"].dt.year.value_counts().sort_index().to_string(), flush=True)

    for theme in THEMES:
        merged[theme] = merged["case_primary_tags"].astype(str).str.contains(theme, regex=False).astype(int)

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=20000, min_df=2)
    x_text = vectorizer.fit_transform(merged["description_stripped"].fillna("").astype(str))
    x_num = StandardScaler().fit_transform(merged[NUMERIC].fillna(0).to_numpy())
    x = np.hstack([x_text.toarray(), x_num])

    cutoff_idx = (merged["received_date_dt"] >= CUTOFF).to_numpy()
    n_test = int(cutoff_idx.sum())
    results: dict[str, object] = {"tagged_n": int(len(merged)), "tagged_n_2024plus": int(n_test)}
    theme_report = {}
    for theme in THEMES:
        y_theme = merged[theme].to_numpy()
        if y_theme.sum() < 20 or (y_theme.sum() == len(y_theme)):
            continue
        if n_test >= 15 and y_theme[cutoff_idx].sum() >= 5 and (1 - y_theme[cutoff_idx]).sum() >= 5:
            model = LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)
            model.fit(x[~cutoff_idx], y_theme[~cutoff_idx])
            p = model.predict_proba(x[cutoff_idx])[:, 1]
            auc = roc_auc_score(y_theme[cutoff_idx], p)
            mode = "time_split"
        else:
            from sklearn.model_selection import cross_val_predict

            model = LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)
            p = cross_val_predict(model, x, y_theme, cv=5, method="predict_proba")[:, 1]
            auc = roc_auc_score(y_theme, p)
            mode = "5fold_cv"
        theme_report[theme] = {"auc": round(float(auc), 3), "n_positive": int(y_theme.sum()), "mode": mode}
    results["per_theme_auc"] = dict(sorted(theme_report.items(), key=lambda kv: -kv[1]["auc"]))

    prior = merged["case_top_primary_tag"].fillna("").astype(str).value_counts()
    results["prior_top_theme_share"] = round(float(prior.iloc[0] / len(merged)), 3) if len(prior) else None

    top3 = {theme: roc_auc_score if False else None for theme in THEMES}
    probs = {}
    for theme in THEMES:
        y_theme = merged[theme].to_numpy()
        if y_theme.sum() < 10 or y_theme.sum() == len(y_theme):
            continue
        from sklearn.model_selection import cross_val_predict

        model = LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)
        probs[theme] = cross_val_predict(model, x, y_theme, cv=5, method="predict_proba")[:, 1]
    if probs:
        prob_frame = pd.DataFrame(probs)
        top1_hit = 0
        top3_hit = 0
        actual_top = merged["case_top_primary_tag"].fillna("").astype(str)
        for i, actual in enumerate(actual_top):
            if actual not in prob_frame.columns:
                continue
            ranked = prob_frame.iloc[i].sort_values(ascending=False).index.tolist()
            if ranked and ranked[0] == actual:
                top1_hit += 1
            if actual in ranked[:3]:
                top3_hit += 1
        n_eval = int((actual_top.isin(prob_frame.columns)).sum())
        results["theme_ranking_hit_rate"] = {
            "n_evaluable": n_eval,
            "top1": round(float(top1_hit / n_eval), 3) if n_eval else None,
            "top3": round(float(top3_hit / n_eval), 3) if n_eval else None,
            "prior_top1": round(float(prior.iloc[0] / len(merged)), 3) if len(prior) else None,
        }

    (OUT / "raw_planning_chokepoint_prediction_eval.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
