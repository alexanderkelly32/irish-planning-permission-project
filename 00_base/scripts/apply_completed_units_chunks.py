#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _build_case_key(df: pd.DataFrame) -> pd.Series:
    council = df.get("PlanningAuthority", pd.Series("", index=df.index)).fillna("").astype(str)
    app = df.get("ApplicationNumber", pd.Series("", index=df.index)).fillna("").astype(str)
    council_clean = council.str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    app_clean = app.str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    return (council_clean + "_" + app_clean).str.lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="extraction_of_site_data/_qa/units_only_200k_chunk_manifest.csv",
    )
    parser.add_argument(
        "--input-wide",
        default="extraction_of_site_data/ground_source_extracted_final_wide_fixed.csv",
    )
    parser.add_argument(
        "--output-wide",
        default="extraction_of_site_data/ground_source_extracted_final_wide_fixed.csv",
    )
    parser.add_argument(
        "--apply-status",
        default="completed",
        help="Only use manifest rows with this status.",
    )
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    if "merged_csv" not in manifest.columns:
        print("Manifest has no merged_csv column; nothing to apply.")
        return

    completed = manifest[manifest["status"].astype(str).str.lower() == args.apply_status.lower()].copy()
    merged_files = [Path(p) for p in completed["merged_csv"].dropna().astype(str) if p and Path(p).exists()]
    if not merged_files:
        print("No completed merged chunk files found to apply.")
        return

    llm_rows = []
    for f in merged_files:
        part = pd.read_csv(f, low_memory=False)
        if "llm_units_total" not in part.columns:
            continue
        part = part[["PlanningAuthority", "ApplicationNumber", "llm_units_total"]].copy()
        part["llm_units_total"] = pd.to_numeric(part["llm_units_total"], errors="coerce")
        # Treat zero/negative as null for units.
        part.loc[part["llm_units_total"] <= 0, "llm_units_total"] = pd.NA
        part = part.dropna(subset=["llm_units_total"])
        if len(part):
            llm_rows.append(part)

    if not llm_rows:
        print("No non-null llm_units_total values found in completed chunks.")
        return

    llm_df = pd.concat(llm_rows, ignore_index=True)
    llm_df["case_key"] = _build_case_key(llm_df)
    llm_df = llm_df.drop_duplicates(subset=["case_key"], keep="last")

    wide = pd.read_csv(args.input_wide, low_memory=False)
    if "case_key" not in wide.columns:
        wide["case_key"] = _build_case_key(wide)

    wide["units_total_best"] = pd.to_numeric(wide.get("units_total_best"), errors="coerce")
    before_missing = int(wide["units_total_best"].isna().sum())

    merged = wide.merge(llm_df[["case_key", "llm_units_total"]], on="case_key", how="left")
    fill_mask = merged["units_total_best"].isna() & merged["llm_units_total"].notna()
    merged.loc[fill_mask, "units_total_best"] = merged.loc[fill_mask, "llm_units_total"]

    if "units_recovery_method" not in merged.columns:
        merged["units_recovery_method"] = pd.NA
    merged.loc[fill_mask, "units_recovery_method"] = "llm_units_only_batch"

    merged = merged.drop(columns=["llm_units_total"], errors="ignore")
    merged.to_csv(args.output_wide, index=False)

    after_missing = int(pd.to_numeric(merged["units_total_best"], errors="coerce").isna().sum())
    print(f"Applied completed chunk files: {len(merged_files)}")
    print(f"Filled units_total_best rows this run: {int(fill_mask.sum())}")
    print(f"units_total_best missing: {before_missing} -> {after_missing}")


if __name__ == "__main__":
    main()
