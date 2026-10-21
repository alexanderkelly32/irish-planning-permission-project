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
DEFAULT_OUTPUT_DIR = ROOT / "08_data_centres" / "source_data"

WIDE_NET_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("data_centre", re.compile(r"\bdata[\s-]*cent(?:re|er)s?\b", re.I)),
    ("datacentre", re.compile(r"\bdatacent(?:re|er)s?\b", re.I)),
    ("data_storage_facility", re.compile(r"\bdata storage facilit(?:y|ies)\b", re.I)),
    ("data_processing_facility", re.compile(r"\bdata processing facilit(?:y|ies)\b", re.I)),
    ("ict_facility", re.compile(r"\bICT facility\b|information and communications? technology \(?ICT\)? facilit(?:y|ies)|information communication technology \(?ICT\)? facilit(?:y|ies)", re.I)),
    ("data_hall", re.compile(r"\bdata halls?\b|\bICT equipment halls?\b", re.I)),
    ("telecom_data_centre", re.compile(r"telecoms? data cent(?:re|er)", re.I)),
    ("disaster_recovery", re.compile(r"disaster recovery|business continuity centre", re.I)),
    ("server_room", re.compile(r"\bserver rooms?\b", re.I)),
    ("ict_room", re.compile(r"\bICT rooms?\b", re.I)),
    ("computer_room", re.compile(r"\bcomputer rooms?\b", re.I)),
    ("digital_hub", re.compile(r"\bdigital hub\b", re.I)),
    ("co_location", re.compile(r"\bco-location\b|\bco location\b|\bcolocation\b", re.I)),
]

PRIMARY_EXPLICIT_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("data_centre", re.compile(r"\bdata[\s-]*cent(?:re|er)s?\b|\bdatacent(?:re|er)s?\b", re.I)),
    ("data_storage_facility", re.compile(r"\bdata storage facilit(?:y|ies)\b", re.I)),
    ("data_processing_facility", re.compile(r"\bdata processing facilit(?:y|ies)\b", re.I)),
    ("telecom_data_centre", re.compile(r"telecoms? data cent(?:re|er)", re.I)),
]

ICT_FACILITY_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("ict_facility", re.compile(r"\bICT facility\b|\bICT facilities\b|information and communications? technology \(?ICT\)? facilit(?:y|ies)|information communication technology \(?ICT\)? facilit(?:y|ies)", re.I)),
    ("ict_building", re.compile(r"\bICT buildings?\b", re.I)),
    ("ict_equipment_rooms", re.compile(r"\bICT equipment rooms?\b|\bICT equipment halls?\b", re.I)),
]

SUPPORT_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("data_halls", re.compile(r"\bdata halls?\b", re.I)),
    ("loading_bay", re.compile(r"loading bays?|loading area", re.I)),
    ("power_trunk", re.compile(r"\bpower trunk\b", re.I)),
    ("customer_compound", re.compile(r"customer compound", re.I)),
    ("switchgear", re.compile(r"switchgear|switch rooms?", re.I)),
    ("substation", re.compile(r"\bsub[- ]?station\b|\bsubstation\b", re.I)),
    ("transformer", re.compile(r"transformers?|transformer compound", re.I)),
    ("backup_generators", re.compile(r"back[\s-]*up generators?|backup generators?|standby generators?|generator compound", re.I)),
    ("energy_centre", re.compile(r"energy centre|energy center", re.I)),
    ("mechanical_electrical_plant", re.compile(r"mechanical (?:and )?electrical plant|electrical and mechanical plant|mechanical equipment rooms?|electrical equipment rooms?|plant rooms?", re.I)),
    ("network_room", re.compile(r"\bnetwork rooms?\b", re.I)),
    ("water_tanks", re.compile(r"water storage tanks?|sprinkler tank|fire water", re.I)),
    ("campus", re.compile(r"\bcampus\b", re.I)),
]

RELATED_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("amendment", re.compile(r"\bamendments?\b|\bamended\b", re.I)),
    ("alteration", re.compile(r"\balterations?\b|\brevisions?\b", re.I)),
    ("modification", re.compile(r"\bmodifications?\b|\bmodified\b", re.I)),
    ("retention", re.compile(r"\bretention\b", re.I)),
    ("extension_of_duration", re.compile(r"extension of duration|extend the appropriate period", re.I)),
    ("permitted_reference", re.compile(r"permitted under|previously approved|approved data centre|granted under|extant planning permissions|supersed(?:e|ing)", re.I)),
    ("minor_works", re.compile(r"minor additions?|minor amendments?|temporary amendment|relocation of .*generator|roof of the building .*data centre", re.I)),
]

