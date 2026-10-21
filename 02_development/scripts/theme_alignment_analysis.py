#!/usr/bin/env python3
"""Theme-alignment analysis: how accurate is the diagnosis->suggestion pipeline?

Two versions, deliberately separated:
1. own-theme (ceiling): each pair diagnosed from ITS OWN refusal themes - the
   optimistic upper bound (production can never know these).
2. comparable-derived (production): each pair diagnosed from text-similar
   REFUSED CASES in the refusal master (TF-IDF over decision texts), exactly
   the information available for a new submission.

Direction accuracy is measured for both against the pair's actual change.
No theme ever enters a prediction model; this evaluates the recommendation
layer only.

Output: raw_planning_theme_alignment_analysis.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"

sys.path.insert(0, str(ROOT / "06_copilot" / "scripts"))
from theme_lever_bridge import THEME_TO_FIELD  # noqa: E402
from recommendation_grader import MATERIAL_MAGNITUDE, STRUCTURED_TO_SCHEME_FIELD, most_common_change_ranking, rerank_by_themes, theme_conditioned_direction  # noqa: E402
from precedent_copilot_logic import clean_text  # noqa: E402

REFUSAL_MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
QUEUE = CURRENT / "full_revision_candidate_queue.csv"
CANONICAL = CURRENT / "canonical_revision_scheme_records.csv"


def backtest_pairs(canonical: pd.DataFrame) -> list[dict]:
    pairs = []
    for _, row in canonical.iterrows():
        try:
            deltas = json.loads(str(row.get("feature_delta_json") or "{}"))
        except (TypeError, ValueError):
            continue
        changes = {}
        for column, delta in deltas.items():
            if not isinstance(delta, dict):
                continue
            magnitude = abs(float(delta.get("delta", 0.0) or 0.0))
            if magnitude < MATERIAL_MAGNITUDE.get(column, 0.0):
                continue
            field = STRUCTURED_TO_SCHEME_FIELD.get(column, column)
            changes[field] = 1 if float(delta.get("delta", 0.0)) > 0 else -1
        if changes:
            pairs.append({
                "original_case_key": str(row.get("original_case_key")),
                "themes": [t.strip() for t in str(row.get("refusal_themes_original") or "").split(";") if t.strip() and t.strip() != "nan"],
                "changes": changes,
            })
    return pairs


def comparable_diagnosis(description: str, vectorizer, master_matrix, master_tags) -> list[str]:
    if not clean_text(description):
        return []
    query = vectorizer.transform([clean_text(description)])
    similarities = cosine_similarity(query, master_matrix)[0]
    top = np.argsort(-similarities)[:5]
    weighted: dict[str, float] = {}
    for index in top:
        weight = float(similarities[index])
        if weight <= 0.02:
            continue
        for tag in master_tags[index]:
            weighted[tag] = weighted.get(tag, 0.0) + weight
    return [tag for tag, _ in sorted(weighted.items(), key=lambda item: -item[1])[:4]]


def evaluate(pairs: list[dict], canonical: pd.DataFrame, diagnose) -> dict:
    records = canonical
    correct = 0
    evaluated = 0
    diagnosed_any = 0
    for pair in pairs:
        diagnosed = diagnose(pair)
        if diagnosed:
            diagnosed_any += 1
        excluded = {pair["original_case_key"]}
        ranking = most_common_change_ranking(records, exclude_case_keys=excluded)
        reranked = rerank_by_themes(ranking, diagnosed, THEME_TO_FIELD, limit=3, window=6)
        directions = []
        for field, global_direction, _majority, _total in reranked:
            conditioned = theme_conditioned_direction(
                records, field, diagnosed, THEME_TO_FIELD, exclude_case_keys=excluded,
            )
            directions.append((field, conditioned or global_direction))
        if any(
            field in pair["changes"]
            and direction == ("up" if pair["changes"][field] > 0 else "down")
            for field, direction in directions
        ):
            correct += 1
        evaluated += 1
    return {
        "n": evaluated,
        "direction_correct": correct,
        "direction_correct_rate": round(correct / evaluated, 4) if evaluated else None,
        "pairs_with_nonempty_diagnosis": diagnosed_any,
    }


def main() -> None:
    canonical = pd.read_csv(CANONICAL, low_memory=False)
    pairs = backtest_pairs(canonical)

    own_theme = evaluate(pairs, canonical, lambda pair: pair["themes"])

    master = pd.read_csv(REFUSAL_MASTER, low_memory=False)
    master = master[master["reasons_joined"].fillna("").astype(str).str.strip().ne("")].copy()
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=30000, min_df=2)
    master_matrix = vectorizer.fit_transform(master["reasons_joined"].fillna("").astype(str).map(clean_text))
    master_tags = [
        [t.strip() for t in str(tags).split(";") if t.strip()]
        for tags in master["case_primary_tags"].fillna("")
    ]

    queue = pd.read_csv(QUEUE, low_memory=False)
    description_by_key = dict(zip(queue["original_case_key"].astype(str), queue["original_description"].fillna("")))
    comparable = evaluate(
        pairs, canonical,
        lambda pair: comparable_diagnosis(
            str(description_by_key.get(pair["original_case_key"], "")),
            vectorizer, master_matrix, master_tags,
        ),
    )

    results = {
        "generated": "2026-09-14",
        "pairs": len(pairs),
        "own_theme_ceiling": own_theme,
        "comparable_derived_production": comparable,
        "production_gap_vs_ceiling": round(
            (own_theme["direction_correct_rate"] or 0) - (comparable["direction_correct_rate"] or 0), 4,
        ),
        "caveat": (
            "The comparable-derived diagnosis uses the 1,411-case theme-tagged refusal "
            "master as the comparable pool (a subset of the national index). Neither "
            "theme set ever enters a prediction model - this evaluates the "
            "recommendation layer only. n is small; rates carry wide uncertainty."
        ),
    }
    (CURRENT / "raw_planning_theme_alignment_analysis.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
