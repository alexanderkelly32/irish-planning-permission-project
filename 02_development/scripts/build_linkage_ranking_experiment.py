#!/usr/bin/env python3
"""Run the conservative labelled candidate-ranking experiment and write outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from evaluate_linkage_ranking import (
    build_labelled_frame,
    evaluate_labelled_ranking,
    review_order_analysis,
)

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
DEFAULT_QUEUE = CURRENT / "full_revision_candidate_queue.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260902)
    args = parser.parse_args()

    queue = pd.read_csv(args.queue, low_memory=False)
    frame = build_labelled_frame(queue)
    results = evaluate_labelled_ranking(frame, n_splits=args.n_splits, seed=args.seed)
    results["review_order"] = review_order_analysis(queue)
    results["source"] = str(args.queue.resolve())
    results["labelled_sources"] = [
        "full_revision_manual_review_pilot_fixed.csv",
        "project_revision_pair_audit.csv",
    ]

    CURRENT.mkdir(parents=True, exist_ok=True)
    (CURRENT / "linkage_ranking_experiment_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    frame.to_csv(CURRENT / "linkage_ranking_labelled_frame.csv", index=False)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
