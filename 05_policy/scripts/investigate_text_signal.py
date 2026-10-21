#!/usr/bin/env python3
"""Investigate what the text actually does in v4-full.

Ranks the model's TF-IDF vocabulary by coefficient (risk-positive vs
risk-negative phrases), groups them into themes, and decomposes one
description's full text contribution.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"
N_TRAIN_DOCS = 183439

THEME_PATTERNS = {
    "apartments / height / urban": r"apart|storey|block|duplex|balcon|terrace|urban|infill|backland|density|height",
    "houses / one-off / rural": r"dwelling|bungalow|one.?off|rural|single|house|detached|semi",
    "extension / retention": r"extension|retention|alteration|conversion|conservator",
    "parking / access / road": r"parking|access|road|entrance|junction|car",
    "open space / amenity / design": r"open space|landscap|amenity|separation|overlook|daylight|design|finish|material",
    "services / drainage": r"drainage|sewer|services|water|connection|utilit",
    "demolition / site works": r"demolition|site works|associated|development works",
}


def main() -> None:
    artifact = joblib.load(ARTIFACT)
    pre = artifact["ranking_model"].named_steps["preprocessor"]
    model = artifact["ranking_model"].named_steps["model"]
    vectorizer = pre.named_transformers_["txt"]
    names = pre.get_feature_names_out()
    coefs = model.coef_[0]
    txt_names = [n for n in names if n.startswith("txt__")]
    txt_idx = [i for i, n in enumerate(names) if n.startswith("txt__")]
    vocabulary = vectorizer.vocabulary_
    idf = vectorizer.idf_
    idf_by_index = {index: idf[pos] for term, (pos, index) in {}}
    term_idf = {term: idf[index] for term, index in vocabulary.items()}

    rows = []
    for i, full in zip(txt_idx, txt_names):
        term = full.split("__", 1)[1]
        coef = float(coefs[i])
        df_approx = max(1.0, N_TRAIN_DOCS * math.exp(-term_idf[term]))
        rows.append({
            "term": term,
            "coefficient": coef,
            "odds_multiplier_per_unit_tfidf": round(math.exp(coef), 3),
            "approx_document_frequency": int(df_approx),
        })
    ranked_pos = sorted([r for r in rows if r["coefficient"] > 0 and r["approx_document_frequency"] >= 200], key=lambda r: -r["coefficient"])
    ranked_neg = sorted([r for r in rows if r["coefficient"] < 0 and r["approx_document_frequency"] >= 200], key=lambda r: r["coefficient"])

    theme_summary = {}
    import re  # noqa: E402

    for theme, pattern in THEME_PATTERNS.items():
        pattern_re = re.compile(pattern, re.IGNORECASE)
        members = [r for r in rows if pattern_re.search(r["term"]) and r["approx_document_frequency"] >= 200]
        if not members:
            continue
        mean_coef = float(np.mean([m["coefficient"] for m in members]))
        top = sorted(members, key=lambda m: -m["coefficient"])[:5]
        bottom = sorted(members, key=lambda m: m["coefficient"])[:5]
        theme_summary[theme] = {
            "n_terms": len(members),
            "mean_coefficient": round(mean_coef, 4),
            "direction": "risk-raising" if mean_coef > 0 else "risk-lowering",
            "top_risk_raising": [t["term"] for t in top],
            "top_risk_lowering": [t["term"] for t in bottom],
        }

    payload = {
        "top_30_risk_raising_phrases": ranked_pos[:30],
        "top_30_risk_lowering_phrases": ranked_neg[:30],
        "theme_summary": theme_summary,
        "note": "Coefficients are per TF-IDF-weighted occurrence in the linear model; odds multipliers are indicative, and only phrases appearing in 200+ training descriptions are listed (stable signal, not rare noise).",
    }
    (OUT / "text_signal_investigation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("=== theme summary ===")
    for theme, summary in theme_summary.items():
        print(f"\n{theme} [{summary['direction']}, mean coef {summary['mean_coefficient']:+.3f}, {summary['n_terms']} terms]")
        print(f"  raises: {', '.join(summary['top_risk_raising'][:5])}")
        print(f"  lowers: {', '.join(summary['top_risk_lowering'][:5])}")

    print("\n=== top 15 risk-raising phrases (support >= 200 docs) ===")
    for r in ranked_pos[:15]:
        print(f"  {r['term']:45s} coef {r['coefficient']:+.3f}  x{r['odds_multiplier_per_unit_tfidf']}  (n={r['approx_document_frequency']})")
    print("\n=== top 15 risk-lowering phrases ===")
    for r in ranked_neg[:15]:
        print(f"  {r['term']:45s} coef {r['coefficient']:+.3f}  x{r['odds_multiplier_per_unit_tfidf']}  (n={r['approx_document_frequency']})")


if __name__ == "__main__":
    main()
