#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "07_solar" / "source_data" / "ambiguous_solar_mentions.csv"
DEFAULT_OUTPUT = ROOT / "07_solar" / "source_data" / "ambiguous_solar_bucketed.csv"
DEFAULT_SUMMARY = ROOT / "07_solar" / "source_data" / "ambiguous_solar_bucket_summary.csv"


def normalize(text: str) -> str:
    return " ".join((text or "").split())


def has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.I) is not None


def hectare_values(text: str) -> List[float]:
    values: List[float] = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:ha|hectares)\b", text, re.I):
        try:
            values.append(float(match.group(1)))
        except ValueError:
            continue
    return values


def bucket_description(desc: str) -> Tuple[str, str, str]:
    text = normalize(desc)
    hectares = hectare_values(text)
    has_large_site = any(value >= 5 for value in hectares)
    explicit_utility = has(
        text,
        r"solar pv farm|solar photovoltaic \(pv\) farm|solar pv energy development|construction and operation of solar pv arrays|export capacity|export up to \d+mw|to the national grid|110kV substation|client substation|electrical substation compound|transformer compound|mainscourt solar dac|development of a solar photovolt|construction of a solar photovolt|ground - mounted solar phot|ground-mounted solar phot",
    )
    rooftop_heavy = has(
        text,
        r"licensed discount foodstore|discount foodstore|retail sales area|rooftop photovoltaic solar panel array|rooftop solar array|existing hotel|existing buildings|existing shed|existing broiler houses",
    )

    if "temporary 120m high lattice type meteorological mast" in text:
        return (
            "solar_misc_nonfarm",
            "exclude_from_primary_map",
            "solar only refers to an ancillary aviation light on a met mast",
        )

    if text == "Permission for 10 years for development. The proposed development of a solar":
        return (
            "utility_scale_candidate",
            "include_primary",
            "truncated description strongly suggests a 10-year solar development application",
        )

    if text == "PERMISSION FOR THE DEVELOPMENT OF A SOLAR P.V. PANEL ARRAY COMPRISING OF APPROXI":
        return (
            "utility_scale_candidate",
            "include_primary",
            "truncated description strongly suggests a larger solar panel array application",
        )

    if text == "DEVELOPMENT WILL CONSIST OF A 10 YEAR PERMISSION FOR THE CONSTRUCTION OF A SOLAR":
        return (
            "utility_scale_candidate",
            "include_primary",
            "truncated description strongly suggests a utility-scale solar application",
        )

    if text == "Retention permission is sought for the following: -Provision of solar":
        return (
            "rooftop_or_building_pv",
            "exclude_from_primary_map",
            "truncated retention description reads as a small-scale solar installation",
        )

    if has(text, r"modification/optimisation of the permitted solar array|amendments to the development permitted|amendment to the existing granted application|amendment planning application to the previously granted permission|amendments to an approved solar development|connect the permitted .* solar array|extension of duration of planning ref.*ground-mounted solar photovoltaic|permitted solar farm|consented development .* solar|grid connection infrastructure .* solar photovoltaic|electricity control compound .* permitted .* solar array"):
        return (
            "utility_scale_related_application",
            "include_primary",
            "application looks tied to an existing solar farm or solar energy development",
        )

    if explicit_utility or (
        has_large_site
        and has(text, r"ground mounted|ground-mounted|mounted on metal frames|mounted on fixed-tilt frames|internal access tracks|inverter|transformer|security fencing|cctv|underground cabling|temporary construction compound")
        and not rooftop_heavy
    ) or has(text, r"up to 5mw|up to 50mw|19\.48 mwp|maximum export capacity|temporary \(27 years\) ground"):
        return (
            "utility_scale_candidate",
            "include_primary",
            "large ground-mounted solar wording or grid/export language suggests a farm-scale project",
        )

    if has(text, r"solar thermal collector|solar collector|solar walk installations|solar drinking trough|solar pumps|solar powered lighting|solar lighting|solar public light columns|solar street lights|solar panel lights|solar powered luminaires|solar powered light|solar structure|solar powered \(solar\) aviation light|ornamental pump|smart solar compacting bins|wind turbine and a battery|integrated lights|solar electric|11kw solar system|kids activity shelter with solar panel electricity generation|instalation of solar panel \(thermal\)"):
        return (
            "solar_misc_nonfarm",
            "exclude_from_primary_map",
            "solar is present, but not as a solar farm or PV generation project",
        )

    if has(text, r"wastewater|treatment plant|pumping station|wwtp|storm water|aeration tank|settlement tanks|sewer"):
        return (
            "ancillary_infrastructure_pv",
            "exclude_from_primary_map",
            "solar appears ancillary to water or utility infrastructure",
        )

    if has(text, r"telecommunications?|telecommunication|antenna|dishes|communications cabin|support structure"):
        return (
            "telecom_compound_pv",
            "exclude_from_primary_map",
            "solar appears ancillary to a telecom compound",
        )

    if has(text, r"car port|carport|car park with .*solar|solar car port|solar carport|solar carports"):
        return (
            "carport_or_canopy_pv",
            "exclude_from_primary_map",
            "solar appears to be a carport or canopy installation",
        )

    if has(text, r"\broof\b|rooftop|roof-mounted|roof mounted|roof level|mounted on the roof|mounted to the roof|roof slope|flat roof|south facing roof|existing profiled metal roof|rear roof|on 2 existing buildings|existing broiler houses|existing shed|cold store and loading bay buildings|rear pitch of the existing roo|solar panel on second storey flat|single storey flat to rear|install a solar panel system to rear|retention of repositioned solar panel|15 no\. residential units .* solar pan|new single storey rear extension .* solar panel|installation of 93 no\. solar p\.v\. panels|retention permission is sought for development consisting of a solar panel|installation of solar pho$|installation of solar phot$"):
        return (
            "rooftop_or_building_pv",
            "exclude_from_primary_map",
            "solar appears building-mounted",
        )

    if has(text, r"mushroom|farm comprising|milking parlour|slatted|silage|livestock|agricultural|cattle|dairy|meal bin|calving|straw|suckler"):
        if has(text, r"ground mounted|ground-mounted|mounted on the ground"):
            return (
                "agricultural_onsite_ground_mount",
                "exclude_from_primary_map",
                "ground-mounted solar appears ancillary to an agricultural operation",
            )
        return (
            "agricultural_onsite_pv",
            "exclude_from_primary_map",
            "solar appears ancillary to an agricultural operation",
        )

    if has(text, r"school|nursing home|swimming pool|gym|sports|community centre|factory|manufacturing|mill|industrial|business park|warehouse|shop|retail|airport|research lab|research station|hostel|tourism|glamping|pods|wellness|cafe|marine research|office building"):
        if has(text, r"ground mounted|ground-mounted|ground level|distributed over grass|mounted on metal frames|mounted on frames/support"):
            return (
                "onsite_nonfarm_ground_mount",
                "exclude_from_primary_map",
                "ground-mounted solar appears ancillary to a non-farm site",
            )
        return (
            "onsite_nonfarm_pv",
            "exclude_from_primary_map",
            "solar appears ancillary to a non-farm site",
        )

    if has(text, r"ground mounted|ground-mounted|ground fixed|free standing solar array|surface-mounted solar array|mounted on the ground|fixed to metal frames|mounted on frames/supports|array consisting of up to .*kwp|distributed over grass|on-site solar panel array|solar energy collection installation at existing hotel|solar panel array \(16 kw hours\)|installation of approx\.? 600 sq\.?m\.? of solar pan|installation of approx 600sq/m of solar pane|retention of the following: solar panel array|installation of solar photo vol|erection/installation of a solar panel array \(16 kw hou|retention and completion of the installation of a solar photo vol"):
        return (
            "small_or_medium_ground_mount",
            "secondary_map_optional",
            "ground-mounted solar is present, but the wording looks smaller-scale or on-site rather than farm-scale",
        )

    if has(text, r"\bsolar panels\b|\bphotovoltaic\b|\bpv\b"):
        return (
            "general_small_scale_pv",
            "exclude_from_primary_map",
            "solar is mentioned but reads as small-scale or ancillary",
        )

    return (
        "needs_manual_review",
        "review",
        "description did not match a stable review bucket",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bucket the ambiguous solar mentions into mapping-friendly categories.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    max_limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_limit)
            break
        except OverflowError:
            max_limit //= 10

    rows: List[Dict[str, str]] = []
    bucket_counts: Counter[str] = Counter()
    map_counts: Counter[str] = Counter()

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or []) + [
            "ambiguous_review_bucket",
            "map_relevance",
            "ambiguous_review_note",
        ]
        for row in reader:
            bucket, map_relevance, note = bucket_description(row.get("DevelopmentDescription", ""))
            row["ambiguous_review_bucket"] = bucket
            row["map_relevance"] = map_relevance
            row["ambiguous_review_note"] = note
            rows.append(row)
            bucket_counts[bucket] += 1
            map_counts[map_relevance] += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with args.summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["type", "name", "count"])
        writer.writeheader()
        for bucket, count in bucket_counts.most_common():
            writer.writerow({"type": "bucket", "name": bucket, "count": count})
        for map_relevance, count in map_counts.most_common():
            writer.writerow({"type": "map_relevance", "name": map_relevance, "count": count})

    print(
        json.dumps(
            {
                "input": str(args.input),
                "output": str(args.output),
                "summary": str(args.summary),
                "rows": len(rows),
                "bucket_counts": dict(bucket_counts),
                "map_relevance_counts": dict(map_counts),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
