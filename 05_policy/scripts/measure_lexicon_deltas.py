#!/usr/bin/env python3
"""Measure the pp delta of each lexicon category via a representative phrase
on the standard 12-unit baseline scheme."""
from __future__ import annotations

import json
import sys
from pathlib import Path

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

REPRESENTATIVES = {
    "extension": "single storey extension",
    "alteration": "elevational changes",
    "conversion": "garage conversion",
    "retention": "retention of existing development",
    "conservatory_porch": "conservatory",
    "new_house": "new dwelling",
    "apartment": "apartments",
    "duplex": "duplex apartments",
    "semi_detached": "semi detached",
    "detached": "detached",
    "terraced": "terraced",
    "storeys": "two storey",
    "bedrooms": "bedrooms",
    "parking": "car parking",
    "access_road": "vehicular access",
    "open_space_amenity": "landscaped open space",
    "services_drainage": "connection to public services",
    "materials": "brick finish",
    "demolition": "demolition of existing buildings",
    "community_retail": "community facilities",
    "flood_water_1": "existing septic tank",
    "flood_water_2": "wastewater treatment unit",
}


def main() -> None:
    baseline_risk = score_proposal(BASELINE)["refusal_probability"]
    deltas = []
    for category, phrase in REPRESENTATIVES.items():
        risk = score_proposal({**BASELINE, "description": f"{BASELINE['description']} with {phrase}"})["refusal_probability"]
        deltas.append({
            "category": category,
            "representative_phrase": phrase,
            "delta_pp": round((risk - baseline_risk) * 100, 1),
            "refusal_probability": round(risk, 4),
        })
    deltas.sort(key=lambda r: -abs(r["delta_pp"]))
    (OUT / "lexicon_category_deltas.json").write_text(json.dumps({
        "baseline_refusal_probability": baseline_risk,
        "deltas": deltas,
        "note": "pp change from adding one representative phrase for each lexicon category to the standard 12-unit baseline.",
    }, indent=2), encoding="utf-8")
    print(f"baseline: {baseline_risk * 100:.1f}%", flush=True)
    print("=== biggest category deltas ===", flush=True)
    for d in deltas:
        print(f"  {d['category']:22s} {d['delta_pp']:+6.1f}pp   [{d['representative_phrase']}]", flush=True)


if __name__ == "__main__":
    main()
