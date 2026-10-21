#!/usr/bin/env python3
"""Build tier audit packs (high or medium) from the pending candidate queue."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"

INSTRUCTIONS = """# WHAT TO DO — revision-linkage audit ({tier} tier)

## Why this batch matters

Each accepted row becomes a verified resubmission pair. These pairs are the raw
material for the alteration-effect tables ("reducing units preceded grants in
X of Y audited resubmissions") and for the recommendation backtest. More pairs
= stronger evidence for every product claim.

Expected acceptance for this tier: ~{expected}% of rows.

## How much to do

The file contains {rows} rows in deterministic order. All are useful; partial
progress is usable. Leave unreviewed rows with `manual_review_status` blank.

## Step 1 - Review the rows

For each row:

1. Open both `original_source_url` and `revised_source_url`.
2. Decide whether the later application is genuinely a revised submission for
   the same physical development (not merely another application at the same
   address).
3. Fill in the four review columns:

| Column | Allowed values | Meaning |
|---|---|---|
| `manual_review_status` | `accepted`, `rejected`, `pending` | accepted = same development resubmitted; rejected = different/not provable; pending = genuinely unsure |
| `manual_review_notes` | free text | Why you decided as you did |
| `reviewer` | your name | Who reviewed the row |
| `reviewed_at` | date | When you reviewed the row |

Do not modify any other column. If the register is unreachable, mark `pending`
with a note - do not guess.

## Step 2 - Save

Save the completed file in this same folder as `review_rows_fixed.csv`.
Do not overwrite the original `review_rows.csv`.

## What happens next

Labels are carried into the queue, canonical records rebuild, and the
improvement cycle re-measures every model and the alteration-effect tables.
"""

EXPECTED = {"high": "93.5", "medium": "80"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", type=str, default="high", choices=["high", "medium"])
    parser.add_argument("--sample", type=int, default=None, help="rows to include (default: all pending in the tier)")
    parser.add_argument("--queue-file", type=Path, default=None, help="candidate queue CSV (default: granted-arm queue)")
    parser.add_argument("--exclude-fixed", type=Path, default=None, help="audit fixed CSV whose rows are excluded from the new pack")
    args = parser.parse_args()

    today = date.today().isoformat()
    tag = "rr_" if args.queue_file else ""
    out_dir = CURRENT / f"{tag}{args.tier}_tier_audit_{today}"

    queue_path = args.queue_file or (CURRENT / "full_revision_candidate_queue.csv")
    queue = pd.read_csv(queue_path, low_memory=False)
    pending = queue[
        (queue["linkage_tier"] == args.tier)
        & (queue["manual_review_status"].fillna("pending").astype(str).str.strip().str.lower() == "pending")
    ].copy()
    if args.exclude_fixed and args.exclude_fixed.exists():
        fixed = pd.read_csv(args.exclude_fixed, low_memory=False)
        audited = set(zip(fixed["original_case_key"].astype(str), fixed["revised_case_key"].astype(str)))
        pending["_key"] = list(zip(pending["original_case_key"].astype(str), pending["revised_case_key"].astype(str)))
        pending = pending[~pending["_key"].isin(audited)].drop(columns="_key")
    pending["_order"] = [
        hashlib.sha256(f"{today}|{original}|{revised}".encode("utf-8")).hexdigest()
        for original, revised in zip(pending["original_case_key"], pending["revised_case_key"])
    ]
    sample = pending.sort_values("_order")
    if args.sample:
        sample = sample.head(args.sample)
    sample = sample.drop(columns="_order")
    sample["manual_review_status"] = ""
    sample["manual_review_notes"] = ""
    sample["reviewer"] = ""
    sample["reviewed_at"] = ""
    out_dir.mkdir(parents=True, exist_ok=True)
    sample.to_csv(out_dir / "review_rows.csv", index=False)
    (out_dir / "INSTRUCTIONS.md").write_text(
        INSTRUCTIONS.format(tier=args.tier, rows=len(sample), expected=EXPECTED[args.tier]),
        encoding="utf-8",
    )
    summary = {
        "tier": args.tier,
        "pending_in_tier": int(len(pending)),
        "audit_rows": int(len(sample)),
        "expected_acceptance_rate": EXPECTED[args.tier] + "%",
        "note": f"Save the completed file as review_rows_fixed.csv in {out_dir.name}.",
    }
    (out_dir / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
