#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "07_solar" / "source_data" / "eirgrid_contracted_non_wind_2025-11-28.pdf"
DEFAULT_OUTPUT = ROOT / "07_solar" / "source_data" / "eirgrid_contracted_non_wind_solar_2025-11-28.csv"


ROW_RE = re.compile(
    r"^(?P<node>.+?)\s+"
    r"(?P<voltage>\d+\s*kV)\s+"
    r"(?P<ref>(?:TG|D)\d+[a-zA-Z]?)\s+"
    r"(?P<name>.+?)\s+"
    r"(?P<processing>ECP-[\d.]+|Non GPA)\s+"
    r"(?P<type>Solar \+ Battery|Wind \+ Solar|Solar)\s+"
    r"(?P<mec>\d+\.\d)\s+"
    r"(?P<signed>[A-Z][a-z]{2}\s+\d{4})$"
)


def clean_text(text: str) -> str:
    replacements = {
        "Solar + \nBattery": "Solar + Battery",
        "Wind + \nSolar": "Wind + Solar",
        "Battery \nStorage": "Battery Storage",
        "Node and Associated \nVoltage Ref Name Processing \nType Type MEC \n(MW) \nSigned \nDate*": "",
        "Node and \nAssociated Voltage Ref Name Processing \nType Type MEC \n(MW) \nSigned \nDate*": "",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def extract_rows(pdf_path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    reader = PdfReader(str(pdf_path))
    for page in reader.pages:
        text = clean_text(page.extract_text() or "")
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line or "Contracted TSO" in line or line.startswith("Page ") or line.startswith("Total TSO"):
                continue
            match = ROW_RE.match(line)
            if not match:
                continue
            rows.append(
                {
                    "eirgrid_node": match.group("node"),
                    "eirgrid_voltage": match.group("voltage"),
                    "eirgrid_ref": match.group("ref"),
                    "eirgrid_project_name": match.group("name"),
                    "eirgrid_processing_type": match.group("processing"),
                    "eirgrid_generator_type": match.group("type"),
                    "eirgrid_mec_mw": match.group("mec"),
                    "eirgrid_signed_date": match.group("signed"),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract solar-related rows from the EirGrid contracted non-wind PDF.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = extract_rows(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "eirgrid_node",
                "eirgrid_voltage",
                "eirgrid_ref",
                "eirgrid_project_name",
                "eirgrid_processing_type",
                "eirgrid_generator_type",
                "eirgrid_mec_mw",
                "eirgrid_signed_date",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        json.dumps(
            {
                "input": str(args.input),
                "output": str(args.output),
                "rows": len(rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
