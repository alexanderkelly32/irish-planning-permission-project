#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
LIKELY_CSV = ROOT / "07_solar" / "source_data" / "likely_solar_farms.csv"
RELATED_CSV = ROOT / "07_solar" / "source_data" / "solar_farm_related_applications.csv"
AMBIGUOUS_BUCKETED_CSV = ROOT / "07_solar" / "source_data" / "ambiguous_solar_bucketed.csv"
EIRGRID_CSV = ROOT / "07_solar" / "source_data" / "eirgrid_contracted_non_wind_solar_2025-11-28.csv"
MATCH_OUTPUT = ROOT / "07_solar" / "source_data" / "eirgrid_solar_project_matches.csv"
UNMATCHED_OUTPUT = ROOT / "07_solar" / "source_data" / "eirgrid_solar_unmatched_projects.csv"

GENERIC_NAME_TOKENS = {
    "solar",
    "farm",
    "park",
    "pv",
    "phase",
    "extension",
    "battery",
    "storage",
    "plus",
    "facility",
    "hybrid",
    "formerly",
    "and",
    "north",
    "south",
    "east",
    "west",
    "county",
    "farmers",
}

GENERIC_LOCATION_TOKENS = {
    "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry", "kildare",
    "kilkenny", "laois", "limerick", "longford", "louth", "mayo", "meath", "monaghan",
    "offaly", "roscommon", "sligo", "tipperary", "waterford", "westmeath", "wexford",
    "wicklow", "city", "council",
}


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def name_tokens(name: str) -> List[str]:
    tokens = [token for token in normalize(name).split() if len(token) >= 4]
    filtered = [
        token
        for token in tokens
        if token not in GENERIC_NAME_TOKENS
        and token not in GENERIC_LOCATION_TOKENS
    ]
    return filtered


def build_project_phrase(name: str) -> str:
    tokens = name_tokens(name)
    return " ".join(tokens)


def relevant_planning_rows() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    rows.extend(load_rows(LIKELY_CSV))
    rows.extend(load_rows(RELATED_CSV))
    rows.extend(
        row
        for row in load_rows(AMBIGUOUS_BUCKETED_CSV)
        if row.get("ambiguous_review_bucket") in {"utility_scale_candidate", "utility_scale_related_application"}
    )
    return rows


def planning_search_text(row: Dict[str, str]) -> str:
    return normalize(
        " ".join(
            filter(
                None,
                [
                    row.get("PlanningAuthority", ""),
                    row.get("DevelopmentAddress", ""),
                    row.get("DevelopmentDescription", ""),
                    row.get("solar_reason", ""),
                    row.get("ambiguous_review_note", ""),
                ],
            )
        )
    )


def score_match(project_name: str, search_text: str) -> Tuple[int, str]:
    full_name = normalize(project_name)
    phrase = build_project_phrase(project_name)
    tokens = name_tokens(project_name)

    if full_name and full_name in search_text:
        return (120, "full_name_exact")
    if phrase and len(phrase.split()) >= 2 and phrase in search_text:
        return (105, "base_phrase_exact")

    matched_tokens = [token for token in tokens if token in search_text.split()]
    if not matched_tokens:
        return (0, "no_signal")

    score = 0
    basis = []
    score += len(matched_tokens) * 22
    basis.append(f"matched_tokens:{','.join(matched_tokens)}")

    if tokens and len(matched_tokens) == len(tokens):
        score += 25
        basis.append("all_tokens")

    if len(tokens) == 1:
        token = tokens[0]
        if len(token) >= 6:
            score += 18
            basis.append("single_distinctive_token")
        else:
            score -= 12
            basis.append("single_short_token")

    return (score, "|".join(basis))


def confidence(score: int) -> str:
    if score >= 110:
        return "high"
    if score >= 65:
        return "medium"
    return "low"


