#!/usr/bin/env python3
"""Mine the policy-contravention bucket for the SPECIFIC instruments cited.

Extracts named plans, ministerial guidelines, objective/policy codes, zoning
language and section references from the policy-citing refusal texts, and
measures how much of the bucket is pure boilerplate ("proper planning") vs a
specific named instrument. This is the shopping list for a phased policy layer.

Output: raw_planning_policy_contravention_dive.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"

INSTRUMENTS = {
    "county/city development plan (named)": [
        r"(?:county|city)\s+development\s+plan\s+\d{4}\s*[-–]\s*\d{4}",
        r"development\s+plan\s+\d{4}\s*[-–]\s*\d{4}",
    ],
    "development plan (unnamed)": [
        r"development\s+plan", r"the\s+plan\b",
    ],
    "local area plan": [r"local\s+area\s+plan"],
    "national planning framework": [r"national\s+planning\s+framework"],
    "regional spatial & economic strategy": [r"regional\s+spatial\s+(?:and\s+)?economic\s+strategy"],
    "core strategy": [r"core\s+strategy"],
    "zoning objective / land use zoning": [r"zoning\s+objective", r"land\s+use\s+zoning", r"zoned\s+(?:for|residential)"],
    "material contravention": [r"material\s+contravention"],
    "ministerial guidelines (any)": [r"guidelines?", r"ministerial\s+guidelines"],
    "quality housing for sustainable communities": [r"quality\s+housing\s+for\s+sustainable\s+communities"],
    "sustainable rural housing guidelines": [r"sustainable\s+rural\s+housing\s+guidelines"],
    "urban development and building heights": [r"building\s+heights?\s+guidelines", r"urban\s+development\s+and\s+building\s+heights"],
    "design manual urban roads streets (DMURS)": [r"design\s+manual\s+for\s+urban\s+roads", r"dmurs"],
    "flood risk management guidelines": [r"flood\s+risk\s+management\s+guidelines"],
    "apartment guidelines": [r"apartments?\s+guidelines", r"sustainable\s+urban\s+housing"],
    "objective/policy code (e.g. CS02, SH06)": [r"\b(?:objective|policy)\s+[a-z]{1,3}\s?\d{1,3}\b", r"\b[a-z]{2,3}\d{1,3}\b(?=[^a-z0-9]*(?:objective|policy))"],
    "section/chapter reference": [r"section\s+\d+(?:\.\d+)*", r"chapter\s+\d+"],
}

POLICY_GATE = [
    r"contrary\s+to", r"material\s+contravention", r"zoning\s+objective", r"development\s+plan",
    r"proper\s+planning", r"local\s+area\s+plan",
]


def main() -> None:
    corpus_frames = []
    master = pd.read_csv(ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv", low_memory=False)
    master["_text"] = master["reasons_joined"].fillna("").astype(str)
    corpus_frames.append(master[["case_key", "_text"]])
    for path in [CURRENT / "refused_arm_themes.csv", CURRENT / "granted_arm_themes.csv"]:
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        text_col = "_decision_text" if "_decision_text" in frame.columns else None
        if text_col is None:
            continue
        frame = frame.rename(columns={"original_case_key": "case_key", text_col: "_text"})
        corpus_frames.append(frame[["case_key", "_text"]])
    corpus = pd.concat(corpus_frames, ignore_index=True)
    corpus["_text"] = corpus["_text"].fillna("").astype(str)
    corpus = corpus[corpus["_text"].str.len() > 40]
    lowered = corpus["_text"].str.lower()

    gate = re.compile("|".join(POLICY_GATE))
    policy_citing = corpus[lowered.apply(lambda t: bool(gate.search(t)))]
    print("policy-citing texts:", len(policy_citing), "of", len(corpus))

    instruments = {}
    examples = {}
    for name, patterns in INSTRUMENTS.items():
        compiled = [re.compile(p) for p in patterns]
        hits = policy_citing[policy_citing["_text"].str.lower().apply(lambda t: any(p.search(t) for p in compiled))]
        instruments[name] = int(len(hits))
        if not hits.empty:
            sample = hits.iloc[0]["_text"].lower()
            for pattern in compiled:
                match = pattern.search(sample)
                if match:
                    examples[name] = sample[max(0, match.start() - 70):match.end() + 70]
                    break

    named_plan_or_guideline = policy_citing["_text"].str.lower().apply(
        lambda t: bool(re.search(r"development\s+plan\s+\d{4}|guidelines?|local\s+area\s+plan|national\s+planning\s+framework|core\s+strategy|zoning\s+objective|material\s+contravention", t))
    )
    boilerplate_only = int((~named_plan_or_guideline).sum())

    payload = {
        "generated": "2026-09-20",
        "policy_citing_texts": int(len(policy_citing)),
        "pure_boilerplate_no_named_instrument": boilerplate_only,
        "boilerplate_share": round(boilerplate_only / len(policy_citing), 4),
        "instruments_cited": [
            {"instrument": name, "cases_citing": instruments[name], "share_of_policy_bucket": round(instruments[name] / len(policy_citing), 4), "example": examples.get(name, "")}
            for name in sorted(instruments, key=lambda k: -instruments[k])
        ],
        "caveat": "A policy layer must be plan-versioned: instruments cite named plan periods and are superseded on schedule. The actionable layer = named plans + objective codes, not the boilerplate.",
    }
    (CURRENT / "raw_planning_policy_contravention_dive.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
