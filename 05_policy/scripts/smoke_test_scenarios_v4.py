"""Scenario smoke test: mutate a proposal and rescore with v4-full."""
import json
import sys
from pathlib import Path

ROOT = Path(r"")
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from model_feature_builder import score_proposal  # noqa: E402

base = {
    "authority": "Dun Laoghaire Rathdown County Council",
    "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
    "units": 12,
    "site_area_sqm": 4000,
    "floor_area_sqm": 2400,
    "itm_easting": 722000,
    "itm_northing": 726500,
    "submission_year": 2026,
}

scenarios = {
    "baseline (12 units, 0.4ha)": {},
    "fewer units (8)": {"units": 8, "floor_area_sqm": 1600},
    "more units (16)": {"units": 16, "floor_area_sqm": 3200},
    "same units, smaller site (0.25ha)": {"site_area_sqm": 2500},
    "same units, bigger site (0.6ha)": {"site_area_sqm": 6000},
    "more floor area (taller, 4000sqm)": {"floor_area_sqm": 4000},
    "rural-style wording": {"description": "construction of 12 no. dwelling houses on serviced sites"},
    "one-off house on same site": {"units": 1, "floor_area_sqm": 250, "description": "construction of a single dwelling house with garage"},
}

results = {}
for name, changes in scenarios.items():
    proposal = {**base, **changes}
    score = score_proposal(proposal)
    results[name] = {
        "units": proposal["units"],
        "site_area_sqm": proposal["site_area_sqm"],
        "floor_area_sqm": proposal["floor_area_sqm"],
        "refusal_probability": score["refusal_probability"],
        "grant_probability": score["grant_probability"],
        "risk_band": score["risk_band"],
        "raw_ranking_score": score["raw_ranking_score"],
    }

base_risk = results["baseline (12 units, 0.4ha)"]["refusal_probability"]
print("baseline refusal probability:", base_risk)
print()
for name, row in results.items():
    delta = row["refusal_probability"] - base_risk
    marker = "  <-- baseline" if delta == 0 else f"  ({delta*100:+.1f}pp vs baseline)"
    print(f"{name:44s} units={row['units']:>3} site={row['site_area_sqm']:>5} floor={row['floor_area_sqm']:>5} risk={row['refusal_probability']*100:5.1f}% {marker}")

out = ROOT / "05_policy" / "current" / "scenario_smoke_test_v4.json"
out.write_text(json.dumps({"baseline_risk": base_risk, "scenarios": results}, indent=2), encoding="utf-8")
print()
print("saved ->", out.name)
