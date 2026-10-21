#!/usr/bin/env python3
"""Refusal themes by lever band: quantifies which themes dominate each band."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from structured_optimiser import build_cohort

OUTPUT_DIR = ROOT / "05_policy" / "current"


def main() -> None:
    cohort = build_cohort(pd.read_csv(
        ROOT / "02_development" / "current" / "height_storeys_extraction_2026-09-04" / "ground_source_storeys_verified.csv",
        low_memory=False,
    ))
    themes = pd.read_csv(ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv", low_memory=False)
    themes["_key"] = themes["case_key"].astype(str).str.lower()
    cohort["_key"] = cohort["case_key"].astype(str).str.lower()
    joined = cohort.merge(
        themes[["_key", "case_primary_tags", "case_top_primary_tag"]],
        on="_key", how="left",
    )
    refused = joined[joined["target_refused"] == 1]
    storey_bands = [(1, 1, "1"), (2, 2, "2"), (3, 3, "3"), (4, 4, "4"), (5, 100, "5+")]
    rows = []
    for low, high, label in storey_bands:
        band = joined[(joined["storeys"] >= low) & (joined["storeys"] <= high)]
        band_refused = band[band["target_refused"] == 1]
        tags = band_refused["case_primary_tags"].fillna("").astype(str)
        tagged = tags[tags.str.strip().ne("")]
        theme_counts: dict[str, int] = {}
        for row_tags in tagged:
            for tag in str(row_tags).split(";"):
                tag = tag.strip()
                if tag:
                    theme_counts[tag] = theme_counts.get(tag, 0) + 1
        rows.append({
            "storey_band": label,
            "cases": int(len(band)),
            "refused": int(len(band_refused)),
            "refusal_rate": round(float(band["target_refused"].mean()), 4),
            "refused_with_themes": int(len(tagged)),
            "top_themes": dict(sorted(theme_counts.items(), key=lambda item: -item[1])[:5]),
        })
    payload = {
        "cohort_rows": int(len(cohort)),
        "by_storey_band": rows,
        "caveat": (
            "Theme prevalence is computed on the subset of refused cases whose decision "
            "documents were OCR'd and tagged (1,159 nationally); bands without tags are "
            "under-reported, so treat theme shares as directional."
        ),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"refusal_themes_by_lever_band_{date.today().isoformat()}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
