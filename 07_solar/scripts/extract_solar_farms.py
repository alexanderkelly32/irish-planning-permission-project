#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_comprehensive_master.csv"
DEFAULT_OUTPUT_DIR = ROOT / "07_solar" / "source_data"

SOLAR_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("solar", re.compile(r"\bsolar\b", re.I)),
    ("photovoltaic", re.compile(r"photovoltaic", re.I)),
    ("pv", re.compile(r"\bpv\b", re.I)),
]

EXPLICIT_FARM_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("solar_farm", re.compile(r"solar farm", re.I)),
    ("solar_park", re.compile(r"solar (?:and )?storage park|solar park", re.I)),
    ("solar_energy_development", re.compile(r"solar energy development", re.I)),
    ("solar_pv_development", re.compile(r"solar (?:pv|photovoltaic) development", re.I)),
    ("photovoltaic_energy_development", re.compile(r"photovoltaic energy development", re.I)),
]

GROUND_MOUNT_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("ground_mounted", re.compile(r"ground mounted", re.I)),
    ("ground_mounted_frames", re.compile(r"ground mounted frames?", re.I)),
    ("ground_mounted_steel_frames", re.compile(r"ground mounted steel frames?", re.I)),
    ("fixed_panels_ground", re.compile(r"fixed panels? on ground mounted frames?", re.I)),
    ("steel_mounting_frames", re.compile(r"steel mounting frames?|steel support structures?", re.I)),
    ("ground_mounted_pv", re.compile(r"ground mounted .*?\bpv\b|\bpv\b .*?ground mounted", re.I)),
    ("laid_out_in_arrays", re.compile(r"laid out in arrays", re.I)),
    ("linear_arrays", re.compile(r"linear arrays", re.I)),
]

UTILITY_INFRA_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("substation", re.compile(r"\bsub[- ]?station\b|\bsubstation\b", re.I)),
    ("inverter", re.compile(r"inverter", re.I)),
    ("transformer", re.compile(r"transformer", re.I)),
    ("energy_storage", re.compile(r"energy storage|battery cells|storage compound", re.I)),
    ("grid_connection", re.compile(r"national grid|electricity grid|grid connection|connect(?:ed)? to the national grid", re.I)),
    ("underground_cabling", re.compile(r"underground cabling|ducting", re.I)),
    ("security_fencing", re.compile(r"security fencing|perimeter security fencing|boundary fencing", re.I)),
    ("cctv", re.compile(r"\bcctv\b", re.I)),
    ("operational_lifespan", re.compile(r"operational lifespan|operational period|projected lifespan|life span of \d+ years", re.I)),
    ("access_tracks", re.compile(r"access tracks?|internal access road", re.I)),
]

ROOFTOP_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("roof_mounted", re.compile(r"roof mounted|mounted to roof|mounted to the roof", re.I)),
    ("roof_surface", re.compile(r"roof surface|roof level|existing roof|roofs of", re.I)),
    ("on_roof", re.compile(r"on the roof|to the roof|roof of (?:the )?existing", re.I)),
    ("dwelling_context", re.compile(r"dwelling|house\b|clubhouse|school building|retail store|industrial buildings?|portal frame building|canopy", re.I)),
]

RELATED_APPLICATION_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("interconnector_cable", re.compile(r"interconnector cable|underground electricity interconnector cable", re.I)),
    ("operational_lifespan_change", re.compile(r"extension of the operational lifespan|operational lifespan .* to \d+", re.I)),
    ("layout_revision", re.compile(r"revision to the approved layout|revisions to the permitted .* layout", re.I)),
    ("minor_amendment", re.compile(r"minor amendments?|modify a previously granted planning permission", re.I)),
    ("substation_relocation", re.compile(r"relocation and revised design .* substation|revised .* substation building", re.I)),
]

DIRECT_PROJECT_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("site_area_hectares", re.compile(r"\b\d+(?:\.\d+)?\s*(?:ha|hectares)\b", re.I)),
    ("construction_of_project", re.compile(r"construction of .*solar|construction of .*photovoltaic", re.I)),
    ("erection_and_operation", re.compile(r"erection and operation of .*photovoltaic energy development|erection and operation of .*solar", re.I)),
    ("solar_farm_on_area", re.compile(r"solar farm on an area of|solar farm with a total area of|comprising the construction of .*solar farm", re.I)),
]

OUTPUT_COLUMNS = [
    "case_key",
    "PlanningAuthority",
    "ApplicationNumber",
    "ApplicationType",
    "ApplicationStatus",
    "Decision",
    "ReceivedDate",
    "DecisionDate",
    "DevelopmentAddress",
    "DevelopmentPostcode",
    "ITMEasting",
    "ITMNorthing",
    "AreaofSite",
    "FloorArea",
    "NumResidentialUnits",
    "units_total_best",
    "site_area_ha_best",
    "site_area_sqm_best",
    "solar_keyword_tags",
    "explicit_farm_tags",
    "ground_mount_tags",
    "utility_infra_tags",
    "rooftop_tags",
    "related_application_tags",
    "direct_project_tags",
    "is_likely_solar_farm",
    "solar_classification",
    "solar_reason",
    "DevelopmentDescription",
]


