#!/usr/bin/env python3
"""Phrase-level pp effects: add each top phrase to a standard baseline scheme and
measure the change in refusal probability.

Also exports the full vocabulary with coefficients to
05_policy/current/text_vocabulary_coefficients.csv
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from model_feature_builder import score_proposal  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"
N_TRAIN_DOCS = 183439
BASELINE = {
    "authority": "Dun Laoghaire Rathdown County Council",
    "description": "construction of a residential development with associated site works",
    "units": 12,
    "site_area_sqm": 4000,
    "floor_area_sqm": 2400,
    "itm_easting": 722000,
    "itm_northing": 726500,
    "submission_year": 2026,
}
CONNECTORS = {
    "apartment": "construction of an apartment development",
    "apartments": "construction of an apartment development",
    "balcony": "construction of a residential development with balconies and associated site works",
    "bedroom": "construction of a residential development with 2 bedroom units and associated site works",
    "bedrooms": "construction of a residential development with 2 bedroom units and associated site works",
    "bungalow": "construction of bungalows and associated site works",
    "dwellings": "construction of a residential development of dwellings with associated site works",
    "garage": "construction of a residential development with a garage and associated site works",
    "mobile": "construction of a residential development of mobile homes with associated site works",
    "porch": "construction of a residential development with porches and associated site works",
    "residential": "construction of a residential development with associated site works",
    "rooflight": "construction of a residential development with rooflights and associated site works",
    "rooflights": "construction of a residential development with rooflights and associated site works",
    "single storey dwelling": "construction of single storey dwellings and associated site works",
    "single storey extension": "construction of a single storey extension to a residential development",
    "storey": "construction of a two storey residential development with associated site works",
    "timber": "construction of a timber residential development with associated site works",
    "treatment": "construction of a residential development with wastewater treatment and associated site works",
    "window": "construction of a residential development with window replacement and associated site works",
}


def main() -> None:
    artifact = joblib.load(ARTIFACT)
    pre = artifact["ranking_model"].named_steps["preprocessor"]
    model = artifact["ranking_model"].named_steps["model"]
    vectorizer = pre.named_transformers_["txt"]
    names = pre.get_feature_names_out()
    coefs = model.coef_[0]
    vocabulary = vectorizer.vocabulary_
    idf = vectorizer.idf_

    rows = []
    for full, coef in zip(names, coefs):
        if not full.startswith("txt__"):
            continue
        term = full.split("__", 1)[1]
        df_approx = max(1.0, N_TRAIN_DOCS * math.exp(-idf[vocabulary[term]]))
        rows.append({"term": term, "coefficient": round(float(coef), 5), "approx_document_frequency": int(df_approx)})
    vocab_frame = pd.DataFrame(rows).sort_values("coefficient", ascending=False)
    vocab_frame.to_csv(OUT / "text_vocabulary_coefficients.csv", index=False)
    print(f"full vocabulary saved: {len(vocab_frame)} phrases -> text_vocabulary_coefficients.csv")

    baseline_risk = score_proposal(BASELINE)["refusal_probability"]
    print(f"baseline refusal: {baseline_risk * 100:.1f}%")

    candidates_raise = vocab_frame[vocab_frame["approx_document_frequency"] >= 200].head(60)["term"].tolist()
    candidates_lower = vocab_frame[vocab_frame["approx_document_frequency"] >= 200].tail(60)["term"].tolist()
    effects = []
    seen = set()
    for term in candidates_raise + candidates_lower:
        if term in seen or " " not in term and len(term) < 4:
            continue
        seen.add(term)
        if term in CONNECTORS:
            variant_desc = CONNECTORS[term]
        else:
            variant_desc = f"{BASELINE['description']} with {term}"
        risk = score_proposal({**BASELINE, "description": variant_desc})["refusal_probability"]
        effects.append({
            "term": term,
            "coefficient": float(vocab_frame[vocab_frame["term"] == term]["coefficient"].iloc[0]),
            "pp_change_vs_baseline": round((risk - baseline_risk) * 100, 2),
            "example_description": variant_desc,
        })
    effects = sorted(effects, key=lambda r: -r["pp_change_vs_baseline"])
    (OUT / "text_phrase_pp_effects.json").write_text(json.dumps({
        "baseline": BASELINE,
        "baseline_refusal_probability": baseline_risk,
        "effects": effects,
        "note": "Each phrase was inserted into the same standard baseline scheme and the model rescored; the pp change is phrase-in-this-context, not universal.",
    }, indent=2), encoding="utf-8")

    print("\n=== biggest RAISERS (pp vs baseline) ===")
    for r in effects[:20]:
        print(f"  {r['term']:38s} {r['pp_change_vs_baseline']:+6.2f}pp   coef {r['coefficient']:+.2f}")
    print("\n=== biggest LOWERERS (pp vs baseline) ===")
    for r in effects[-20:]:
        print(f"  {r['term']:38s} {r['pp_change_vs_baseline']:+6.2f}pp   coef {r['coefficient']:+.2f}")


if __name__ == "__main__":
    main()
