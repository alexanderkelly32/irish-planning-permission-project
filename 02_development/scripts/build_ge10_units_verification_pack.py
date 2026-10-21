#!/usr/bin/env python3
"""Build the GE10 units verification pack.

Targets the extraction-only rows (null register units) in the ground-source
data, weighted toward the authorities the smoke test flagged (South Dublin
first, then Cork/Fingal). The smoke-test disagreement rows are included
explicitly. The ground-source CSV is read-only.
"""
from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
SOURCE = CURRENT / "height_storeys_extraction_2026-09-04" / "ground_source_storeys_verified.csv"

INSTRUCTIONS = """# WHAT TO DO — GE10 unit-count verification

## Why this batch matters

The unit counts in this file were LLM-extracted from application descriptions
because the register has no unit numbers for these authorities (Dun Laoghaire,
Dublin City, South Dublin, Fingal, Cork County). A smoke re-extraction agreed
with the stored values ~81% of the time but flagged South Dublin badly
(20% agreement), so these numbers need a human check before they feed the
unit-band AUC analysis.

## How to review

For each row:

1. Read the description text.
2. Work out the TOTAL number of residential units the application proposes
   (sum of houses/apartments/duplexes/dwellings explicitly stated).
3. Enter it in `verified_units` (a number, or leave blank if the description
   does not state a total).
4. `verified_by` / `verified_at`: your name and date.
5. `verify_notes`: anything useful (e.g. "description states 40 apartments +
   2 houses").

## Save

Save as `verify_rows_fixed.csv` in this folder. Do not edit the original.

## What happens next

I score precision per authority, correct nothing automatically, and decide
whether the affected authorities need a fresh extraction pass.
"""


def main() -> None:
    today = date.today().isoformat()
    out_dir = CURRENT / f"ge10_units_verification_{today}"
    out_dir.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(SOURCE, low_memory=False)
    register = pd.to_numeric(source["NumResidentialUnits"], errors="coerce")
    extracted = pd.to_numeric(source["units_total_best"], errors="coerce")
    pool = source[register.isna() & extracted.notna()].copy()

    flagged_keys = {
        "cork_county_council_164961",
        "south_dublin_county_council_sd058_0004",
        "south_dublin_county_council_sd05a_0870",
        "south_dublin_county_council_sd03a_0601",
        "south_dublin_county_council_lrd24a_0008",
        "fingal_county_council_f17a_0666_",
    }
    flagged = pool[pool["case_key"].isin(flagged_keys)].copy()

    quotas = [
        ("South Dublin County Council", 25),
        ("Cork County Council", 20),
        ("Fingal County Council", 15),
        ("Dun Laoghaire Rathdown County Council", 10),
        ("Dublin City Council", 10),
    ]
    parts = [flagged]
    for authority, quota in quotas:
        group = pool[(pool["PlanningAuthority"] == authority) & (~pool["case_key"].isin(flagged_keys))]
        parts.append(group.sample(n=min(quota, len(group)), random_state=20260919))
    others = pool[~pool["PlanningAuthority"].isin([a for a, _ in quotas])]
    parts.append(others.sample(n=min(15, len(others)), random_state=20260919))
    sample = pd.concat(parts, ignore_index=True).drop_duplicates("case_key")

    rows = []
    for _, row in sample.iterrows():
        rows.append({
            "verify_id": "",
            "case_key": str(row.get("case_key")),
            "authority": str(row.get("PlanningAuthority")),
            "application_number": str(row.get("ApplicationNumber") or ""),
            "description": str(row.get("DevelopmentDescription") or "")[:4000],
            "extracted_units": float(row["units_total_best"]) if pd.notna(row.get("units_total_best")) else None,
            "verified_units": "",
            "verified_by": "",
            "verified_at": "",
            "verify_notes": "",
        })
    frame = pd.DataFrame(rows)
    frame["verify_id"] = [f"U{i + 1:03d}" for i in range(len(frame))]
    frame.to_csv(out_dir / "verify_rows.csv", index=False)
    (out_dir / "INSTRUCTIONS.md").write_text(INSTRUCTIONS, encoding="utf-8")
    summary = {
        "rows": int(len(frame)),
        "by_authority": frame["authority"].value_counts().to_dict(),
        "flagged_disagreements_included": int(frame["case_key"].isin(flagged_keys).sum()),
        "note": "Save as verify_rows_fixed.csv in this folder.",
    }
    (out_dir / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
