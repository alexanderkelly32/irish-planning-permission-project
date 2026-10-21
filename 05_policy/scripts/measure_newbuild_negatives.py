#!/usr/bin/env python3
"""Complete the new-build negative-delta table: measure remaining candidates."""
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
CANDIDATES = [
    "landscaping works",
    "retail unit",
    "private open space",
    "bay window",
    "house",
    "dwelling house",
    "single storey",
    "construction single storey",
    "site works significant",
    "boiler house",
    "construction replacement",
    "community facilities",
    "brick finish",
    "demolition of existing buildings",
    "duplex apartments",
    "semi detached",
]


def main() -> None:
    baseline_risk = score_proposal(BASELINE)["refusal_probability"]
    rows = []
    for phrase in CANDIDATES:
        risk = score_proposal({**BASELINE, "description": f"{BASELINE['description']} with {phrase}"})["refusal_probability"]
        rows.append({"phrase": phrase, "delta_pp": round((risk - baseline_risk) * 100, 1)})
    rows.sort(key=lambda r: r["delta_pp"])
    (OUT / "newbuild_negative_deltas.json").write_text(json.dumps({
        "baseline_refusal_probability": baseline_risk,
        "deltas": rows,
    }, indent=2), encoding="utf-8")
    print(f"baseline: {baseline_risk * 100:.1f}%", flush=True)
    for r in rows:
        print(f"  {r['phrase']:32s} {r['delta_pp']:+6.1f}pp", flush=True)


if __name__ == "__main__":
    main()
