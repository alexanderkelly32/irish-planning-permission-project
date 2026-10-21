#!/usr/bin/env python3
"""Wow-facts: real observed refusal rates for folk-belief pairs.

Computes P(refused | description contains X) vs P(refused | contains Y) from
the actual register decisions - rates people already half-believe, with the
number attached.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_prospective_calibration_backtest import prepare  # noqa: E402


def rate(mask: pd.Series) -> dict:
    sel = df[mask & df["target_refused"].notna()]
    if len(sel) < 50:
        return None
    return {"refusal_rate": round(float(sel["target_refused"].mean()), 4), "n": int(len(sel))}


def fact(label: str, mask_a: pd.Series, mask_b: pd.Series) -> dict | None:
    a = rate(mask_a)
    b = rate(mask_b)
    if a is None or b is None:
        return None
    ratio = a["refusal_rate"] / b["refusal_rate"] if b["refusal_rate"] > 0 else None
    diff = (a["refusal_rate"] - b["refusal_rate"]) * 100
    return {
        "label": label,
        "a": a,
        "b": b,
        "ratio": round(ratio, 2) if ratio else None,
        "diff_pp": round(diff, 1),
    }


def main() -> None:
    global df
    df = prepare()
    df = df[df["target_refused"].notna()].copy()
    desc = df["DevelopmentDescription"].fillna("").astype(str).str.lower()
    has = lambda pattern: desc.str.contains(pattern, regex=True)
    base_rate = float(df["target_refused"].mean())

    facts = []
    candidates = [
        ("Kitchen extensions are dodgy; bedroom extensions aren't",
         has(r"kitchen\s+extension"), has(r"bedroom\s+extension")),
        ("Timber-frame is refused more than masonry",
         has(r"timber"), has(r"\b(?:masonry|brick|render)\b")),
        ("Bungalows are refused more than houses",
         has(r"bungalow"), has(r"\bhouse[s]?\b")),
        ("'Housing development' is refused more than 'residential development'",
         has(r"housing\s+development"), has(r"residential\s+development")),
        ("Two-storey extensions are refused more than single-storey",
         has(r"two\s+storey\s+extension"), has(r"single\s+storey\s+extension")),
        ("Conservatories nearly never refuse",
         has(r"conservatory"), pd.Series(True, index=df.index)),
        ("Semi-detached is safer than detached",
         has(r"semi[- ]detached"), has(r"\bdetached\b")),
        ("80+ unit schemes refuse less than 10-19 unit schemes",
         (pd.to_numeric(df["NumResidentialUnits"], errors="coerce") >= 80),
         (pd.to_numeric(df["NumResidentialUnits"], errors="coerce").between(10, 19))),
        ("One-off houses in DLR refuse at double the national one-off rate",
         has(r"one[- ]?off") & (df["PlanningAuthority"] == "Dun Laoghaire Rathdown County Council"),
         has(r"one[- ]?off")),
        ("Apartment schemes refuse more than house schemes",
         has(r"apartments?"), has(r"\bhouse[s]?\b")),
        ("Extensions refuse far less than new builds",
         has(r"extension"), has(r"new\s+(?:dwelling|house|build)")),
        ("Porch applications are nearly free",
         has(r"porch"), pd.Series(True, index=df.index)),
    ]
    for label, mask_a, mask_b in candidates:
        result = fact(label, mask_a, mask_b)
        if result:
            facts.append(result)

    words = desc.str.split().str.len()
    refused_words = words[df["target_refused"] == 1]
    granted_words = words[df["target_refused"] == 0]
    facts.append({
        "label": "Refused applications are described in fewer words",
        "a": {"refusal_rate": float(refused_words.median()), "n": int(len(refused_words)), "unit": "median words"},
        "b": {"refusal_rate": float(granted_words.median()), "n": int(len(granted_words)), "unit": "median words"},
        "ratio": None,
        "diff_pp": None,
    })

    payload = {"national_base_refusal_rate": round(base_rate, 4), "facts": facts}
    (OUT / "wow_facts.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"national base refusal rate: {base_rate * 100:.1f}%\n")
    for f in facts:
        a, b = f["a"], f["b"]
        if f["diff_pp"] is not None:
            print(f"{f['label']}")
            print(f"    {a['refusal_rate'] * 100:.1f}% vs {b['refusal_rate'] * 100:.1f}%  ({f['diff_pp']:+.1f}pp, {f['ratio']}x)  n={a['n']} / {b['n']}")
        else:
            print(f"{f['label']}: median {a['refusal_rate']} vs {b['refusal_rate']} words (n={a['n']} / {b['n']})")


if __name__ == "__main__":
    main()
