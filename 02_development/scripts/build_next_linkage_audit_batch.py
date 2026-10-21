#!/usr/bin/env python3
"""Cut the next deterministic linkage audit batch from the pending review sample."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
DEFAULT_SAMPLE = CURRENT / "full_revision_manual_review_sample.csv"


def build_audit_batch(sample: pd.DataFrame, per_tier: int = 100, tiers: tuple[str, ...] = ("high", "medium", "low")) -> pd.DataFrame:
    """Take the first per_tier hash-ordered pending rows from each requested tier."""
    missing = {"original_case_key", "revised_case_key", "linkage_tier", "manual_review_status"}.difference(sample.columns)
    if missing:
        raise ValueError(f"sample is missing columns: {', '.join(sorted(missing))}")
    frame = sample.copy()
    frame["manual_review_status"] = frame["manual_review_status"].fillna("pending").astype(str).str.strip().str.lower()
    pending = frame[frame["manual_review_status"] == "pending"]
    selected = []
    for tier in tiers:
        group = pending[pending["linkage_tier"].astype(str).str.lower() == tier]
        selected.append(group.head(max(0, per_tier)))
    if not selected:
        return pending.iloc[0:0].copy()
    batch = pd.concat(selected, ignore_index=True)
    batch["manual_review_status"] = ""
    batch["manual_review_notes"] = ""
    batch["reviewer"] = ""
    batch["reviewed_at"] = ""
    return batch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--per-tier", type=int, default=100)
    parser.add_argument("--tiers", type=str, default="high,medium,low",
                        help="comma-separated tiers to include")
    parser.add_argument("--out-dir", type=Path, default=CURRENT / "linkage_audit_batch_2026-09-04")
    args = parser.parse_args()

    tiers = tuple(part.strip().lower() for part in args.tiers.split(",") if part.strip())
    sample = pd.read_csv(args.sample, low_memory=False)
    batch = build_audit_batch(sample, per_tier=args.per_tier, tiers=tiers)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    batch.to_csv(args.out_dir / "review_rows.csv", index=False)
    diagnostics = {
        "source": str(args.sample.resolve()),
        "batch_row_count": int(len(batch)),
        "rows_by_tier": batch["linkage_tier"].value_counts().to_dict() if not batch.empty else {},
        "selection": "first hash-ordered pending rows per tier (deterministic, effectively random within tier)",
        "status": "labels_blank_for_independent_review",
    }
    (args.out_dir / "batch_diagnostics.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()
