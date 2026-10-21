#!/usr/bin/env python3
"""Find the model's 'safest big scheme': search councils, sizes and wording
built from the measured risk-lowering phrases, and report the lowest-refusal
combinations plus the units-vs-minimum-risk trade-off."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from model_feature_builder import score_proposal  # noqa: E402

COUNCILS = [
    "Mayo County Council", "Roscommon County Council", "Leitrim County Council",
    "Longford County Council", "Tipperary County Council", "Donegal County Council",
]
UNITS_LEVELS = [40, 47, 60, 80, 100, 120]
DENSITY = 22.0  # homes per hectare, low band

DESCRIPTIONS = {
    "baseline_detailed": (
        "Construction of a residential development comprising 47 No. dwellings in total, consisting of "
        "11 No. two-bedroom two storey houses and 10 No. three-bedroom three storey houses (21 No. houses in total) "
        "including rear private open spaces; 13 No. one bedroom apartments and 13 No. two-bedroom apartments "
        "(26 No. three storey duplex apartments) with balconies or terraces; provision of surface car parking spaces "
        "and bicycle parking; vehicular access from the adjoining road; landscaped open space and boundary treatments; "
        "connection to the public water main, foul and surface water drainage; and all associated site development works."
    ),
    "safe_v1": (
        "Construction of a residential development comprising single storey semi detached dwellings and bedroom "
        "apartments with landscaping works, a retail unit and community facilities, and associated site works."
    ),
    "safe_v2": (
        "Construction of a residential development of single storey semi detached dwellings, construction domestic, "
        "bedroom apartments and a retail unit with landscaping works and community facilities, site works significant "
        "and all associated site development works."
    ),
}

CENTRES = {
    "Mayo County Council": (540000.0, 810000.0),
    "Roscommon County Council": (585000.0, 780000.0),
    "Leitrim County Council": (560000.0, 835000.0),
    "Longford County Council": (615000.0, 775000.0),
    "Tipperary County Council": (600000.0, 675000.0),
    "Donegal County Council": (585000.0, 910000.0),
}


def main() -> None:
    results = []
    for council in COUNCILS:
        easting, northing = CENTRES[council]
        for units in UNITS_LEVELS:
            site_sqm = units / DENSITY * 10000
            floor_sqm = site_sqm * 0.18
            for desc_name, description in DESCRIPTIONS.items():
                proposal = {
                    "authority": council,
                    "description": description,
                    "units": units,
                    "site_area_sqm": site_sqm,
                    "floor_area_sqm": floor_sqm,
                    "itm_easting": easting,
                    "itm_northing": northing,
                    "submission_year": 2026,
                }
                score = score_proposal(proposal)
                results.append({
                    "council": council,
                    "units": units,
                    "site_area_sqm": round(site_sqm, 0),
                    "description_name": desc_name,
                    "refusal_probability": score["refusal_probability"],
                    "risk_band": score["risk_band"],
                })
    results.sort(key=lambda r: r["refusal_probability"])

    print("=== top 10 safest big schemes ===", flush=True)
    for r in results[:10]:
        print(
            f"  {r['refusal_probability'] * 100:5.1f}%  {r['council']:28s} {r['units']:>4} units "
            f"{r['site_area_sqm'] / 10000:5.1f} ha  [{r['description_name']}]",
            flush=True,
        )

    print("\n=== units vs minimum risk (best council+wording per level) ===", flush=True)
    pareto = {}
    for r in results:
        key = r["units"]
        if key not in pareto or r["refusal_probability"] < pareto[key]["refusal_probability"]:
            pareto[key] = r
    for units in UNITS_LEVELS:
        r = pareto[units]
        print(f"  {units:>4} units -> min {r['refusal_probability'] * 100:5.1f}% ({r['council']}, {r['description_name']})", flush=True)

    best = results[0]
    (OUT / "safest_big_scheme_search.json").write_text(json.dumps({
        "best": best,
        "top10": results[:10],
        "pareto": {str(k): v for k, v in pareto.items()},
        "note": "Model search over councils/sizes/wording built from measured risk-lowering phrases. Not planning advice; the model's optimum only.",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
