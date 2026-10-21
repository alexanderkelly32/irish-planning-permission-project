#!/usr/bin/env python3
"""Material risk-lowering phrases report.

Merges: measured pp effects, semantic-twin winners, and newly measured
strong-lowering vocabulary candidates (support >= 300, multi-word), grouped
by domain, measured on the standard 12-unit baseline.
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

DOMAINS = {
    "site / access / infrastructure": r"access|entrance|vehicular|road|junction|footpath|services|drainage|sewer|water|utility|widening|carriageway",
    "extension / alteration": r"extension|alteration|conversion|conservator|porch|dormer|retention",
    "house form / type": r"dwelling|house|bungalow|semi|terraced|detached|storey|flat|apartment|duplex|bedroom",
    "landscaping / amenity": r"landscap|open space|amenity|play|garden|planting|boundary|treatment",
    "misc": r".",
}


def domain_of(term: str) -> str:
    for name, pattern in DOMAINS.items():
        if name == "misc":
            continue
        import re

        if re.search(pattern, term, re.IGNORECASE):
            return name
    return "misc"


def main() -> None:
    effects = json.loads((OUT / "text_phrase_pp_effects.json").read_text(encoding="utf-8"))["effects"]
    twins = json.loads((OUT / "newbuild_semantic_twins.json").read_text(encoding="utf-8"))["pairs"]
    vocab = pd.read_csv(OUT / "text_vocabulary_coefficients.csv")

    rows: dict[str, dict] = {}

    def add(term: str, pp: float, source: str) -> None:
        if pp >= -4.0:
            return
        if term in rows:
            rows[term]["pp"] = min(rows[term]["pp"], pp)
            rows[term]["sources"].add(source)
        else:
            rows[term] = {"term": term, "pp": round(pp, 1), "sources": {source}}

    for r in effects:
        add(r["term"], r["pp_change_vs_baseline"], "measured")
    for pair in twins:
        if pair["pp_switch"] < 0:
            add(pair["to"], pair["pp_switch"], "twin")

    candidates = vocab[(vocab["coefficient"] <= -0.9) & (vocab["approx_document_frequency"] >= 300)]
    candidates = candidates[candidates["term"].str.contains(" ")]
    baseline_risk = score_proposal(BASELINE)["refusal_probability"]
    measured_new = 0
    for term in candidates.head(30)["term"]:
        if term in rows:
            continue
        risk = score_proposal({**BASELINE, "description": f"{BASELINE['description']} with {term}"})["refusal_probability"]
        pp = round((risk - baseline_risk) * 100, 1)
        if pp <= -4.0:
            add(term, pp, "new_measured")
            measured_new += 1
    print(f"newly measured candidates: {measured_new}", flush=True)

    grouped: dict[str, list] = {}
    for row in rows.values():
        grouped.setdefault(domain_of(row["term"]), []).append(row)
    out_payload = {
        "baseline_refusal_probability": baseline_risk,
        "note": "Materially risk-lowering phrases (pp <= -4 on the standard 12-unit baseline). pp is context-dependent; apply only phrases that accurately describe the scheme.",
        "by_domain": {
            k: sorted(({**r, "sources": sorted(r["sources"])} for r in v), key=lambda r: r["pp"])
            for k, v in sorted(grouped.items())
        },
    }
    (OUT / "material_lowering_phrases.json").write_text(json.dumps(out_payload, indent=2), encoding="utf-8")

    print(f"\nbaseline: {baseline_risk * 100:.1f}%", flush=True)
    for domain, items in out_payload["by_domain"].items():
        print(f"\n=== {domain} ===", flush=True)
        for item in items[:12]:
            print(f"  {item['term']:42s} {item['pp']:+.1f}pp   [{', '.join(sorted(item['sources']))}]", flush=True)


if __name__ == "__main__":
    main()
