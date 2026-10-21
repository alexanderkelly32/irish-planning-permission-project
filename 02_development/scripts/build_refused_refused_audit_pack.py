#!/usr/bin/env python3
"""Package the refused->refused audit sample for the user."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "refused_refused_audit_2026-09-09"


def main() -> None:
    sample = pd.read_csv(CURRENT / "refused_refused_manual_review_sample.csv", low_memory=False)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for column in ("manual_review_status", "manual_review_notes", "reviewer", "reviewed_at"):
        sample[column] = ""
    sample.to_csv(OUT_DIR / "review_rows.csv", index=False)
    summary = {
        "rows": int(len(sample)),
        "by_tier": sample["linkage_tier"].value_counts().to_dict(),
        "note": (
            "These are candidate pairs where an earlier refused application is followed by a "
            "LATER REFUSAL at the same address/site - the counterfactual arm. Auditing them "
            "tells us how often resubmissions failed again and what changed between refusals."
        ),
    }
    (OUT_DIR / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
