#!/usr/bin/env python3
"""New-build semantic twins: same-meaning phrase groups with different outcomes.

Groups of practically-synonymous planning phrases; all pairs within a group
are compared by model coefficient and measured pp switch on the standard
baseline scheme.
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

GROUPS = {
    "house form": ["semi detached", "detached", "terraced", "end of terrace", "terraced houses", "detached houses", "semi detached houses"],
    "height": ["single storey", "two storey", "three storey", "four storey", "two storey dwelling", "single storey dwelling", "three storey dwelling"],
    "unit type": ["house", "dwelling", "bungalow", "dwelling house", "houses", "dwellings", "bungalows", "dwelling houses"],
    "apartment type": ["apartments", "flats", "maisonettes", "duplex apartments", "duplexes", "apartment units", "residential units"],
    "parking": ["car parking", "surface car parking", "bicycle parking", "cycle parking", "car parking spaces", "parking spaces"],
    "roof": ["pitched roof", "flat roof", "pitched roofs", "flat roofs"],
    "finish": ["timber", "brick", "render", "stone", "timber frame", "brick finish"],
    "open space": ["private open space", "communal open space", "public open space", "open space", "landscaped open space", "amenity space"],
    "scheme": ["residential development", "housing development", "residential estate", "housing estate", "development"],
    "bedrooms": ["one bedroom", "two bedroom", "three bedroom", "four bedroom", "two bedroom apartments", "one bedroom apartments"],
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


def main() -> None:
    vocab = pd.read_csv(OUT / "text_vocabulary_coefficients.csv")
    vocab = vocab[vocab["approx_document_frequency"] >= 100].copy()
    coefs = {row["term"]: float(row["coefficient"]) for _, row in vocab.iterrows()}

    pairs = []
    for group_name, members in GROUPS.items():
        present = [m for m in members if m in coefs]
        for a in present:
            for b in present:
                if a >= b:
                    continue
                gap = coefs[b] - coefs[a]
                if abs(gap) >= 0.25:
                    pairs.append({"group": group_name, "from": a, "to": b, "coef_from": round(coefs[a], 3), "coef_to": round(coefs[b], 3), "coef_gap": round(gap, 3)})
    pairs.sort(key=lambda p: -abs(p["coef_gap"]))
    print(f"semantic twin pairs found: {len(pairs)}", flush=True)

    baseline_risk = score_proposal(BASELINE)["refusal_probability"]
    measured = []
    for pair in pairs[:20]:
        risk_a = score_proposal({**BASELINE, "description": f"{BASELINE['description']} with {pair['from']}"})["refusal_probability"]
        risk_b = score_proposal({**BASELINE, "description": f"{BASELINE['description']} with {pair['to']}"})["refusal_probability"]
        pair["pp_from"] = round((risk_a - baseline_risk) * 100, 1)
        pair["pp_to"] = round((risk_b - baseline_risk) * 100, 1)
        pair["pp_switch"] = round((risk_b - risk_a) * 100, 1)
        measured.append(pair)
    measured.sort(key=lambda p: -abs(p["pp_switch"]))

    print(f"\nbaseline: {baseline_risk * 100:.1f}%", flush=True)
    print("=== biggest same-meaning switches (new build) ===", flush=True)
    for pair in measured:
        print(
            f"  [{pair['group']}] {pair['from']:24s} -> {pair['to']:24s}  switch {pair['pp_switch']:+.1f}pp "
            f"(coef gap {pair['coef_gap']:+.2f})",
            flush=True,
        )
    (OUT / "newbuild_semantic_twins.json").write_text(json.dumps({
        "baseline_refusal_probability": baseline_risk,
        "pairs": measured,
        "note": "Same-meaning phrase groups within the model vocabulary; pp measured by inserting each phrase into the standard 12-unit baseline.",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
