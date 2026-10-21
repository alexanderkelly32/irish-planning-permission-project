#!/usr/bin/env python3
"""Build the high-tier revision-pair audit pack.

Deterministic sample of pending high-tier refused->later-granted candidates.
Each accepted label grows the audited-pair dataset that feeds the lever
contrasts, the blind backtest and the recommendation evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"

INSTRUCTIONS = """# WHAT TO DO — high-tier linkage audit

## Why this batch matters

The refused-to-revised-to-granted queue has ~597 unlabelled high-tier candidates.
High-tier labels average 93.5% acceptance, so each reviewed row is very likely to
become a verified resubmission pair. Every accepted pair strengthens:

1. the lever-contrast table (which changes preceded grants vs refusals);
2. the blind backtest that validates the recommendation engine;
3. the "audited resubmission statistics" shown in the app.

## How much to do

The file contains 200 rows, all high tier, in deterministic order. All 200 are
useful; partial progress is usable. Leave unreviewed rows with
`manual_review_status` blank.

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

I will carry your resolved labels into the rebuilt candidate queue, rebuild the
canonical revision records, and re-run the improvement cycle so every model
metric re-measures against the enlarged ground truth.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=200)
    args = parser.parse_args()

    today = date.today().isoformat()
    out_dir = CURRENT / f"high_tier_audit_{today}"

    queue = pd.read_csv(CURRENT / "full_revision_candidate_queue.csv", low_memory=False)
    pending_high = queue[
        (queue["linkage_tier"] == "high")
        & (queue["manual_review_status"].fillna("pending").astype(str).str.strip().str.lower() == "pending")
    ].copy()
    pending_high["_order"] = [
        hashlib.sha256(f"{today}|{original}|{revised}".encode("utf-8")).hexdigest()
        for original, revised in zip(pending_high["original_case_key"], pending_high["revised_case_key"])
    ]
    sample = pending_high.sort_values("_order").head(args.sample).drop(columns="_order")
    sample["manual_review_status"] = ""
    sample["manual_review_notes"] = ""
    sample["reviewer"] = ""
    sample["reviewed_at"] = ""
    out_dir.mkdir(parents=True, exist_ok=True)
    sample.to_csv(out_dir / "review_rows.csv", index=False)
    (out_dir / "INSTRUCTIONS.md").write_text(INSTRUCTIONS, encoding="utf-8")
    summary = {
        "pending_high_tier_rows": int(len(pending_high)),
        "audit_rows": int(len(sample)),
        "note": "High-tier pending pairs, deterministic sample. Follow INSTRUCTIONS.md; save the completed file as review_rows_fixed.csv in this folder.",
    }
    (out_dir / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
