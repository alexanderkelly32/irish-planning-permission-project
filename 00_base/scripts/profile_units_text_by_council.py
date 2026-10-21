#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


TARGET_AUTHORITIES = [
    "Cork County Council",
    "Dublin City Council",
    "Dun Laoghaire Rathdown County Council",
    "Fingal County Council",
    "South Dublin County Council",
    "Wexford County Council",
]


def _normalize_template(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\d+", "<n>", t)
    t = re.sub(r"[^a-z0-9<>\s/.-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 180:
        t = t[:180]
    return t


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="extraction_of_site_data/ground_source_extracted_final_wide_comprehensive_master.csv",
    )
    parser.add_argument(
        "--output",
        default="extraction_of_site_data/_reports/units_council_structure_profile.csv",
    )
    parser.add_argument("--top-n", type=int, default=40)
    args = parser.parse_args()

    df = pd.read_csv(args.input, low_memory=False)
    text = df.get("DevelopmentDescription", pd.Series("", index=df.index)).fillna("").astype(str)
    missing_units = pd.to_numeric(df.get("units_total_best"), errors="coerce").isna()
    has_housing_kw = text.str.contains(
        r"\b(?:unit|units|dwelling|dwellings|house|houses|apartment|apartments|residential)\b",
        case=False,
        regex=True,
    )
    base = df[missing_units & has_housing_kw].copy()
    base["DevelopmentDescription"] = text[missing_units & has_housing_kw].values
    base = base[base["PlanningAuthority"].isin(TARGET_AUTHORITIES)].copy()
    base["text_template"] = base["DevelopmentDescription"].map(_normalize_template)

    grouped = (
        base.groupby(["PlanningAuthority", "text_template"], dropna=False)
        .agg(
            case_count=("ApplicationNumber", "size"),
            sample_description=("DevelopmentDescription", "first"),
        )
        .reset_index()
    )
    grouped = grouped.sort_values(["PlanningAuthority", "case_count"], ascending=[True, False])
    out = grouped.groupby("PlanningAuthority", group_keys=False).head(args.top_n)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    print(f"Wrote: {out_path}")
    print(f"Rows: {len(out)}")


if __name__ == "__main__":
    main()
