#!/usr/bin/env python3
"""Which NEW-BUILD/SCALE phrases lower refusal probability?

Filters the full vocabulary to the new-build domain (excluding extension/
alteration/retention wording) and ranks risk-LOWERING phrases, then measures
their pp effect on the standard baseline scheme.
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
from model_feature_builder import score_proposal  # noqa: E402

NEW_BUILD_INCLUDE = re.compile(
    r"(house|dwelling|apart|block|storey|unit|terrac|semi|detached|estate|development|residential|home|"
    r"maisonette|duplex|bungalow|crescent|avenue|drive|road|site|foundation|build|construct|density|"
    r"height|storeys|flat|scheme|land)",
    re.IGNORECASE,
)
ALTERATION_EXCLUDE = re.compile(
    r"(extension|alteration|retention|conversion|conservator|porch|window|roof|dormer|garage|amendment|"
    r"existing|rear|elevation|information|received|duration|change|used|use )",
    re.IGNORECASE,
)
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
    domain = vocab[
        vocab["term"].map(lambda t: bool(NEW_BUILD_INCLUDE.search(t)))
        & ~vocab["term"].map(lambda t: bool(ALTERATION_EXCLUDE.search(t)))
        & (vocab["approx_document_frequency"] >= 200)
    ].copy()
    lowering = domain.sort_values("coefficient").head(40)
    print("new-build domain phrases (support>=200):", len(domain), flush=True)
    print("=== lowest-coefficient new-build phrases ===", flush=True)
    for _, row in lowering.head(25).iterrows():
        print(f"  {row['term']:42s} coef {row['coefficient']:+.3f}  (n={row['approx_document_frequency']})", flush=True)

    baseline_risk = score_proposal(BASELINE)["refusal_probability"]
    effects = []
    for _, row in lowering.head(12).iterrows():
        term = row["term"]
        variant = f"{BASELINE['description']} with {term}"
        risk = score_proposal({**BASELINE, "description": variant})["refusal_probability"]
        effects.append({
            "term": term,
            "coefficient": float(row["coefficient"]),
            "pp_change_vs_baseline": round((risk - baseline_risk) * 100, 2),
        })
    effects = sorted(effects, key=lambda r: r["pp_change_vs_baseline"])
    print(f"\nbaseline: {baseline_risk * 100:.1f}%", flush=True)
    print("=== pp effect of top new-build lowering phrases (standard scheme) ===", flush=True)
    for effect in effects:
        print(f"  {effect['term']:42s} {effect['pp_change_vs_baseline']:+6.2f}pp   coef {effect['coefficient']:+.2f}", flush=True)
    (OUT / "text_newbuild_lowering_phrases.json").write_text(json.dumps({
        "baseline_refusal_probability": baseline_risk,
        "effects": effects,
        "note": "New-build domain = phrases matching house/apartment/storey/site/estate/land etc., excluding extension/alteration/retention wording. pp measured by inserting the phrase into the standard 12-unit baseline.",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
