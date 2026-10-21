#!/usr/bin/env python3
"""Readiness check for the v5 structured optimiser candidate.

Counts planner-report extraction coverage for the structured variables the v5
candidate needs (heights first, then storeys/parking/setbacks/separations) and
reports a verdict. Re-running the candidate before the targets are met is
noise, so this script is the gate.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "02_development" / "source_data" / "planner_reports"
OUT_PATH = ROOT / "02_development" / "current" / "v5_optimiser_readiness.json"

TARGETS = {
    "max_height_m": 300,
    "max_storeys": 200,
    "parking_spaces": 200,
    "upper_floor_setback_m": 150,
    "nearest_dwelling_separation_m": 100,
    "opposing_window_separation_m": 100,
    "communal_open_space_sqm": 100,
}

COLUMN_KEYS = {
    "max_height_m": ["height"],
    "max_storeys": ["storey"],
    "parking_spaces": ["parking"],
    "upper_floor_setback_m": ["setback"],
    "nearest_dwelling_separation_m": ["separation"],
    "opposing_window_separation_m": ["window"],
    "communal_open_space_sqm": ["communal", "open_space"],
}

ALL_KEYS_FIELDS = {"communal_open_space_sqm"}


def count_extraction_values() -> dict[str, int]:
    counts = {field: 0 for field in TARGETS}
    reports = 0
    for csv_path in REPORTS_DIR.rglob("report_ocr_extractions.csv"):
        frame = pd.read_csv(csv_path, low_memory=False)
        reports += len(frame)
        for field, keys in COLUMN_KEYS.items():
            if field in ALL_KEYS_FIELDS:
                columns = [
                    column for column in frame.columns
                    if all(key in column.lower() for key in keys)
                ]
            else:
                columns = [
                    column for column in frame.columns
                    if any(key in column.lower() for key in keys)
                ]
            if columns:
                counts[field] += int(frame[columns].notna().sum().sum())
    return {"reports": reports, **counts}


def build_readiness(counts: dict[str, int] | None = None) -> dict:
    counts = counts or count_extraction_values()
    fields = {}
    ready = True
    for field, target in TARGETS.items():
        current = counts.get(field, 0)
        met = current >= target
        ready = ready and met
        fields[field] = {
            "values": current,
            "target": target,
            "pct": round(current / target, 4) if target else None,
            "met": met,
        }
    return {
        "generated": date.today().isoformat(),
        "planner_reports": counts.get("reports", 0),
        "status": "ready" if ready else "blocked_on_insufficiency",
        "verdict": (
            "v5 candidate can be re-run with all variables at target density."
            if ready else
            "BLOCKED BY INSUFFICIENCY - re-running the structured candidate now would be noise."
        ),
        "fields": fields,
        "note": "Coverage counts non-null extracted values across council report_ocr_extractions.csv files.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    args = parser.parse_args()
    readiness = build_readiness()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(readiness, indent=2), encoding="utf-8")
    print(json.dumps(readiness, indent=2))


if __name__ == "__main__":
    main()
