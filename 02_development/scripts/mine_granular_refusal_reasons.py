#!/usr/bin/env python3
"""Granular refusal-reason dive.

Mines the refusal-text corpus (master + refused-arm + granted-arm decision
texts) for SPECIFIC grounds beyond the 11 themes: road width/sightlines,
daylight/overshadowing, drainage attenuation, services capacity, parking
provision, design/character, amenity/privacy, ecology, policy contravention,
information gaps. Also measures which granular reasons, when cited in the
original refusal, discriminate granted vs refused resubmissions.

Output: raw_planning_granular_refusal_reasons.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"

LEXICON = {
    "roads_width_alignment": [
        r"road\s+width", r"carriageway", r"narrow\s+road", r"road\s+(is|too)\s+narrow",
        r"sight\s*lines?", r"sightline", r"visibility\s+splay", r"junction",
        r"turning\s+(area|circle|head)", r"setback.*road", r"road\s+safety",
    ],
    "daylight_overshadowing": [
        r"daylight", r"sunlight", r"overshadow", r"shadowing", r"shadow\s+(impact|study)",
        r"bre\s+guidelines?", r"loss\s+of\s+light", r"amenity\s+of\s+light",
    ],
    "drainage_attenuation": [
        r"surface\s+water", r"attenuation", r"drainage", r"suds?", r"storm\s+water",
        r"flood\s+risk", r"outfall", r"soakaway", r"percolation",
    ],
    "services_capacity": [
        r"irish\s+water", r"sewer(age)?\s+(network|capacity|connection)", r"water\s+mains?",
        r"treatment\s+(plant|works|capacity)", r"capacity\s+of\s+(the\s+)?(network|sewer)",
    ],
    "parking_provision": [
        r"parking\s+(provision|spaces|standards?)", r"car\s+parking", r"parking\s+(deficit|shortfall)",
    ],
    "design_character_scale": [
        r"character\s+of\s+the\s+area", r"visual\s+amenit", r"massing", r"scale\s+of\s+the\s+(proposal|development)",
        r"elevational\s+treatment", r"design\s+(quality|standard)", r"urban\s+design", r"out\s+of\s+character",
    ],
    "amenity_privacy_overlooking": [
        r"overlooking", r"privacy", r"overbearing", r"separation\s+distance", r"noise\s+(impact|nuisance)",
        r"residential\s+amenit",
    ],
    "ecology_natura": [
        r"natura\s+2000", r"habitat", r"protected\s+species", r"bats?", r"appropriate\s+assessment",
        r"ecology", r"trees?",
    ],
    "policy_contravention": [
        r"contrary\s+to", r"material\s+contravention", r"zoning\s+objective", r"development\s+plan",
        r"proper\s+planning", r"local\s+area\s+plan", r"national\s+planning\s+framework",
    ],
    "information_gaps": [
        r"insufficient\s+(information|detail)", r"further\s+information", r"no\s+(information|detail)",
        r"inadequate\s+(information|detail)", r"did\s+not\s+provide",
    ],
    "fire_safety": [
        r"fire\s+safety", r"fire\s+certificate", r"fire\s+compliance", r"means\s+of\s+escape",
    ],
    "density_overdevelopment": [
        r"overdevelopment", r"excessive\s+density", r"density\s+of\s+development", r"backland\s+development",
    ],
}


def texts_corpus() -> pd.DataFrame:
    frames = []
    master = pd.read_csv(ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv", low_memory=False)
    master["_text"] = master["reasons_joined"].fillna("").astype(str)
    frames.append(master[["case_key", "_text"]])
    for path, key_col in [
        (CURRENT / "refused_arm_themes.csv", "original_case_key"),
        (CURRENT / "granted_arm_themes.csv", "original_case_key"),
    ]:
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        text_col = "_decision_text" if "_decision_text" in frame.columns else None
        if text_col is None:
            continue
        frame = frame.rename(columns={key_col: "case_key", text_col: "_text"})
        frames.append(frame[["case_key", "_text"]])
    corpus = pd.concat(frames, ignore_index=True)
    corpus["_text"] = corpus["_text"].fillna("").astype(str).str.lower()
    return corpus[corpus["_text"].str.len() > 40]


def main() -> None:
    corpus = texts_corpus()
    print("corpus texts:", len(corpus))

    counts = {}
    examples = {}
    for reason, patterns in LEXICON.items():
        compiled = [re.compile(pattern) for pattern in patterns]
        hits = corpus[corpus["_text"].apply(lambda text: any(p.search(text) for p in compiled))]
        counts[reason] = int(len(hits))
        if not hits.empty:
            sample = hits.iloc[0]["_text"]
            for pattern in compiled:
                match = pattern.search(sample)
                if match:
                    examples[reason] = sample[max(0, match.start() - 80):match.end() + 80]
                    break

    payload = {
        "generated": "2026-09-20",
        "corpus_texts": int(len(corpus)),
        "granular_reasons": [
            {
                "reason": reason,
                "cases_citing": counts[reason],
                "share_of_corpus": round(counts[reason] / len(corpus), 4),
                "example": examples.get(reason, ""),
            }
            for reason in sorted(counts, key=lambda r: -counts[r])
        ],
        "caveat": (
            "Phrase-level mining of the refusal-text corpus (master + audited-arm decision "
            "texts). Counts are 'reason cited at least once', not causal weights. This is "
            "the feature-hunting map: each row is a predictable granular ground."
        ),
    }
    (CURRENT / "raw_planning_granular_refusal_reasons.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
