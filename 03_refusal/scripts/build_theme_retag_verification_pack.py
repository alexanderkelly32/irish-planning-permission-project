#!/usr/bin/env python3
"""Build the refusal-theme RETAG verification pack for the weak themes.

The pack verifies the stricter retag output against decision texts so the
bottleneck-quality improvement can be measured before the retag is promoted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RETAG_MASTER = ROOT / "03_refusal" / "current" / "theme_retag_2026-09-10" / "refusal_reasons_cases_master_retagged.csv"
REFUSAL_MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
OUT_DIR = ROOT / "02_development" / "current" / "theme_retag_verification_2026-09-10"

WEAK_THEMES = ["heritage_archaeology", "land_use_policy", "other"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=100)
    args = parser.parse_args()

    if RETAG_MASTER.exists():
        master = pd.read_csv(RETAG_MASTER, low_memory=False)
    else:
        master = pd.read_csv(REFUSAL_MASTER, low_memory=False)

    retagged = master[
        master["tag_extraction_model"].fillna("").astype(str).eq("deepseek-v4-pro-retag")
        & master["reasons_joined"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    retagged["_top"] = retagged["case_top_primary_tag"].fillna("").astype(str)
    retagged["_order"] = [
        hashlib.sha256(f"20260910|{key}".encode("utf-8")).hexdigest()
        for key in retagged["case_key"].astype(str)
    ]
    sample_rows = []
    per_theme_quota = max(1, args.sample // len(WEAK_THEMES))
    for theme in WEAK_THEMES:
        group = retagged[retagged["_top"] == theme].sort_values("_order")
        sample_rows.append(group.head(per_theme_quota))
    top_theme_sample = pd.concat(sample_rows, ignore_index=True)
    remaining = args.sample - len(top_theme_sample)
    if remaining > 0:
        already = set(top_theme_sample["case_key"])
        fill = retagged[~retagged["case_key"].isin(already)].sort_values("_order").head(remaining)
        top_theme_sample = pd.concat([top_theme_sample, fill], ignore_index=True)
    sample = top_theme_sample.sort_values("_order").head(args.sample)

    rows = []
    for _, row in sample.iterrows():
        rows.append({
            "verify_id": "",
            "case_key": str(row.get("case_key")),
            "council": str(row.get("council") or ""),
            "application_number": str(row.get("application_number") or ""),
            "decision_text": str(row.get("reasons_joined") or "")[:8000],
            "extracted_tags": str(row.get("case_primary_tags") or ""),
            "extracted_top_tag": str(row.get("case_top_primary_tag") or ""),
            "extracted_evidence": str(row.get("tag_evidence") or ""),
            "verified_tags": "",
            "verified_top_tag": "",
            "verified_by": "",
            "verified_at": "",
            "verify_notes": "",
        })
    frame = pd.DataFrame(rows)
    frame["verify_id"] = [f"R{index + 1:03d}" for index in range(len(frame))]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT_DIR / "verify_rows.csv", index=False)
    summary = {
        "rows": int(len(frame)),
        "retagged_cases_available": int(len(retagged)),
        "weak_themes": WEAK_THEMES,
        "note": (
            "Sample is stratified across the three retagged weak themes. The verifier "
            "checks each retag against the decision text; extracted_evidence contains "
            "the verbatim quotes the stricter prompt required."
        ),
    }
    (OUT_DIR / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
