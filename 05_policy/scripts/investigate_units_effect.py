#!/usr/bin/env python3
"""Investigate the counterintuitive units direction in the structured candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from structured_optimiser import build_cohort, split_temporal

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
DEFAULT_SOURCE = ROOT / "02_development" / "current" / "height_storeys_extraction_2026-09-04" / "ground_source_storeys_verified.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()

    cohort = build_cohort(pd.read_csv(args.source, low_memory=False))
    cohort["unit_band"] = pd.cut(
        cohort["log_units"].map(np.expm1),
        bins=[0, 12, 20, 40, 80, 150, np.inf],
        labels=["10-11", "12-19", "20-39", "40-79", "80-149", "150+"],
        right=False,
    )
    by_band = cohort.groupby("unit_band", observed=False).agg(
        rows=("target_refused", "size"),
        refusal_rate=("target_refused", "mean"),
        median_storeys=("storeys", "median"),
        median_density=("density_units_per_ha", "median"),
    ).reset_index()
    by_band_and_authority = cohort.groupby(["PlanningAuthority", "unit_band"], observed=False).agg(
        rows=("target_refused", "size"),
        refusal_rate=("target_refused", "mean"),
    ).reset_index()
    by_band_and_authority = by_band_and_authority[
        (by_band_and_authority["unit_band"] == "10-11") | (by_band_and_authority["unit_band"] == "150+")
    ]
    by_band_and_authority = by_band_and_authority[by_band_and_authority["rows"] >= 5].sort_values("rows", ascending=False)

    results = {
        "observation": (
            "In the sensitivity sweep, holding density, storeys and authority constant, "
            "increasing units lowered the modelled refusal probability - counterintuitive."
        ),
        "by_unit_band": json.loads(by_band.to_json(orient="records")),
        "by_band_and_authority": json.loads(by_band_and_authority.to_json(orient="records")),
        "explanation_candidates": [
            "Large schemes in the GE10 cohort may be better-resourced SDZ/apartment projects with lower refusal rates, while 10-11 unit schemes are often contentious small estates.",
            "At fixed density, more units implies a larger site, so the 'units' sweep is confounded with site size, which the model may treat as protective.",
            "The cohort skews to granted large schemes because refusals are harder to extract for them.",
        ],
        "caveat": "This is cohort-level association, not causal evidence.",
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "raw_planning_structured_units_effect_investigation.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, indent=2)[:4000])


if __name__ == "__main__":
    main()
