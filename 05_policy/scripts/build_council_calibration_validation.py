#!/usr/bin/env python3
"""Run the council-aware calibration validation on the frozen 2025 predictions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from council_calibration import evaluate_council_calibration, fit_council_calibrators

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
PREDICTIONS = OUTPUT_DIR / "raw_planning_v3_2025_predictions.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS)
    parser.add_argument("--minimum-samples", type=int, default=100)
    args = parser.parse_args()

    predictions = pd.read_csv(args.predictions)
    predictions["received_date_dt"] = pd.to_datetime(predictions["received_date_dt"], utc=True, errors="coerce")
    split = pd.Timestamp("2025-07-01", tz="UTC")
    fit_frame = predictions[predictions["received_date_dt"] < split].copy()
    eval_frame = predictions[predictions["received_date_dt"] >= split].copy()

    council_calibrators, national, diagnostics = fit_council_calibrators(
        fit_frame, minimum_samples=args.minimum_samples
    )
    evaluation = evaluate_council_calibration(eval_frame, council_calibrators, national)
    payload = {
        "source": str(args.predictions.resolve()),
        "fit_window": [str(fit_frame["received_date_dt"].min()), str(fit_frame["received_date_dt"].max())],
        "eval_window": [str(eval_frame["received_date_dt"].min()), str(eval_frame["received_date_dt"].max())],
        "fit_rows": int(len(fit_frame)),
        "fit_diagnostics": diagnostics,
        "evaluation": evaluation,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "raw_planning_v3_council_calibration_validation.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    rows = []
    for council, metrics in evaluation["by_council"].items():
        rows.append({"authority": council, **metrics})
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "raw_planning_v3_council_calibration_by_authority.csv", index=False)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
