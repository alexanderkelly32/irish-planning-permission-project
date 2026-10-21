#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Tuple


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "07_solar" / "source_data" / "eirgrid_solar_project_matches.csv"
OUTPUT_ALL = ROOT / "07_solar" / "source_data" / "eirgrid_solar_project_matches_reviewed.csv"
OUTPUT_ACCEPTED = ROOT / "07_solar" / "source_data" / "eirgrid_solar_project_matches_reviewed_accepted.csv"


REVIEW_DECISIONS: Dict[str, Tuple[str, str, str]] = {
    "carlow_county_council_1946": ("accepted", "direct", "Address and project naming align closely with Friarstown solar farm."),
    "carlow_county_council_20143": ("accepted", "direct", "Planning address includes Garreenleen and looks consistent with Garreenleen phase 2."),
    "carlow_county_council_2123": ("accepted", "direct", "Planning address includes Grangeford and description is utility-scale solar."),
    "carlow_county_council_2560155": ("accepted", "related", "BESS application explicitly tied to the permitted Garreenleen solar farm."),
    "clare_county_council_20562": ("accepted", "direct", "Manusmore name and address align directly."),
    "clare_county_council_22591": ("accepted", "direct", "Ballyglass appears directly in the planning address and description."),
    "cork_city_council_2341837": ("rejected", "none", "Planning case concerns Ballinvuskig modifications and a Ballinrea substation link, not a clear Ballinrea Solar Park match."),
    "cork_county_council_165455": ("accepted", "direct", "Carragraigue name and location align."),
    "cork_county_council_174167": ("accepted", "direct", "Coumaclovane name and location align."),
    "cork_county_council_195729": ("accepted", "direct", "Lysaghtstown phase 2 reference is explicit in the description."),
    "cork_county_council_225777": ("accepted", "related", "Interconnector application explicitly references Ballyroe Solar Farm."),
    "cork_county_council_234304": ("accepted", "related", "Application is an alteration/extension to the Ballyvatta solar farm."),
    "fingal_county_council_f21a_0042_": ("accepted", "direct", "Fieldstown is explicit in the planning address despite truncated text."),
    "galway_county_council_20783": ("accepted", "direct", "Barnacurragh appears in the address and project naming aligns."),
    "galway_county_council_20961": ("accepted", "direct", "Ballymoneen phase 2 aligns with address and solar plus battery description."),
    "kerry_county_council_23431": ("accepted", "related", "Substation application explicitly supports the previously permitted Drombeg solar farm."),
    "kildare_county_council_201529": ("accepted", "direct", "Coolcarrigan is explicit in the address and description."),
    "kildare_county_council_2560326": ("accepted", "direct", "Toolestown is explicit in the address and the project is utility-scale."),
    "limerick_county_council_1918": ("rejected", "none", "Planning case is in Deelish and Mullagh and only mentions Ballinknockane as an adjoining connection route."),
    "limerick_county_council_22313667": ("accepted", "related", "Substation application is clearly associated with the proposed Ballyvalode solar farm."),
    "longford_county_council_22275": ("accepted", "related", "Grid connection application explicitly references Middleton House / Ballycore solar farm."),
    "meath_county_council_22595": ("accepted", "related", "Cable application explicitly links parcels of the permitted Milltown Solar Farm."),
    "meath_county_council_2460288": ("accepted", "related", "Application is an extension to the permitted Clonymeath Solar Farm."),
    "meath_county_council_2461016": ("rejected", "none", "Blackwater Bog Solar Farm 1 at Shannonbridge does not fit the Meath townlands in this planning case."),
    "meath_county_council_lb200487": ("accepted", "direct", "Gaskinstown appears explicitly in the planning address."),
    "meath_county_council_ta181225": ("accepted", "direct", "Harristown appears explicitly in the planning address."),
    "offaly_county_council_21292": ("rejected", "none", "This is a 1.73 ha small site and does not look like the contracted Clonin North solar farm."),
    "offaly_county_council_2165": ("accepted", "direct", "Ballyteige name and location align."),
    "offaly_county_council_2560610": ("accepted", "related", "Application explicitly refers to parent permission for the Kilcormac solar farm."),
    "roscommon_county_council_2036": ("accepted", "direct", "Taduff is explicit in the address and project naming aligns."),
    "tipperary_county_council_211057": ("accepted", "direct", "Killoran is explicit in the address and project naming aligns."),
    "westmeath_county_council_176239": ("rejected", "none", "This appears to be the main Clondardis scheme, not clearly the EirGrid extension project."),
    "westmeath_county_council_196168": ("accepted", "direct", "Clonfad is explicit in the project and location."),
    "westmeath_county_council_2560201": ("accepted", "related", "Amendment application is clearly tied to the approved Clondardis solar farm."),
    "wexford_county_council_20191272": ("accepted", "direct", "Tullabeg appears in the address and description."),
    "wexford_county_council_20231025": ("accepted", "direct", "Tincurry appears in the address and description."),
    "wicklow_county_council_171440": ("accepted", "direct", "North Arklow solar plus storage aligns with the planning description."),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply manual review decisions to EirGrid/planning project matches.")
    parser.parse_args()

    with INPUT.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    reviewed = []
    accepted = []
    for row in rows:
        decision, match_kind, note = REVIEW_DECISIONS[row["case_key"]]
        row["manual_review_status"] = decision
        row["manual_match_kind"] = match_kind
        row["manual_review_note"] = note
        reviewed.append(row)
        if decision == "accepted":
            accepted.append(row)

    fieldnames = list(reviewed[0].keys()) if reviewed else []
    with OUTPUT_ALL.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(reviewed)

    with OUTPUT_ACCEPTED.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(accepted)

    print(
        json.dumps(
            {
                "input_rows": len(rows),
                "accepted_rows": len(accepted),
                "rejected_rows": len(rows) - len(accepted),
                "reviewed_output": str(OUTPUT_ALL),
                "accepted_output": str(OUTPUT_ACCEPTED),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
