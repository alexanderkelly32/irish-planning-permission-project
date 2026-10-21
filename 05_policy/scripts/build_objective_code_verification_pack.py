#!/usr/bin/env python3
"""Verification pack for the objective-code layer.

Samples 120 (council, period, code) rows - 60 from single-mention tail, 60
from higher-mention rows - with a context snippet for human review. Reviewer
marks is_real_code (yes/no) in the sheet; precision is computed against the
current objective_code_layer.csv.

Output: 05_policy/current/objective_code_verification_pack.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = ROOT / "05_policy" / "current"


def snippet(context: str, code: str, width: int = 220) -> str:
    context = str(context or "")
    marker = f" {code} "
    pos = context.lower().find(marker.lower())
    if pos < 0:
        pos = max(0, len(context) // 2)
    return context[max(0, pos - 60):pos + width]


def main() -> None:
    layer = pd.read_csv(POLICY_DIR / "objective_code_layer.csv")
    rng = pd.core.common.random_state(20260921)
    tail = layer[layer["mentions"] <= 2].sample(60, random_state=rng)
    head = layer[layer["mentions"] > 2].sample(60, random_state=rng)
    pack = pd.concat([tail, head], ignore_index=True)
    pack = pack[["council", "plan_period", "objective_code", "mentions", "mention_docs", "plan_document", "context"]].copy()
    pack["context_snippet"] = [
        snippet(c, code)
        for c, code in zip(pack["context"], pack["objective_code"])
    ]
    pack = pack.drop(columns=["context"])
    pack.insert(0, "review_id", range(1, len(pack) + 1))
    pack["is_real_code"] = ""
    pack["note"] = ""
    pack.to_csv(POLICY_DIR / "objective_code_verification_pack.csv", index=False)
    print(f"wrote {len(pack)} rows -> objective_code_verification_pack.csv")
    print("tail share (<=2 mentions):", int((pack["mentions"] <= 2).sum()), "/", len(pack))
    print("unknown periods in pack:", int((pack["plan_period"] == "unknown").sum()))


if __name__ == "__main__":
    main()
