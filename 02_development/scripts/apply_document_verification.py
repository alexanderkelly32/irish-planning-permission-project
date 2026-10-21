#!/usr/bin/env python3
"""Overlay the human-extracted verified tier onto the document campaign."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from structured_document_extraction import apply_human_verification

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "02_development" / "current" / "document_extraction_campaign_2026-09-04"
DEFAULT_MERGED = OUT_DIR / "ground_source_document_extracted.csv"
DEFAULT_HUMAN = ROOT / "02_development" / "current" / "document_extraction_review_fixed.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--human", type=Path, default=DEFAULT_HUMAN)
    args = parser.parse_args()

    merged = pd.read_csv(args.merged, low_memory=False)
    human = pd.read_csv(args.human, low_memory=False)
    verified, metrics = apply_human_verification(merged, human)
    verified.to_csv(OUT_DIR / "ground_source_document_verified.csv", index=False)
    metrics["verified_output"] = str(OUT_DIR / "ground_source_document_verified.csv")
    (OUT_DIR / "document_verification_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