MIXED_USE_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("mixed_use_block", re.compile(r"mixed use|mixed-use", re.I)),
    ("data_centre_light_industrial", re.compile(r"data centre\s*/?\s*light industrial|data centre/light industrial|data centre/light industrial / storage / research and development", re.I)),
]

SMALL_SPECIALISED_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("telephone_exchange_conversion", re.compile(r"telephone exchange .* data cent(?:re|er)|exchange use .* data cent(?:re|er)", re.I)),
    ("change_of_use_to_data_centre", re.compile(r"change of use .* data cent(?:re|er)", re.I)),
    ("disaster_recovery_business_continuity", re.compile(r"disaster recovery|business continuity centre", re.I)),
    ("external_data_centre_unit", re.compile(r"external data cent(?:re|er) unit", re.I)),
]

EXCLUSION_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("digital_hub", re.compile(r"\bdigital hub\b", re.I)),
    ("telecom_co_location", re.compile(r"\bco-location\b|\bco location\b|\bcolocation\b", re.I)),
    ("ict_room", re.compile(r"\bICT rooms?\b", re.I)),
    ("server_room", re.compile(r"\bserver rooms?\b", re.I)),
    ("computer_room", re.compile(r"\bcomputer rooms?\b", re.I)),
    ("telecom_structure", re.compile(r"communications structure|antennae|dishes|telecommunications equipment|monopole|lattice communications", re.I)),
    ("school_context", re.compile(r"\bschool\b|classroom|educational building|third level", re.I)),
    ("community_context", re.compile(r"resource centre|family support centre|community space|community digital hub", re.I)),
]

NEW_PRIMARY_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("construction", re.compile(r"\bconstruction of\b|\bconstruct\b|\berection of\b|\bprovision of\b|\bdevelopment of\b", re.I)),
    ("replacement_with_new_facility", re.compile(r"replacement .* with .*data cent(?:re|er)|replacement .* with .*ICT facility|replacement .* with .*data storage facilit", re.I)),
    ("new_buildings", re.compile(r"\bnew data cent(?:re|er)\b|\bnew ICT facility\b|\bnew data storage facilit", re.I)),
    ("expansion", re.compile(r"expansion of .*data cent(?:re|er)|expansion of .*data centre campus", re.I)),
    ("change_of_use", re.compile(r"change of use .* data cent(?:re|er)", re.I)),
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
    "geometry",
    "AreaofSite",
    "site_area_ha_best",
    "site_area_sqm_best",
    "FloorArea",
    "floor_area_sqm_best",
    "units_total_best",
    "LinkAppDetails",
    "wide_net_tags",
    "primary_explicit_tags",
    "ict_facility_tags",
    "support_tags",
    "related_tags",
    "mixed_use_tags",
    "small_specialised_tags",
    "exclusion_tags",
    "new_primary_tags",
    "is_likely_data_centre",
    "data_centre_classification",
    "data_centre_reason",
    "DevelopmentDescription",
]


def matched_labels(text: str, patterns: Iterable[Tuple[str, re.Pattern[str]]]) -> List[str]:
    return [label for label, pattern in patterns if pattern.search(text)]


