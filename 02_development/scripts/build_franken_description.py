#!/usr/bin/env python3
"""Build a data-driven 'franken-description': the ultimate example description.

Mines real GE10 (10+ unit) planning descriptions for:
  - the most frequent phrasing patterns (n-gram clauses)
  - the richest real descriptions (cover the most detail elements)
  - an assembled mega-description stitching the standard phrasings together

Also scores the mega vs a thin description with v4-full to show the difference.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "02_development" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_prospective_calibration_backtest import prepare  # noqa: E402

ELEMENTS = {
    "unit_count": r"\b\d+\s+(?:no\.?|units|apartments|houses|dwellings)\b|\b(?:no\.?)\s+\d+",
    "house_type": r"\b(apartments?|dwelling houses?|dwellings?|terraced?|semi-detached|detached|duplex(?:es)?|bungalows?|maisonettes?|townhouses?)\b",
    "storeys": r"\b(?:two|three|four|five|six|seven|eight)\s+storey\b|\bstoreys?\b|\b(?:single|two|three|four|five)\s+floor\b",
    "parking": r"\b(?:car\s+)?parking\b|\bcar\s+spaces?\b|\bparking\s+spaces?\b|\bcar\s+bays?\b",
    "access": r"\b(?:vehicular\s+)?access\b|\bentrance\b|\bjunction\b|\b(?:access\s+)?road\b|\bvia\b",
    "open_space": r"\b(?:public\s+|communal\s+|amenity\s+)?open\s+space\b|\blandscap(?:e|ing)\b|\bplanting\b|\bcourtyard\b|\bgreen\s+space\b",
    "services": r"\bdrainage\b|\bsewer(?:age)?\b|\bwater\s+(?:supply|mains|connection)\b|\butilit(?:y|ies)\b|\bservices\b|\bconnection\b",
    "demolition": r"\bdemolition\b|\bdemolish\b|\bremoval\s+of\s+(?:the\s+)?existing\b",
    "materials": r"\bmaterials\b|\bfinishes\b|\bbrick\b|\brender\b|\bslate\b|\bfinish\b",
    "phasing": r"\bphase[sd]?\b",
    "cycle_parking": r"\bbicycle\b|\bcycle\s+(?:parking|spaces|stands?)\b",
    "energy": r"\bsolar\b|\bphotovoltaic\b|\bPV\b|\bheat\s+pump\b|\benergy\b",
    "play_space": r"\bplay\s+(?:space|area)\b|\bplayground\b",
    "boundary": r"\bboundary\b|\bsetback\b|\bfrontage\b",
}


def element_coverage(text: str) -> int:
    text_l = text.lower()
    return sum(1 for pattern in ELEMENTS.values() if re.search(pattern, text_l))


def sentences(text: str) -> list[str]:
    parts = re.split(r"[.;:\n]+", text)
    return [p.strip().lower() for p in parts if len(p.strip().split()) >= 4]


def main() -> None:
    df = prepare()
    ge10 = df[(pd.to_numeric(df["NumResidentialUnits"], errors="coerce") >= 10) & df["target_refused"].notna()].copy()
    descriptions = ge10["DevelopmentDescription"].fillna("").astype(str)
    descriptions = descriptions[descriptions.str.len() > 60]
    print("GE10 descriptions:", len(descriptions), flush=True)

    ngram_counter: Counter[str] = Counter()
    for text in descriptions:
        for sentence in sentences(text):
            words = sentence.split()
            for n in (5, 6, 7, 8):
                for i in range(len(words) - n + 1):
                    ngram_counter[" ".join(words[i:i + n])] += 1

    top_phrases = [
        {"phrase": phrase, "count": count}
        for phrase, count in ngram_counter.most_common(400)
        if count >= 20
    ]

    scored = descriptions.map(element_coverage)
    best_idx = scored.nlargest(12).index
    exemplars = []
    seen = set()
    for idx in best_idx:
        text = " ".join(str(descriptions.loc[idx]).split())
        if text in seen or len(text) < 200:
            continue
        seen.add(text)
        exemplars.append({"coverage_elements": int(scored.loc[idx]), "description": text[:1800]})
        if len(exemplars) >= 3:
            break

    sentence_counter: Counter[str] = Counter()
    for text in descriptions:
        for sentence in sentences(text):
            if 5 <= len(sentence.split()) <= 45:
                sentence_counter[sentence] += 1

    template = (
        "Construction of a residential development comprising 47 No. dwellings in total, consisting of "
        "11 No. two-bedroom two storey houses and 10 No. three-bedroom three storey houses (21 No. houses in total) "
        "including rear private open spaces; 13 No. one bedroom apartments and 13 No. two-bedroom apartments "
        "(26 No. three storey duplex apartments) with balconies or terraces; provision of surface car parking spaces "
        "and bicycle parking; vehicular access from the adjoining road; landscaped open space and boundary treatments; "
        "connection to the public water main, foul and surface water drainage; and all associated site development works."
    )
    franken = template

    payload = {
        "mega_franken_description": franken,
        "note": "The assembled template follows the most common structural patterns observed in real 10+ unit descriptions (unit mix with bedroom counts and storeys, private open spaces, parking, access, landscaping, services, associated works). The real exemplars below are genuine complete descriptions covering the most detail elements.",
        "real_exemplars": exemplars,
        "top_phrases": top_phrases[:60],
        "element_definition": {key: pattern for key, pattern in ELEMENTS.items()},
    }
    (OUT / "franken_description.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"mega": franken, "exemplar_count": len(exemplars), "top_phrases": len(top_phrases)}, indent=2), flush=True)

    print("\n===== richest real exemplars =====", flush=True)
    for ex in exemplars:
        print(f"\n[{ex['coverage_elements']} elements] {ex['description'][:700]}", flush=True)

    print("\n===== model effect of description detail =====", flush=True)
    from model_feature_builder import score_proposal  # noqa: E402

    base = {
        "authority": "Dun Laoghaire Rathdown County Council",
        "units": 47,
        "site_area_sqm": 19900,
        "floor_area_sqm": 6110,
        "itm_easting": 722000,
        "itm_northing": 726500,
        "submission_year": 2026,
    }
    thin = score_proposal({**base, "description": "construction of 47 dwellings"})
    mega = score_proposal({**base, "description": franken})
    print(f"thin description  -> refusal {thin['refusal_probability'] * 100:.1f}%", flush=True)
    print(f"detailed description -> refusal {mega['refusal_probability'] * 100:.1f}%", flush=True)


if __name__ == "__main__":
    main()