def main() -> None:
    parser = argparse.ArgumentParser(description="Match extracted EirGrid solar projects to the planning solar rows.")
    parser.parse_args()

    planning_rows = relevant_planning_rows()
    search_rows = [
        {
            "case_key": row.get("case_key", ""),
            "planning_authority": row.get("PlanningAuthority", ""),
            "application_number": row.get("ApplicationNumber", ""),
            "search_text": planning_search_text(row),
        }
        for row in planning_rows
        if row.get("case_key")
    ]

    matches: List[Dict[str, str]] = []
    matched_eirgrid_refs = set()

    for eirgrid_row in load_rows(EIRGRID_CSV):
        project_name = eirgrid_row.get("eirgrid_project_name", "")
        scored = []
        for planning_row in search_rows:
            score, basis = score_match(project_name, planning_row["search_text"])
            if score > 0:
                scored.append((score, basis, planning_row))
        if not scored:
            continue
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_basis, best_planning = scored[0]
        if best_score < 40:
            continue
        matched_eirgrid_refs.add(eirgrid_row.get("eirgrid_ref", ""))
        matches.append(
            {
                "case_key": best_planning["case_key"],
                "planning_authority": best_planning["planning_authority"],
                "application_number": best_planning["application_number"],
                "eirgrid_ref": eirgrid_row.get("eirgrid_ref", ""),
                "eirgrid_project_name": project_name,
                "eirgrid_node": eirgrid_row.get("eirgrid_node", ""),
                "eirgrid_voltage": eirgrid_row.get("eirgrid_voltage", ""),
                "eirgrid_processing_type": eirgrid_row.get("eirgrid_processing_type", ""),
                "eirgrid_generator_type": eirgrid_row.get("eirgrid_generator_type", ""),
                "eirgrid_mec_mw": eirgrid_row.get("eirgrid_mec_mw", ""),
                "eirgrid_signed_date": eirgrid_row.get("eirgrid_signed_date", ""),
                "eirgrid_match_score": str(best_score),
                "eirgrid_match_confidence": confidence(best_score),
                "eirgrid_match_basis": best_basis,
            }
        )

    # Keep the strongest EirGrid match per planning case.
    by_case: Dict[str, Dict[str, str]] = {}
    for row in matches:
        current = by_case.get(row["case_key"])
        if current is None or int(row["eirgrid_match_score"]) > int(current["eirgrid_match_score"]):
            by_case[row["case_key"]] = row

    final_matches = sorted(by_case.values(), key=lambda row: (row["planning_authority"], row["application_number"]))
    unmatched_rows = [
        row for row in load_rows(EIRGRID_CSV)
        if row.get("eirgrid_ref", "") not in matched_eirgrid_refs
    ]

    MATCH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with MATCH_OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(final_matches[0].keys()) if final_matches else [
            "case_key","planning_authority","application_number","eirgrid_ref","eirgrid_project_name","eirgrid_node",
            "eirgrid_voltage","eirgrid_processing_type","eirgrid_generator_type","eirgrid_mec_mw",
            "eirgrid_signed_date","eirgrid_match_score","eirgrid_match_confidence","eirgrid_match_basis"
        ])
        writer.writeheader()
        writer.writerows(final_matches)

    with UNMATCHED_OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(unmatched_rows[0].keys()) if unmatched_rows else [
            "eirgrid_node","eirgrid_voltage","eirgrid_ref","eirgrid_project_name","eirgrid_processing_type",
            "eirgrid_generator_type","eirgrid_mec_mw","eirgrid_signed_date"
        ])
        writer.writeheader()
        writer.writerows(unmatched_rows)

    print(
        json.dumps(
            {
                "planning_rows_considered": len(search_rows),
                "eirgrid_projects": len(load_rows(EIRGRID_CSV)),
                "matched_planning_cases": len(final_matches),
                "unmatched_eirgrid_projects": len(unmatched_rows),
                "output_matches": str(MATCH_OUTPUT),
                "output_unmatched": str(UNMATCHED_OUTPUT),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