def classify_row(row: Dict[str, str]) -> Dict[str, str]:
    desc = " ".join((row.get("DevelopmentDescription", "") or "").split())
    if not desc:
        return {}

    wide_tags = matched_labels(desc, WIDE_NET_PATTERNS)
    if not wide_tags:
        return {}

    primary_tags = matched_labels(desc, PRIMARY_EXPLICIT_PATTERNS)
    ict_tags = matched_labels(desc, ICT_FACILITY_PATTERNS)
    support_tags = matched_labels(desc, SUPPORT_PATTERNS)
    related_tags = matched_labels(desc, RELATED_PATTERNS)
    mixed_tags = matched_labels(desc, MIXED_USE_PATTERNS)
    small_tags = matched_labels(desc, SMALL_SPECIALISED_PATTERNS)
    exclusion_tags = matched_labels(desc, EXCLUSION_PATTERNS)
    new_tags = matched_labels(desc, NEW_PRIMARY_PATTERNS)

    primary_non_processing = [tag for tag in primary_tags if tag != "data_processing_facility"]
    strong_data_halls = "data_halls" in support_tags and bool(
        {
            "loading_bay",
            "power_trunk",
            "customer_compound",
            "switchgear",
            "substation",
            "transformer",
            "backup_generators",
            "energy_centre",
            "mechanical_electrical_plant",
            "network_room",
            "water_tanks",
            "campus",
        }.intersection(support_tags)
    )
    data_processing_primary = "data_processing_facility" in primary_tags and strong_data_halls
    has_primary_signal = bool(primary_non_processing) or data_processing_primary or (bool(ict_tags) and bool(support_tags)) or strong_data_halls
    looks_new_primary = bool(new_tags) and (has_primary_signal or bool(small_tags))
    exclusion_only = bool(exclusion_tags) and not has_primary_signal and not small_tags

    if exclusion_only:
        classification = "excluded_non_data_centre"
        reason = "wide-net hit appears to be telecom, digital-hub, room-level IT, or community wording rather than a data centre"
    elif mixed_tags:
        classification = "ambiguous_data_centre"
        reason = "description references data-centre use in a mixed-use context and needs a review decision"
    elif small_tags and not looks_new_primary:
        classification = "ambiguous_data_centre"
        reason = "description points to a small or specialised data-centre style use and needs review"
    elif related_tags and has_primary_signal and not looks_new_primary:
        classification = "data_centre_related_application"
        reason = "description reads as an amendment, retention, or follow-on application tied to an existing data-centre scheme"
    elif has_primary_signal or looks_new_primary:
        classification = "likely_data_centre"
        reason = "description explicitly describes a data-centre, data-storage, or data-centre-style ICT facility project"
    else:
        classification = "ambiguous_data_centre"
        reason = "wide-net hit needs a manual spot-check"

    return {
        "wide_net_tags": "|".join(wide_tags),
        "primary_explicit_tags": "|".join(primary_tags),
        "ict_facility_tags": "|".join(ict_tags),
        "support_tags": "|".join(support_tags),
        "related_tags": "|".join(related_tags),
        "mixed_use_tags": "|".join(mixed_tags),
        "small_specialised_tags": "|".join(small_tags),
        "exclusion_tags": "|".join(exclusion_tags),
        "new_primary_tags": "|".join(new_tags),
        "is_likely_data_centre": "True" if classification == "likely_data_centre" else "False",
        "data_centre_classification": classification,
        "data_centre_reason": reason,
    }


def normalize_field_size_limit() -> None:
    max_limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_limit)
            return
        except OverflowError:
            max_limit //= 10


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract likely data-centre planning applications from the master planning CSV.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    normalize_field_size_limit()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_rows: List[Dict[str, str]] = []
    likely_rows: List[Dict[str, str]] = []
    related_rows: List[Dict[str, str]] = []
    ambiguous_rows: List[Dict[str, str]] = []
    excluded_rows: List[Dict[str, str]] = []
    classification_counts: Counter[str] = Counter()
    likely_by_la: Dict[str, int] = defaultdict(int)

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            classification = classify_row(row)
            if not classification:
                continue

            out_row = {column: row.get(column, "") for column in OUTPUT_COLUMNS}
            out_row.update(classification)

            all_rows.append(out_row)
            bucket = out_row["data_centre_classification"]
            classification_counts[bucket] += 1

            if bucket == "likely_data_centre":
                likely_rows.append(out_row)
                likely_by_la[out_row.get("PlanningAuthority", "")] += 1
            elif bucket == "data_centre_related_application":
                related_rows.append(out_row)
            elif bucket == "ambiguous_data_centre":
                ambiguous_rows.append(out_row)
            elif bucket == "excluded_non_data_centre":
                excluded_rows.append(out_row)

    def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    write_csv(args.output_dir / "all_data_centre_mentions.csv", all_rows)
    write_csv(args.output_dir / "likely_data_centres.csv", likely_rows)
    write_csv(args.output_dir / "data_centre_related_applications.csv", related_rows)
    write_csv(args.output_dir / "ambiguous_data_centres.csv", ambiguous_rows)
    write_csv(args.output_dir / "excluded_non_data_centre_mentions.csv", excluded_rows)

    summary_rows = [
        {"metric": "all_data_centre_mentions", "value": str(len(all_rows))},
        {"metric": "likely_data_centres", "value": str(len(likely_rows))},
        {"metric": "data_centre_related_applications", "value": str(len(related_rows))},
        {"metric": "ambiguous_data_centres", "value": str(len(ambiguous_rows))},
        {"metric": "excluded_non_data_centre_mentions", "value": str(len(excluded_rows))},
    ]
    with (args.output_dir / "data_centre_exploration_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(summary_rows)

    with (args.output_dir / "likely_data_centres_by_la.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["PlanningAuthority", "likely_data_centres"])
        writer.writeheader()
        for planning_authority, count in sorted(likely_by_la.items(), key=lambda item: (-item[1], item[0])):
            writer.writerow({"PlanningAuthority": planning_authority, "likely_data_centres": count})

    print(
        json.dumps(
            {
                "input": str(args.input),
                "output_dir": str(args.output_dir),
                "all_data_centre_mentions": len(all_rows),
                "likely_data_centres": len(likely_rows),
                "data_centre_related_applications": len(related_rows),
                "ambiguous_data_centres": len(ambiguous_rows),
                "excluded_non_data_centre_mentions": len(excluded_rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
