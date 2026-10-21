#!/usr/bin/env python3
"""Find 'practically identical, measurably different' phrase switches.

Generates one-word-substitution pairs within the model's vocabulary
(bedroom<->kitchen style), ranks them by coefficient gap, and measures the
pp effect of the top switches on a standard baseline scheme.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from model_feature_builder import score_proposal  # noqa: E402

SUBSTITUTES = {
    "dwelling": ["dwelling", "extension", "apartment", "house", "bungalow", "flat", "unit", "home"],
    "dwellings": ["dwellings", "extensions", "apartments", "houses", "bungalows", "units", "homes"],
    "extension": ["dwelling", "extension", "apartment", "house", "bungalow"],
    "apartment": ["dwelling", "extension", "apartment", "house", "bungalow", "duplex"],
    "apartments": ["dwellings", "extensions", "apartments", "houses", "bungalows", "duplexes"],
    "house": ["dwelling", "extension", "apartment", "house", "bungalow"],
    "houses": ["dwellings", "extensions", "apartments", "houses", "bungalows"],
    "bungalow": ["dwelling", "extension", "apartment", "house", "bungalow"],
    "kitchen": ["kitchen", "bedroom", "bathroom", "living", "dining", "utility"],
    "bedroom": ["kitchen", "bedroom", "bathroom", "living", "dining", "utility"],
    "bedrooms": ["kitchens", "bedrooms", "bathrooms"],
    "front": ["front", "rear", "side"],
    "rear": ["front", "rear", "side"],
    "side": ["front", "rear", "side"],
    "single": ["single", "two", "three", "four"],
    "two": ["single", "two", "three", "four"],
    "three": ["single", "two", "three", "four"],
    "four": ["single", "two", "three", "four"],
    "storey": ["storey", "floor", "level"],
    "storeys": ["storeys", "floors", "levels"],
    "floor": ["storey", "floor", "level"],
    "semi": ["semi", "terraced", "detached", "end"],
    "detached": ["semi", "terraced", "detached"],
    "terraced": ["semi", "terraced", "detached", "end"],
    "pitched": ["pitched", "flat"],
    "flat": ["pitched", "flat"],
    "timber": ["timber", "brick", "block", "concrete"],
    "brick": ["timber", "brick", "block"],
    "private": ["private", "communal", "public"],
    "communal": ["private", "communal", "public"],
    "public": ["private", "communal", "public"],
    "parking": ["parking", "bicycle"],
    "bicycle": ["parking", "bicycle"],
}

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

ALTERATION_MARKER = r"(extension|alteration|conversion|retention|conservator|porch|window|roof|dormer|garage|rear|existing)"


def main() -> None:
    vocab = pd.read_csv(OUT / "text_vocabulary_coefficients.csv")
    vocab = vocab[vocab["approx_document_frequency"] >= 200].copy()
    index = {row["term"]: row["coefficient"] for _, row in vocab.iterrows()}

    pairs = []
    for term, coef_a in index.items():
        words = term.split()
        if len(words) < 2 or len(words) > 3:
            continue
        for position, word in enumerate(words):
            options = SUBSTITUTES.get(word)
            if not options:
                continue
            for alternate in options:
                if alternate == word:
                    continue
                variant_words = words.copy()
                variant_words[position] = alternate
                variant = " ".join(variant_words)
                coef_b = index.get(variant)
                if coef_b is None:
                    continue
                gap = coef_b - coef_a
                pairs.append({
                    "from": term,
                    "to": variant,
                    "coef_from": round(coef_a, 3),
                    "coef_to": round(coef_b, 3),
                    "coef_gap": round(gap, 3),
                })
    pairs = [p for p in pairs if abs(p["coef_gap"]) >= 0.4]
    pairs.sort(key=lambda p: -abs(p["coef_gap"]))
    deduped = []
    seen = set()
    for pair in pairs:
        key = frozenset((pair["from"], pair["to"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(pair)
    print(f"substitution pairs with |gap| >= 0.4: {len(deduped)}", flush=True)

    baseline_risk = score_proposal(BASELINE)["refusal_probability"]
    for pair in deduped[:16]:
        risk_a = score_proposal({**BASELINE, "description": f"{BASELINE['description']} with {pair['from']}"})["refusal_probability"]
        risk_b = score_proposal({**BASELINE, "description": f"{BASELINE['description']} with {pair['to']}"})["refusal_probability"]
        pair["pp_from"] = round((risk_a - baseline_risk) * 100, 1)
        pair["pp_to"] = round((risk_b - baseline_risk) * 100, 1)
        pair["pp_switch"] = round((risk_b - risk_a) * 100, 1)

    print(f"\nbaseline: {baseline_risk * 100:.1f}%", flush=True)
    print("=== biggest practically-identical switches ===", flush=True)
    for pair in deduped[:16]:
        print(
            f"  {pair['from']:32s} -> {pair['to']:32s}  coef gap {pair['coef_gap']:+.2f}   "
            f"pp: {pair.get('pp_from', 0):+.1f} -> {pair.get('pp_to', 0):+.1f}   switch {pair.get('pp_switch', 0):+.1f}pp",
            flush=True,
        )
    (OUT / "minimal_phrase_switches.json").write_text(json.dumps({
        "baseline_refusal_probability": baseline_risk,
        "pairs": deduped[:40],
        "note": "One-word substitution within the model vocabulary; pp measured by inserting each phrase into the standard 12-unit baseline. Switch = effect of choosing 'to' instead of 'from'.",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
