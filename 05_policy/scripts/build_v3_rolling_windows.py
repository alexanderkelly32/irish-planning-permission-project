#!/usr/bin/env python3
"""Report monthly, quarterly and cumulative temporal robustness for frozen Model v3."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from validate_v3_rolling_windows import window_summaries

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
PREDICTIONS = OUTPUT_DIR / "raw_planning_v3_2025_predictions.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS)
    args = parser.parse_args()

    predictions = pd.read_csv(args.predictions)
    summary, diagnostics = window_summaries(predictions)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_DIR / "raw_planning_v3_2025_monthly_validation.csv", index=False)
    payload = {
        "source": str(args.predictions.resolve()),
        "windows": diagnostics[0]["window_summary"],
        "single_class_blocks": diagnostics[0]["single_class_blocks"],
        "small_blocks_under_100_rows": diagnostics[0]["small_blocks_under_100_rows"],
        "caveat": diagnostics[0]["caveat"],
    }
    (OUTPUT_DIR / "raw_planning_v3_2025_rolling_windows.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
