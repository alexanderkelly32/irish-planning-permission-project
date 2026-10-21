#!/usr/bin/env python3
"""Build the independent double-review slice from the completed pilot review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from double_review import build_double_review_slice

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
DEFAULT_PILOT = CURRENT / "full_revision_manual_review_pilot_fixed.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--per-tier", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260902)
    args = parser.parse_args()

    pilot = pd.read_csv(args.pilot, low_memory=False)
    slice_df = build_double_review_slice(pilot, per_tier=args.per_tier, seed=args.seed)
    resolved = pilot[
        pilot["manual_review_status"].fillna("pending").astype(str).str.strip().str.lower().isin({"accepted", "rejected"})
    ]
    diagnostics = {
        "source": str(args.pilot.resolve()),
        "resolved_pilot_row_count": int(len(resolved)),
        "double_review_slice_row_count": int(len(slice_df)),
        "slice_rows_by_tier": slice_df["linkage_tier"].value_counts().to_dict()
        if not slice_df.empty else {},
        "configuration": {"per_tier": args.per_tier, "seed": args.seed},
        "status": "labels_masked_for_independent_second_review",
    }

    CURRENT.mkdir(parents=True, exist_ok=True)
    slice_df.to_csv(CURRENT / "full_revision_double_review_slice.csv", index=False)
    (CURRENT / "full_revision_double_review_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )
    print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()
