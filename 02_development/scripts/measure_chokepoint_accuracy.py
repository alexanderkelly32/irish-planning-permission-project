#!/usr/bin/env python3
"""Chokepoint-prediction measurement.

Ground truth: audited refused->granted pairs whose ORIGINAL application has
human-verified refusal themes (the planner's actual cited choke points).

Diagnosis under test (the production path): retrieve text-similar refused cases
from the theme-tagged refusal master, weight their themes by similarity, and
predict the pair's choke points. Scored as top-1 / hit@3 theme matches against
the actual cited themes.

Also reports the dumb prior (most common themes overall) as the baseline the
diagnosis must beat, and the coverage limitation (only 1,411 cases are tagged).

Output: raw_planning_chokepoint_accuracy.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"

sys_import = __import__("sys")
sys_import.path.insert(0, str(ROOT / "06_copilot" / "scripts"))
from precedent_copilot_logic import clean_text  # noqa: E402

MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
QUEUE = CURRENT / "full_revision_candidate_queue.csv"
CANONICAL = CURRENT / "canonical_revision_scheme_records.csv"
REFUSED_THEMES = CURRENT / "refused_arm_themes.csv"
GRANTED_THEMES = CURRENT / "granted_arm_themes.csv"


def theme_pool() -> pd.DataFrame:
    """Master + arm theme tables merged into one tagged comparable pool."""
    frames = [pd.read_csv(MASTER, low_memory=False)]
    for path in (REFUSED_THEMES, GRANTED_THEMES):
        if path.exists():
            extra = pd.read_csv(path, low_memory=False)
            extra = extra.rename(columns={})
            frames.append(extra)
    pool = pd.concat(frames, ignore_index=True)
    pool["case_key"] = pool["case_key"].fillna("").astype(str)
    pool = pool[pool["case_key"] != ""].drop_duplicates("case_key", keep="first")
    return pool


def theme_by_key(pool: pd.DataFrame) -> dict[str, str]:
    return dict(zip(pool["case_key"], pool["case_primary_tags"].fillna("")))


def actual_themes(canonical: pd.DataFrame) -> pd.DataFrame:
    sys_import.path.insert(0, str(ROOT / "02_development" / "scripts"))
    from canonical_revision_schemes import normalize_key

    arm_lookup: dict[str, str] = {}
    for path in (REFUSED_THEMES, GRANTED_THEMES):
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        for _, row in frame.iterrows():
            key = normalize_key(row.get("original_case_key"))
            tags = str(row.get("case_primary_tags") or "").strip()
            if key and tags:
                arm_lookup[key] = tags

    rows = []
    for _, row in canonical.iterrows():
        key = str(row.get("original_case_key"))
        tags = str(row.get("refusal_themes_original") or "")
        if not tags.strip() or tags.strip().lower() == "nan":
            tags = arm_lookup.get(normalize_key(key), "")
        themes = [
            t.strip() for t in tags.split(";")
            if t.strip() and t.strip().lower() != "nan"
        ]
        if themes:
            rows.append({"original_case_key": key, "themes": themes})
    return pd.DataFrame(rows)


def main() -> None:
    canonical = pd.read_csv(CANONICAL, low_memory=False)
    ground_truth = actual_themes(canonical)
    queue = pd.read_csv(QUEUE, low_memory=False)
    description_by_key = dict(zip(queue["original_case_key"].astype(str), queue["original_description"].fillna("")))

    master = pd.read_csv(MASTER, low_memory=False)
    master = master[master["reasons_joined"].fillna("").astype(str).str.strip().ne("")].copy()
    master["_text"] = master["reasons_joined"]
    master["_tags"] = master["case_primary_tags"]
    for path in (REFUSED_THEMES, GRANTED_THEMES):
        if not path.exists():
            continue
        extra = pd.read_csv(path, low_memory=False)
        if "case_key" not in extra.columns and "original_case_key" in extra.columns:
            extra = extra.rename(columns={"original_case_key": "case_key"})
        text_column = "_decision_text" if "_decision_text" in extra.columns else ("decision_text" if "decision_text" in extra.columns else None)
        if text_column is None:
            continue
        extra = extra[extra[text_column].fillna("").astype(str).str.strip().ne("")].copy()
        if extra.empty:
            continue
        extra["_text"] = extra[text_column]
        extra["_tags"] = extra["case_primary_tags"]
        master = pd.concat([master, extra[["case_key", "_text", "_tags"]]], ignore_index=True)
    master = master.drop_duplicates("case_key", keep="first")
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=30000, min_df=2)
    master_matrix = vectorizer.fit_transform(master["_text"].fillna("").astype(str).map(clean_text))
    master_tags = [
        [t.strip() for t in str(tags).split(";") if t.strip()]
        for tags in master["_tags"].fillna("")
    ]

    prior_counts: dict[str, int] = {}
    for tags in master_tags:
        for tag in tags:
            prior_counts[tag] = prior_counts.get(tag, 0) + 1
    prior_ranking = [tag for tag, _ in sorted(prior_counts.items(), key=lambda item: -item[1])]

    top1_hits = 0
    top3_hits = 0
    evaluated = 0
    no_comparables = 0
    examples = []
    for _, row in ground_truth.iterrows():
        description = clean_text(str(description_by_key.get(row["original_case_key"], "")))
        actual = row["themes"]
        if not description:
            continue
        query = vectorizer.transform([description])
        similarities = cosine_similarity(query, master_matrix)[0]
        order = np.argsort(-similarities)
        weighted: dict[str, float] = {}
        used = 0
        for index in order[:5]:
            weight = float(similarities[index])
            if weight <= 0.02:
                break
            for tag in master_tags[index]:
                weighted[tag] = weighted.get(tag, 0.0) + weight
            used += 1
        predicted = [tag for tag, _ in sorted(weighted.items(), key=lambda item: -item[1])[:3]]
        evaluated += 1
        if not predicted:
            no_comparables += 1
        if predicted and predicted[0] in actual:
            top1_hits += 1
        if set(predicted) & set(actual):
            top3_hits += 1
        if len(examples) < 6:
            examples.append({
                "original_case_key": row["original_case_key"],
                "actual_themes": actual,
                "predicted_top3": predicted,
            })

    prior_top1 = 0
    prior_top3 = 0
    for _, row in ground_truth.iterrows():
        actual = row["themes"]
        if prior_ranking and prior_ranking[0] in actual:
            prior_top1 += 1
        if set(prior_ranking[:3]) & set(actual):
            prior_top3 += 1

    payload = {
        "generated": "2026-09-17",
        "ground_truth_pairs": int(len(ground_truth)),
        "evaluated": evaluated,
        "diagnosis_retrieval": {
            "top1_theme_match": round(top1_hits / evaluated, 4) if evaluated else None,
            "top3_theme_match": round(top3_hits / evaluated, 4) if evaluated else None,
            "pairs_with_no_comparable_found": no_comparables,
        },
        "dumb_prior_baseline": {
            "top1": round(prior_top1 / evaluated, 4) if evaluated else None,
            "top3": round(prior_top3 / evaluated, 4) if evaluated else None,
            "prior_themes": prior_ranking[:5],
        },
        "examples": examples,
        "caveat": (
            "Ground truth is the ~62 audited pairs whose originals happen to be among the "
            "1,411 theme-tagged refusal cases. The binding constraint is theme COVERAGE "
            "on the national corpus, not the scoring method: tagging more originals is "
            "the fix, not a smarter model. Top-1 means the highest-weighted predicted "
            "theme is among the themes the planner actually cited."
        ),
    }
    (CURRENT / "raw_planning_chokepoint_accuracy.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

