#!/usr/bin/env python3
"""Chokepoint prediction by unit-size bands.

For thresholds 10/25/50/100 units: how do the dumb prior and the
comparable-theme retrieval score on top-1/top-3 theme match, and how does the
band-adapted prior (themes most common within that size band) do? The band
prior is the honest bar: it uses only size, not the case text.

Output: raw_planning_chokepoint_by_units.json
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

sys.path.insert(0, str(ROOT / "02_development" / "scripts"))
from canonical_revision_schemes import normalize_key  # noqa: E402

sys.path.insert(0, str(ROOT / "06_copilot" / "scripts"))
from precedent_copilot_logic import clean_text  # noqa: E402

MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
QUEUE = CURRENT / "full_revision_candidate_queue.csv"
CANONICAL = CURRENT / "canonical_revision_scheme_records.csv"
REFUSED_THEMES = CURRENT / "refused_arm_themes.csv"
GRANTED_THEMES = CURRENT / "granted_arm_themes.csv"


def build_ground_truth() -> pd.DataFrame:
    canonical = pd.read_csv(CANONICAL, low_memory=False)
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
        themes = [t.strip() for t in tags.split(";") if t.strip() and t.strip().lower() != "nan"]
        if themes:
            rows.append({"original_case_key": key, "themes": themes})
    ground = pd.DataFrame(rows)
    queue = pd.read_csv(QUEUE, low_memory=False)
    units_by_key = dict(zip(queue["original_case_key"].astype(str), pd.to_numeric(queue["original_units"], errors="coerce")))
    ground["original_units"] = ground["original_case_key"].map(lambda k: units_by_key.get(k))
    return ground


def main() -> None:
    ground = build_ground_truth()
    queue = pd.read_csv(QUEUE, low_memory=False)
    description_by_key = dict(zip(queue["original_case_key"].astype(str), queue["original_description"].fillna("")))

    master = pd.read_csv(MASTER, low_memory=False)
    master = master[master["reasons_joined"].fillna("").astype(str).str.strip().ne("")].copy()
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=30000, min_df=2)
    master_matrix = vectorizer.fit_transform(master["reasons_joined"].fillna("").astype(str).map(clean_text))
    master_tags = [
        [t.strip() for t in str(tags).split(";") if t.strip()]
        for tags in master["case_primary_tags"].fillna("")
    ]

    prior_counts: dict[str, int] = {}
    for tags in master_tags:
        for tag in tags:
            prior_counts[tag] = prior_counts.get(tag, 0) + 1
    global_prior = [tag for tag, _ in sorted(prior_counts.items(), key=lambda item: -item[1])]

    def retrieval_topk(subset: pd.DataFrame) -> tuple[int, int, int]:
        top1 = top3 = n = 0
        for _, row in subset.iterrows():
            description = clean_text(str(description_by_key.get(row["original_case_key"], "")))
            actual = row["themes"]
            if not description:
                continue
            query = vectorizer.transform([description])
            similarities = cosine_similarity(query, master_matrix)[0]
            order = np.argsort(-similarities)
            weighted: dict[str, float] = {}
            for index in order[:5]:
                weight = float(similarities[index])
                if weight <= 0.02:
                    break
                for tag in master_tags[index]:
                    weighted[tag] = weighted.get(tag, 0.0) + weight
            predicted = [tag for tag, _ in sorted(weighted.items(), key=lambda item: -item[1])[:3]]
            n += 1
            if predicted and predicted[0] in actual:
                top1 += 1
            if set(predicted) & set(actual):
                top3 += 1
        return top1, top3, n

    def prior_topk(subset: pd.DataFrame, ranking: list[str]) -> tuple[int, int, int]:
        top1 = top3 = n = 0
        for _, row in subset.iterrows():
            actual = row["themes"]
            n += 1
            if ranking and ranking[0] in actual:
                top1 += 1
            if set(ranking[:3]) & set(actual):
                top3 += 1
        return top1, top3, n

    thresholds = [10, 25, 50, 100]
    rows = []
    for threshold in thresholds:
        subset = ground[ground["original_units"] >= threshold]
        if subset.empty:
            rows.append({"threshold": threshold, "n": 0})
            continue
        band_counts: dict[str, int] = {}
        for themes in subset["themes"]:
            for theme in themes:
                band_counts[theme] = band_counts.get(theme, 0) + 1
        band_prior = [theme for theme, _ in sorted(band_counts.items(), key=lambda item: -item[1])]
        r1, r3, rn = retrieval_topk(subset)
        g1, g3, gn = prior_topk(subset, global_prior)
        b1, b3, bn = prior_topk(subset, band_prior)
        rows.append({
            "threshold_units": threshold,
            "n": rn,
            "band_top_themes": band_prior[:4],
            "retrieval": {"top1": round(r1 / rn, 4) if rn else None, "top3": round(r3 / rn, 4) if rn else None},
            "global_prior": {"top1": round(g1 / gn, 4) if gn else None, "top3": round(g3 / gn, 4) if gn else None},
            "band_prior": {"top1": round(b1 / bn, 4) if bn else None, "top3": round(b3 / bn, 4) if bn else None},
        })
    payload = {
        "generated": "2026-09-18",
        "ground_truth_pairs_total": int(len(ground)),
        "rows": rows,
        "caveat": (
            "The band prior uses only the size band's own theme frequencies - it is the "
            "bar any text-using method must beat, and it leaks no case text. Subsets are "
            "small at higher thresholds; treat as directional."
        ),
    }
    (CURRENT / "raw_planning_chokepoint_by_units.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
