#!/usr/bin/env python3
"""Observed outcome rates by lever value band (the observational contrast behind
'changing this lever' claims). Association only - never causal."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
DEFAULT_SOURCE = ROOT / "02_development" / "current" / "height_storeys_extraction_2026-09-04" / "ground_source_storeys_verified.csv"

sys = __import__("sys")
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from structured_optimiser import build_cohort

BANDS = {
    "max_storeys": [(1, 1, "1"), (2, 2, "2"), (3, 3, "3"), (4, 4, "4"), (5, 100, "5+")],
    "units": [(10, 19, "10-19"), (20, 39, "20-39"), (40, 79, "40-79"), (80, 2000, "80+")],
    "parking_spaces": [(0, 9, "0-9"), (10, 29, "10-29"), (30, 59, "30-59"), (60, 10000, "60+")],
}


def observed_rates(cohort: pd.DataFrame) -> dict:
    rates = {}
    for field, bands in BANDS.items():
        column = {
            "max_storeys": "storeys",
            "units": "units_total_best",
            "parking_spaces": "parking_spaces_best",
        }[field]
        if column not in cohort.columns:
            continue
        values = pd.to_numeric(cohort[column], errors="coerce")
        rows = []
        for low, high, label in bands:
            band = cohort[(values >= low) & (values <= high)]
            if len(band) < 10:
                continue
            refusal = band["target_refused"].mean()
            rows.append({
                "band": label,
                "cases": int(len(band)),
                "observed_refusal_rate": round(float(refusal), 4),
                "observed_grant_rate": round(float(1.0 - refusal), 4),
            })
        rates[field] = rows
    return rates


def main() -> None:
    cohort = build_cohort(pd.read_csv(DEFAULT_SOURCE, low_memory=False))
    payload = {
        "cohort_rows": int(len(cohort)),
        "cohort_refusal_rate": round(float(cohort["target_refused"].mean()), 4),
        "rates": observed_rates(cohort),
        "caveat": (
            "Observed historical grant/refusal rates by lever band within the GE10 structured cohort. "
            "These are observational associations across different schemes, not causal effects of "
            "changing the lever; scheme mix differs between bands."
        ),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "lever_outcome_rates_2026-09-09.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
