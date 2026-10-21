#!/usr/bin/env python3
"""Score the refusal-theme tagging verification when the completed pack returns."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "02_development" / "current" / "theme_tagging_verification_2026-09-09"

THEMES = [
    "density_scale", "design_layout", "traffic_access", "residential_amenity",
    "flooding_drainage", "land_use_policy", "premature_or_info_gap",
    "heritage_archaeology", "ecology_trees", "water_wastewater", "other",
]


def _tags(value: object) -> set[str]:
    return {part.strip().lower() for part in str(value or "").split(";") if part.strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "02_development" / "current" / "theme_tagging_verification_fixed.csv",
        help="completed verification CSV (defaults to the original theme-tagging pack)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "02_development" / "current" / "theme_tagging_scoring.json",
        help="scoring JSON output path",
    )
    args = parser.parse_args()
    verification_path = args.input
    if not verification_path.exists():
        raise FileNotFoundError(f"{verification_path} not found - wait for the completed pack.")
    frame = pd.read_csv(verification_path, low_memory=False)
    frame = frame[frame["verified_tags"].fillna("").astype(str).str.strip().ne("")].copy()
    results = {"verified_rows": int(len(frame))}

    per_theme = {}
    for theme in THEMES:
        tp = fp = fn = 0
        for _, row in frame.iterrows():
            extracted = _tags(row.get("extracted_tags"))
            verified = _tags(row.get("verified_tags"))
            if theme in extracted and theme in verified:
                tp += 1
            elif theme in extracted and theme not in verified:
                fp += 1
            elif theme not in extracted and theme in verified:
                fn += 1
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        per_theme[theme] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(2 * precision * recall / (precision + recall), 4) if precision and recall else None,
        }
    top1_correct = 0
    for _, row in frame.iterrows():
        if _tags(row.get("extracted_top_tag")) == _tags(row.get("verified_top_tag")):
            top1_correct += 1
    total_tp = sum(per_theme[theme]["tp"] for theme in THEMES)
    total_fp = sum(per_theme[theme]["fp"] for theme in THEMES)
    total_fn = sum(per_theme[theme]["fn"] for theme in THEMES)
    results["per_theme"] = per_theme
    results["top1_accuracy"] = round(top1_correct / len(frame), 4)
    results["overall_micro_precision"] = round(total_tp / (total_tp + total_fp), 4) if total_tp + total_fp else None
    results["overall_micro_recall"] = round(total_tp / (total_tp + total_fn), 4) if total_tp + total_fn else None
    results["caveat"] = "Measured against human review of the decision texts; sample stratified across themes."
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
