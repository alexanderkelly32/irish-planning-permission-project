"""Alternative-landmark registry: ranked candidates for observable state
changes. Scores 1-5 on data accessibility x likely coverage x causal
closeness to real activity x expected information gain. Rank = product.
Each entry: causal mechanism + cheapest validation test BEFORE extraction.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

REGISTRY = [
    {"id": "spv_incorporation", "name": "New SPV incorporation by developer post-grant",
     "mechanism": "A developer creates a project SPV when funding/site control is being assembled for a specific scheme; incorporation is a free CRO filing that precedes real mobilisation.",
     "accessibility": 5, "coverage": 3, "closeness": 4, "gain": 4,
     "data": "companies.csv.zip + applicant_entities_with_cro.csv + developer_groups.csv (held)",
     "cheapest_test": "grant->new-SPV-incorporation->commencement chain; landmark test at 90/180d via the generic adapter (no extraction).",
     "status": "not_started"},
    {"id": "amendment_activity", "name": "Post-grant amendment/revision applications on same parcel",
     "mechanism": "Filing an amendment or revision application is a revealed act of continued engagement with the site - the opposite of dormancy.",
     "accessibility": 5, "coverage": 4, "closeness": 4, "gain": 3,
     "data": "npad_register_bronze.parquet + graph parcel links (held)",
     "cheapest_test": "Count amendment/revision filings between grant and commencement; compare dormant vs commenced cohorts (held data, no extraction).",
     "status": "not_started"},
    {"id": "enforcement_events", "name": "Enforcement notice / warning letters",
     "mechanism": "Enforcement action signals active site activity (often premature works) and typically precedes corrective submissions or commencement.",
     "accessibility": 4, "coverage": 2, "closeness": 4, "gain": 3,
     "data": "run_pull_enforcement harvest (held, partial)",
     "cheapest_test": "Link harvested enforcement rows to schemes; adapter before/after on commencement and CCC transitions.",
     "status": "not_started"},
    {"id": "fsc_dac_progression", "name": "FSC/DAC application -> grant progression",
     "mechanism": "Fire/access cert grants are statutory late-construction milestones; grant->CCC lead should be short and stable.",
     "accessibility": 5, "coverage": 3, "closeness": 5, "gain": 3,
     "data": "infrastructure_readiness_features.csv (held)",
     "cheapest_test": "fsc_first_grant_days_from_grant -> first CCC lead distribution (first_submit already tested: width -11.9%, no collapse).",
     "status": "partial (first_submit tested: no collapse)"},
    {"id": "sales_listing_launch", "name": "Sales launch / new-home listings appearance",
     "mechanism": "Marketing launch is a revealed state change: units offered means construction is far advanced or forward-funded; precedes first PPR sale by weeks-months.",
     "accessibility": 3, "coverage": 4, "closeness": 4, "gain": 4,
     "data": "public listing sites (myhome/daft) - scraping required",
     "cheapest_test": "Scrape listings for 10 pilot estates; compare launch date vs first CCC/first sale via adapter; only if the first pass is cheap.",
     "status": "not_started"},
    {"id": "taking_in_charge", "name": "Taking-in-charge requests",
     "mechanism": "TIC request is a terminal completeness marker; follows final CCC and precedes estate handover.",
     "accessibility": 3, "coverage": 2, "closeness": 4, "gain": 2,
     "data": "iDocs ledger types (held for ~90 schemes)",
     "cheapest_test": "Adapter on TIC ledger events for the iDocs cohort.",
     "status": "not_started"},
    {"id": "uisce_connection", "name": "Uisce connection agreement/application",
     "mechanism": "Water connection agreement is a pre-commencement statutory milestone; its date pins utility-readiness before works.",
     "accessibility": 1, "coverage": 2, "closeness": 5, "gain": 4,
     "data": "FOI only",
     "cheapest_test": "If data arrives: generic adapter (B-test value likely even if C-test fails).",
     "status": "blocked_on_foi"},
    {"id": "esb_energisation", "name": "ESB energisation of units",
     "mechanism": "Energisation approximately equals units habitable; immediately precedes first sale/occupation.",
     "accessibility": 1, "coverage": 3, "closeness": 5, "gain": 4,
     "data": "FOI only",
     "cheapest_test": "Generic adapter on arrival; distributional value likely even at small n.",
     "status": "blocked_on_foi"},
    {"id": "eircode_address_creation", "name": "New eircode/address appearance",
     "mechanism": "Address assignment happens when units near handover; a late-stage state change observable from address registers.",
     "accessibility": 2, "coverage": 3, "closeness": 4, "gain": 3,
     "data": "paid eircode product / OSM address nodes (free, partial)",
     "cheapest_test": "OSM address-node diff for 5 estates vs CCC dates (free probe).",
     "status": "not_started"},
    {"id": "cro_charge_registration", "name": "CRO charge/mortgage registration on developer SPV",
     "mechanism": "Charge registration (within 21 days of creation) is a hard dated financing event; charges usually precede commencement.",
     "accessibility": 1, "coverage": 2, "closeness": 4, "gain": 4,
     "data": "paid CRO charge search only",
     "cheapest_test": "Paid pilot on the 24 forensics pairs (user decision).",
     "status": "blocked_paid"},
]


def main() -> None:
    for r in REGISTRY:
        r["rank_score"] = r["accessibility"] * r["coverage"] * r["closeness"] * r["gain"]
    ranked = sorted(REGISTRY, key=lambda r: -r["rank_score"])
    out = settings.SILVER_DIR / "landmarks" / "alternative_landmark_registry.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ranked, indent=2), encoding="utf-8")
    print(json.dumps([{"id": r["id"], "rank_score": r["rank_score"], "status": r["status"]}
                      for r in ranked], indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
