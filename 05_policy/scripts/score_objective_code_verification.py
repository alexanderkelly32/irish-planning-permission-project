#!/usr/bin/env python3
"""Score the objective-code verification pack once is_real_code is filled in.

Usage: python 05_policy/scripts/score_objective_code_verification.py
Reads 05_policy/current/objective_code_verification_pack.csv, computes
precision overall and by tail/head split, writes the result summary.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = ROOT / "05_policy" / "current"


def main() -> None:
    pack_path = POLICY_DIR / "objective_code_verification_pack.csv"
    pack = pd.read_csv(pack_path)
    reviewed = pack[pack["is_real_code"].astype(str).str.lower().isin({"yes", "y", "1", "true", "no", "n", "0", "false"})].copy()
    if reviewed.empty:
        print("no reviews yet - fill the is_real_code column (yes/no) and re-run")
        return
    reviewed["is_real"] = reviewed["is_real_code"].astype(str).str.lower().isin({"yes", "y", "1", "true"})
    precision = float(reviewed["is_real"].mean())
    tail = reviewed[reviewed["mentions"] <= 2]
    head = reviewed[reviewed["mentions"] > 2]
    unknown_period = reviewed[reviewed["plan_period"] == "unknown"]
    result = {
        "reviewed": int(len(reviewed)),
        "precision": precision,
        "true_positives": int(reviewed["is_real"].sum()),
        "tail_precision": float(tail["is_real"].mean()) if len(tail) else None,
        "head_precision": float(head["is_real"].mean()) if len(head) else None,
        "unknown_period_reviewed": int(len(unknown_period)),
        "unknown_period_precision": float(unknown_period["is_real"].mean()) if len(unknown_period) else None,
        "false_samples": reviewed.loc[~reviewed["is_real"], ["review_id", "council", "plan_period", "objective_code", "context_snippet"]].to_dict("records"),
    }
    (POLICY_DIR / "objective_code_verification_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
