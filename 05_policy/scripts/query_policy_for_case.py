#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
CURRENT_DIR = ROOT / "05_policy" / "current"


def main() -> None:
    parser = argparse.ArgumentParser(description="Show top retrieved policy chunks for a Dublin case.")
    parser.add_argument("--case-key", required=True, help="case_key to inspect")
    parser.add_argument("--top-k", type=int, default=5, help="number of matches to show")
    args = parser.parse_args()

    predictions = pd.read_csv(CURRENT_DIR / "dublin_refusal_predictions.csv")
    matches = pd.read_csv(CURRENT_DIR / "dublin_case_policy_matches.csv")

    pred = predictions[predictions["case_key"] == args.case_key]
    if pred.empty:
        raise SystemExit(f"case_key not found: {args.case_key}")
    row = pred.iloc[0]
    print(f"case_key: {row['case_key']}")
    print(f"authority: {row['PlanningAuthority']}")
    print(f"policy probability: {row['policy_refusal_probability']:.3f}")
    print(f"prediction band: {row['prediction_band']}")
    print(f"coverage flag: {row['policy_coverage_flag']}")
    print(f"explanation: {row['grounded_policy_explanation']}")
    print()

    subset = matches[matches["case_key"] == args.case_key].sort_values("rank").head(args.top_k)
    for _, match in subset.iterrows():
        print(f"[{int(match['rank'])}] {match['document_label']} | {match['page_range']} | score={match['similarity_score']:.3f}")
        print(f"section: {match['section_title']}")
        print(f"themes: {match['policy_theme_tags']}")
        print(f"text: {str(match['chunk_text_preview'])[:400]}")
        print()


if __name__ == "__main__":
    main()
