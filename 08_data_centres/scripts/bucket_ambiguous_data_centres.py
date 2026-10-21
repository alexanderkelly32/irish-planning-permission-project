#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "08_data_centres" / "source_data" / "ambiguous_data_centres.csv"
DEFAULT_OUTPUT = ROOT / "08_data_centres" / "source_data" / "ambiguous_data_centres_bucketed.csv"
DEFAULT_SUMMARY = ROOT / "08_data_centres" / "source_data" / "ambiguous_data_centres_bucket_summary.csv"

OVERRIDES: Dict[str, Tuple[str, str]] = {
    "clare_county_council_17583": (
        "promote_primary_data_centre",
        "Mixed-use business campus block, but the description explicitly assigns lower floors to data-centre use.",
    ),
    "clare_county_council_221062": (
        "promote_related_application",
        "This is the extension-of-duration follow-on to the reviewed Westpark mixed-use block with explicit data-centre floors.",
    ),
    "tipperary_county_council_21953": (
        "exclude_non_data_centre",
        "The wording refers to an existing building called a data processing facility, but the application is for change of use to recycling rather than a data centre.",
    ),
    "tipperary_county_council_211156": (
        "exclude_non_data_centre",
        "The wording refers to an existing building called a data processing facility, but the application is for change of use to recycling rather than a data centre.",
    ),
    "tipperary_county_council_211279": (
        "exclude_non_data_centre",
        "The wording refers to an existing building called a data processing facility, but the application is for change of use to recycling rather than a data centre.",
    ),
    "louth_county_council_24226": (
        "promote_small_specialised_data_centre",
        "Telephone exchange conversion to telecoms data-centre use reads as a genuine specialised data-centre application.",
    ),
    "south_dublin_county_council_ed17_0028": (
        "promote_small_specialised_data_centre",
        "Warehouse change of use to a data centre is small, but still an explicit data-centre use.",
    ),
    "south_dublin_county_council_sd20a_0272": (
        "promote_small_specialised_data_centre",
        "Disaster recovery and business continuity wording points to a dedicated resilient IT facility rather than an ordinary server room.",
    ),
    "south_dublin_county_council_sd21a_0346": (
        "promote_small_specialised_data_centre",
        "Ancillary external data-centre unit within a manufacturing campus is still a real on-site data-centre facility.",
    ),
    "fingal_county_council_fw20a_0087_": (
        "promote_primary_data_centre",
        "Even with a truncated source description, the case clearly states construction of three data-hall buildings with ancillary offices.",
    ),
    "dublin_city_council_3577_20": (
        "promote_related_application",
        "This is an internal change within an existing data-hall building, so it belongs with related applications rather than as a new site.",
    ),
}

PROMOTE_PRIMARY_PATTERNS = [
    re.compile(r"mixed use|mixed-use", re.I),
    re.compile(r"data centre/light industrial|data centre\s*/?\s*light industrial", re.I),
]

PROMOTE_SMALL_SPECIALISED_PATTERNS = [
    re.compile(r"telephone exchange .* data cent(?:re|er)|exchange use .* data cent(?:re|er)", re.I),
    re.compile(r"change of use .* data cent(?:re|er)", re.I),
    re.compile(r"disaster recovery|business continuity centre", re.I),
    re.compile(r"external data cent(?:re|er) unit", re.I),
]

PROMOTE_RELATED_PATTERNS = [
    re.compile(r"extension of duration|extend the appropriate period", re.I),
    re.compile(r"retention .* data cent(?:re|er) campus|building already in existence on the datacentre campus", re.I),
]

EXCLUDE_PATTERNS = [
    re.compile(r"\bdigital hub\b", re.I),
    re.compile(r"\bco-location\b|\bco location\b|\bcolocation\b", re.I),
    re.compile(r"\bICT rooms?\b|\bserver rooms?\b|\bcomputer rooms?\b", re.I),
    re.compile(r"communications structure|antennae|dishes|telecommunications equipment", re.I),
]


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def bucket_row(row: Dict[str, str]) -> Tuple[str, str]:
    case_key = row.get("case_key", "")
    if case_key in OVERRIDES:
        return OVERRIDES[case_key]

    desc = " ".join((row.get("DevelopmentDescription", "") or "").split())

    for pattern in EXCLUDE_PATTERNS:
        if pattern.search(desc):
            return (
                "exclude_non_data_centre",
                "Lookalike wording still reads as telecom, digital-hub, or room-level IT rather than a data-centre project.",
            )

    for pattern in PROMOTE_RELATED_PATTERNS:
        if pattern.search(desc):
            return (
                "promote_related_application",
                "The case looks like a follow-on application tied to an existing data-centre site.",
            )

    for pattern in PROMOTE_PRIMARY_PATTERNS:
        if pattern.search(desc) and re.search(r"data[\s-]*cent(?:re|er)", desc, re.I):
            return (
                "promote_primary_data_centre",
                "Mixed-use case still includes an explicit data-centre component worth plotting as a site.",
            )

    for pattern in PROMOTE_SMALL_SPECIALISED_PATTERNS:
        if pattern.search(desc):
            return (
                "promote_small_specialised_data_centre",
                "The wording points to a real but smaller or more specialised data-centre use.",
            )

    return (
        "needs_manual_review",
        "No rule or reviewed override promoted or excluded this edge case yet.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bucket ambiguous data-centre planning hits into reviewed promotion / exclusion categories.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    rows = load_rows(args.input)
    output_rows: List[Dict[str, str]] = []
    counts: Counter[str] = Counter()

    for row in rows:
        bucket, note = bucket_row(row)
        out_row = dict(row)
        out_row["ambiguous_review_bucket"] = bucket
        out_row["ambiguous_review_note"] = note
        output_rows.append(out_row)
        counts[bucket] += 1

    fieldnames = list(rows[0].keys()) + ["ambiguous_review_bucket", "ambiguous_review_note"] if rows else ["ambiguous_review_bucket", "ambiguous_review_note"]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    with args.summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ambiguous_review_bucket", "count"])
        writer.writeheader()
        for bucket, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            writer.writerow({"ambiguous_review_bucket": bucket, "count": count})

    print(
        json.dumps(
            {
                "input": str(args.input),
                "output": str(args.output),
                "summary": str(args.summary),
                "bucket_counts": dict(counts),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
