#!/usr/bin/env python3
"""v3 coefficient-attribution as a chokepoint predictor.

For each audited pair with known refusal themes: take the original description,
compute which phrases push frozen v3's risk up (token contributions = tfidf x
coefficients), then map those phrases to refusal themes using per-theme token
vocabularies learned from the retagged refusal corpus. Scored as top-1 / top-3
theme matches against the themes the planner actually cited.

Competes with: theme retrieval from comparables (~54% top-1) and the dumb
most-common-themes prior (~61%).

Output: raw_planning_chokepoint_v3_attribution.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
BUNDLE = ROOT / "05_policy" / "current" / "model_v3" / "national_residential_v3_comparables.joblib"
MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
QUEUE = CURRENT / "full_revision_candidate_queue.csv"
CANONICAL = CURRENT / "canonical_revision_scheme_records.csv"

THEMES = [
    "density_scale", "design_layout", "traffic_access", "residential_amenity",
    "flooding_drainage", "land_use_policy", "premature_or_info_gap",
    "heritage_archaeology", "ecology_trees", "water_wastewater", "other",
]


def ground_truth_pairs() -> pd.DataFrame:
    sys.path.insert(0, str(ROOT / "02_development" / "scripts"))
    from canonical_revision_schemes import normalize_key

    canonical = pd.read_csv(CANONICAL, low_memory=False)
    rows = []
    for _, row in canonical.iterrows():
        themes = [
            t.strip() for t in str(row.get("refusal_themes_original") or "").split(";")
            if t.strip() and t.strip().lower() != "nan"
        ]
        if themes:
            rows.append({"original_case_key": str(row.get("original_case_key")), "themes": themes})
    return pd.DataFrame(rows)


def theme_vocabularies(master: pd.DataFrame, top_n: int = 400) -> dict[str, set[str]]:
    from sklearn.feature_extraction.text import TfidfVectorizer

    frames = []
    for theme in THEMES:
        part = master[master["case_primary_tags"].fillna("").astype(str).str.contains(theme)]
        if part.empty:
            continue
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=20000, min_df=1)
        matrix = vectorizer.fit_transform(part["reasons_joined"].fillna("").astype(str))
        names = np.asarray(vectorizer.get_feature_names_out())
        totals = np.asarray(matrix.sum(axis=0)).ravel()
        order = np.argsort(-totals)[:top_n]
        frames.append((theme, set(names[order].tolist())))
    return dict(frames)


def main() -> None:
    model = joblib.load(BUNDLE)
    pipeline = model["ranking_model"]
    vectorizer = pipeline.named_steps["preprocessor"].named_transformers_["txt"]
    coefficients = pipeline.named_steps["model"].coef_[0]
    feature_names = np.asarray(vectorizer.get_feature_names_out())
    text_weights = coefficients[-len(feature_names):]

    master = pd.read_csv(MASTER, low_memory=False)
    vocab = theme_vocabularies(master)

    pairs = ground_truth_pairs()
    queue = pd.read_csv(QUEUE, low_memory=False)
    description_by_key = dict(zip(queue["original_case_key"].astype(str), queue["original_description"].fillna("")))

    top1_hits = 0
    top3_hits = 0
    evaluated = 0
    examples = []
    for _, row in pairs.iterrows():
        description = str(description_by_key.get(row["original_case_key"], ""))
        if not description.strip():
            continue
        tfidf = vectorizer.transform([description])
        contributions = tfidf.toarray()[0] * text_weights
        positive_tokens = {str(feature_names[i]): float(contributions[i]) for i in np.where(contributions > 0)[0]}
        theme_scores: dict[str, float] = {}
        for theme, tokens in vocab.items():
            score = 0.0
            for token, weight in positive_tokens.items():
                if token in tokens:
                    score += weight
            theme_scores[theme] = score / max(len(tokens), 1)
        ranked = [theme for theme, _ in sorted(theme_scores.items(), key=lambda item: -item[1])][:3]
        actual = row["themes"]
        evaluated += 1
        if ranked and ranked[0] in actual:
            top1_hits += 1
        if set(ranked) & set(actual):
            top3_hits += 1
        if len(examples) < 6:
            examples.append({
                "original_case_key": row["original_case_key"],
                "actual_themes": actual,
                "predicted_top3": ranked,
            })

    payload = {
        "generated": "2026-09-18",
        "ground_truth_pairs": int(len(pairs)),
        "evaluated": evaluated,
        "v3_attribution": {
            "top1_theme_match": round(top1_hits / evaluated, 4) if evaluated else None,
            "top3_theme_match": round(top3_hits / evaluated, 4) if evaluated else None,
        },
        "reference_baselines": {
            "theme_retrieval_top1": 0.5373,
            "theme_retrieval_top3": 0.791,
            "dumb_prior_top1": 0.6119,
            "dumb_prior_top3": 0.8507,
        },
        "examples": examples,
        "caveat": (
            "Attribution maps the description phrases that push v3's risk up onto theme "
            "vocabularies learned from the retagged refusal corpus. Original descriptions "
            "often do not state the refusal grounds, so this measures the ceiling of "
            "description-only chokepoint prediction with v3's own weights."
        ),
    }
    (CURRENT / "raw_planning_chokepoint_v3_attribution.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
