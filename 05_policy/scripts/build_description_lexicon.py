#!/usr/bin/env python3
"""Definitive description lexicon: deterministic phrase categories.

Each category is a regex word-list grounded in the planning vocabulary.
lexicon_features() turns a description series into per-category counts.
"""
from __future__ import annotations

import re

import pandas as pd

CATEGORIES: dict[str, list[str]] = {
    "extension": [r"\bextension[s]?\b", r"\bextend(?:ing|ed)?\b"],
    "alteration": [r"\balteration[s]?\b", r"\belevational\s+changes?\b", r"\binternal\s+modifications?\b"],
    "conversion": [r"\bconversion[s]?\b", r"\bchange\s+of\s+use\b", r"\bconvert(?:ing|ed)?\b"],
    "retention": [r"\bretention\b"],
    "conservatory_porch": [r"\bconservator(y|ies)\b", r"\bporch(?:es)?\b", r"\bsunroom[s]?\b", r"\bbay\s+window[s]?\b"],
    "new_house": [r"\bnew\s+(?:dwelling|house|home)[s]?\b", r"\bone[- ]?off\b", r"\bsingle\s+dwelling[s]?\b"],
    "apartment": [r"\bapartments?\b", r"\bflats?\b", r"\bmaisonettes?\b", r"\bresidential\s+units?\b"],
    "duplex": [r"\bduplex(?:es)?\b"],
    "semi_detached": [r"\bsemi[- ]detached\b"],
    "detached": [r"\bdetached\b"],
    "terraced": [r"\bterrac(?:ed|e)[s]?\b"],
    "storeys": [r"\b(?:single|two|three|four|five|six|seven|eight)[- ]storey\b", r"\bstoreys?\b", r"\b(?:single|two|three|four|five)[- ]floor\b"],
    "bedrooms": [r"\b(?:one|two|three|four|five|six)[- ]?bedroom[s]?\b", r"\bbedrooms?\b"],
    "parking": [r"\b(?:car|surface|bicycle|cycle|basement|underground)?\s*parking\b", r"\bcar\s+(?:spaces?|bays?|ports?)\b", r"\bbicycle\s+(?:spaces?|stands?|parking)\b"],
    "access_road": [r"\b(?:vehicular|pedestrian)?\s*access\b", r"\bentrance[s]?\b", r"\bjunction[s]?\b", r"\b(?:access|estate|internal)?\s*road[s]?\b", r"\bfootpath[s]?\b"],
    "open_space_amenity": [r"\b(?:public|communal|amenity|landscaped|open)\s+space[s]?\b", r"\blandscap(?:e|ing)?\b", r"\bplanting\b", r"\bplay(?:ground|space|area)\b", r"\bboundary\s+treatments?\b"],
    "services_drainage": [r"\bdrainage\b", r"\bsewer(?:age)?\b", r"\bfoul\s+(?:and\s+surface\s+)?water\b", r"\bwater\s+(?:main|supply|connection)\b", r"\butilit(?:y|ies)\b", r"\bconnection[s]?\s+to\b"],
    "materials": [r"\bmasonry\b", r"\bbrick[s]?\b", r"\brender(?:ed)?\b", r"\bstone\b", r"\btimber\b", r"\bfinish(?:es)?\b", r"\brooflights?\b"],
    "demolition": [r"\bdemolition\b", r"\bdemolish\b", r"\bremoval\s+of\s+(?:the\s+)?existing\b", r"\bdecommission\b"],
    "community_retail": [r"\bcommunity\s+(?:facilit(?:y|ies)|centre|hall)\b", r"\bcreche\b", r"\bretail\s+unit[s]?\b", r"\bshop[s]?\b"],
    "flood_water": [r"\bflood\b", r"\bwastewater\b", r"\bseptic\s+tank[s]?\b", r"\btreatment\s+(?:unit|system)\b", r"\bdrainage\s+works?\b"],
}

_COMPILED = {name: [re.compile(pattern, re.IGNORECASE) for pattern in patterns] for name, patterns in CATEGORIES.items()}

TYPE_CODE_RE = re.compile(r"\btypes?\s*[a-z]?\d?\b|\btype\s+[a-z]\d?\b|\(type[s]?\s+[a-z0-9 ]+\)", re.IGNORECASE)
BED_RE = re.compile(r"\d+\s*[- ]?bed", re.IGNORECASE)
STOREY_RE = re.compile(r"\d+\s*[- ]?storey", re.IGNORECASE)
FORM_RE = re.compile(r"\b(terrace[sd]?|semi[- ]detached|detached|duplex(?:es)?|maisonettes?|bungalows?)\b", re.IGNORECASE)


def type_code_features(descriptions: pd.Series) -> pd.DataFrame:
    """Parse SHD-style type-coded descriptions into structured counts."""
    out = pd.DataFrame(index=descriptions.index)
    text = descriptions.fillna("").astype(str)
    out["tparse_has_type_codes"] = text.str.contains(r"\btype[s]?\b", case=False, regex=True).astype(float)
    out["tparse_type_code_mentions"] = text.str.count(TYPE_CODE_RE).astype(float)
    out["tparse_bed_mentions"] = text.str.count(BED_RE).astype(float)
    out["tparse_storey_mentions"] = text.str.count(STOREY_RE).astype(float)
    out["tparse_form_mentions"] = text.str.count(FORM_RE).astype(float)
    out["tparse_structure_density"] = (out["tparse_type_code_mentions"] + out["tparse_bed_mentions"] + out["tparse_storey_mentions"]).astype(float)
    return out


def lexicon_features(descriptions: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame(index=descriptions.index)
    for name, patterns in _COMPILED.items():
        counts = sum(descriptions.fillna("").astype(str).str.count(pattern) for pattern in patterns)
        out[f"lex_{name}"] = counts.astype(float)
    out["lex_total_matches"] = out.sum(axis=1)
    return out


if __name__ == "__main__":
    from build_prospective_calibration_backtest import prepare

    data = prepare()
    features = lexicon_features(data["DevelopmentDescription"].fillna(""))
    print("coverage: rows with >= 1 match:", round(float((features["lex_total_matches"] > 0).mean()), 3))
    print("per-category non-zero share:")
    for column in features.columns[:-1]:
        print(f"  {column:28s} {(features[column] > 0).mean():.3f}")
