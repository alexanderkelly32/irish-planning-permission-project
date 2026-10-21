#!/usr/bin/env python3
"""Build the refusal-theme tagging verification pack (bottleneck-quality measurement)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REFUSAL_MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
OUT_DIR = ROOT / "02_development" / "current" / "theme_tagging_verification_2026-09-09"

THEMES = [
    "density_scale", "design_layout", "traffic_access", "residential_amenity",
    "flooding_drainage", "land_use_policy", "premature_or_info_gap",
    "heritage_archaeology", "ecology_trees", "water_wastewater", "other",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=100)
    args = parser.parse_args()

    master = pd.read_csv(REFUSAL_MASTER, low_memory=False)
    tagged = master[
        master["case_primary_tags"].fillna("").astype(str).str.strip().ne("")
        & master["reasons_joined"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    tagged["_top"] = tagged["case_top_primary_tag"].fillna("").astype(str)
    tagged["_order"] = [
        hashlib.sha256(f"20260909|{key}".encode("utf-8")).hexdigest()
        for key in tagged["case_key"].astype(str)
    ]
    sample_rows = []
    per_theme_quota = max(1, args.sample // len(THEMES))
    for theme in THEMES:
        group = tagged[tagged["_top"] == theme].sort_values("_order")
        sample_rows.append(group.head(per_theme_quota))
    sample = pd.concat(sample_rows, ignore_index=True)
    sample = sample.sort_values("_order").head(args.sample)

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
            "verified_tags": "",
            "verified_top_tag": "",
            "verified_by": "",
            "verified_at": "",
            "verify_notes": "",
        })
    frame = pd.DataFrame(rows)
    frame["verify_id"] = [f"T{index + 1:03d}" for index in range(len(frame))]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT_DIR / "verify_rows.csv", index=False)
    summary = {
        "rows": int(len(frame)),
        "tagged_cases_available": int(len(tagged)),
        "themes": THEMES,
        "note": "Sample is stratified across the 11 themes; the verifier checks each extraction against the decision text.",
    }
    (OUT_DIR / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