def matched_labels(text: str, patterns: Iterable[Tuple[str, re.Pattern[str]]]) -> List[str]:
    return [label for label, pattern in patterns if pattern.search(text)]


def classify_row(description: str) -> Dict[str, str]:
    desc = " ".join((description or "").split())
    solar_tags = matched_labels(desc, SOLAR_PATTERNS)
    if not solar_tags:
        return {}

    explicit_tags = matched_labels(desc, EXPLICIT_FARM_PATTERNS)
    ground_tags = matched_labels(desc, GROUND_MOUNT_PATTERNS)
    utility_tags = matched_labels(desc, UTILITY_INFRA_PATTERNS)
    rooftop_tags = matched_labels(desc, ROOFTOP_PATTERNS)
    related_tags = matched_labels(desc, RELATED_APPLICATION_PATTERNS)
    direct_project_tags = matched_labels(desc, DIRECT_PROJECT_PATTERNS)

    rooftop_only = bool(rooftop_tags) and not ground_tags and not explicit_tags
    likely_solar_farm = bool(explicit_tags) or (bool(ground_tags) and bool(utility_tags))
    strong_direct_project = bool(direct_project_tags) or bool(ground_tags)

    if likely_solar_farm and rooftop_only:
        likely_solar_farm = False

    if likely_solar_farm:
        if related_tags and not strong_direct_project:
            classification = "solar_farm_related_application"
            reason = "utility-scale solar is referenced, but the application reads as a modification or follow-on works"
        elif explicit_tags:
            classification = "likely_solar_farm"
            reason = "explicit utility-scale solar wording in description"
        else:
            classification = "likely_solar_farm"
            reason = "ground-mounted solar wording plus utility infrastructure signals"
    elif rooftop_only:
        classification = "rooftop_or_building_solar"
        reason = "solar mention appears tied to roof/building-mounted panels"
    else:
        classification = "ambiguous_solar"
        reason = "solar mention found, but description needs spot-check"

    return {
        "solar_keyword_tags": "|".join(solar_tags),
        "explicit_farm_tags": "|".join(explicit_tags),
        "ground_mount_tags": "|".join(ground_tags),
        "utility_infra_tags": "|".join(utility_tags),
        "rooftop_tags": "|".join(rooftop_tags),
        "related_application_tags": "|".join(related_tags),
        "direct_project_tags": "|".join(direct_project_tags),
        "is_likely_solar_farm": "True" if likely_solar_farm else "False",
        "solar_classification": classification,
        "solar_reason": reason,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract solar-related planning cases and flag likely solar farms.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    max_limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_limit)
            break
        except OverflowError:
            max_limit = max_limit // 10
    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_rows: List[Dict[str, str]] = []
    likely_rows: List[Dict[str, str]] = []
    related_rows: List[Dict[str, str]] = []
    ambiguous_rows: List[Dict[str, str]] = []
    classification_counts: Counter[str] = Counter()
    likely_by_la: Dict[str, int] = defaultdict(int)

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            classification = classify_row(row.get("DevelopmentDescription", ""))
            if not classification:
                continue

            out_row = {column: row.get(column, "") for column in OUTPUT_COLUMNS}
            out_row.update(classification)

            all_rows.append(out_row)
            classification_counts[out_row["solar_classification"]] += 1

            if out_row["solar_classification"] == "likely_solar_farm":
                likely_rows.append(out_row)
                likely_by_la[out_row.get("PlanningAuthority", "")] += 1
            elif out_row["solar_classification"] == "solar_farm_related_application":
                related_rows.append(out_row)
            elif out_row["solar_classification"] == "ambiguous_solar":
                ambiguous_rows.append(out_row)

    def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    write_csv(args.output_dir / "all_solar_mentions.csv", all_rows)
    write_csv(args.output_dir / "likely_solar_farms.csv", likely_rows)
    write_csv(args.output_dir / "solar_farm_related_applications.csv", related_rows)
    write_csv(args.output_dir / "ambiguous_solar_mentions.csv", ambiguous_rows)

    summary_rows = [
        {"metric": "all_solar_mentions", "value": str(len(all_rows))},
        {"metric": "likely_solar_farms", "value": str(len(likely_rows))},
        {"metric": "solar_farm_related_applications", "value": str(len(related_rows))},
        {"metric": "ambiguous_solar_mentions", "value": str(len(ambiguous_rows))},
        {
            "metric": "rooftop_or_building_solar",
            "value": str(classification_counts.get("rooftop_or_building_solar", 0)),
        },
    ]
    with (args.output_dir / "solar_exploration_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(summary_rows)

    with (args.output_dir / "likely_solar_farms_by_la.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["PlanningAuthority", "likely_solar_farms"])
        writer.writeheader()
        for planning_authority, count in sorted(likely_by_la.items(), key=lambda item: (-item[1], item[0])):
            writer.writerow({"PlanningAuthority": planning_authority, "likely_solar_farms": count})

    print(
        json.dumps(
            {
                "input": str(args.input),
                "output_dir": str(args.output_dir),
                "all_solar_mentions": len(all_rows),
                "likely_solar_farms": len(likely_rows),
                "solar_farm_related_applications": len(related_rows),
                "ambiguous_solar_mentions": len(ambiguous_rows),
                "rooftop_or_building_solar": classification_counts.get("rooftop_or_building_solar", 0),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
