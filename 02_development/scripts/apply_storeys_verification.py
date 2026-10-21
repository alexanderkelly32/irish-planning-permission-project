#!/usr/bin/env python3
"""Apply the completed verification sheet to the extraction output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from height_storeys_extraction import apply_verification

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "height_storeys_extraction_2026-09-04"
DEFAULT_MERGED = OUT_DIR / "ground_source_height_storeys_extracted.csv"
DEFAULT_VERIFICATION = OUT_DIR / "height_storeys_verification_sample_fixed.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--verification", type=Path, default=DEFAULT_VERIFICATION)
    args = parser.parse_args()

    merged = pd.read_csv(args.merged, low_memory=False)
    verification = pd.read_csv(args.verification, low_memory=False)
    verified_frame, metrics = apply_verification(merged, verification)
    verified_frame.to_csv(OUT_DIR / "ground_source_storeys_verified.csv", index=False)
    metrics["verified_output"] = str(OUT_DIR / "ground_source_storeys_verified.csv")
    (OUT_DIR / "verification_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
