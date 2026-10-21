#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _read_csv(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path)
    return pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-long", default="extraction_of_site_data/refusal_reasons_long.csv")
    parser.add_argument("--base-cases", default="extraction_of_site_data/refusal_reasons_cases.csv")
    parser.add_argument("--ocr-long", default="extraction_of_site_data/refusal_reasons_long_ocr_fill.csv")
    parser.add_argument("--ocr-cases", default="extraction_of_site_data/refusal_reasons_cases_ocr_fill.csv")
    parser.add_argument("--out-long", default="extraction_of_site_data/refusal_reasons_long_final.csv")
    parser.add_argument("--out-cases", default="extraction_of_site_data/refusal_reasons_cases_final.csv")
    parser.add_argument("--out-tag-counts", default="extraction_of_site_data/refusal_reason_tag_counts_final.csv")
    parser.add_argument("--source-wide", default="extraction_of_site_data/ground_source_extracted_final_wide.csv")
    parser.add_argument("--out-merged", default="extraction_of_site_data/ground_source_extracted_final_wide_with_refusal_reasons_final.csv")
    args = parser.parse_args()

    base_long = _read_csv(Path(args.base_long))
    ocr_long = _read_csv(Path(args.ocr_long))
    base_cases = _read_csv(Path(args.base_cases))
    ocr_cases = _read_csv(Path(args.ocr_cases))

    long_frames = [df for df in [base_long, ocr_long] if not df.empty]
    if long_frames:
        long_df = pd.concat(long_frames, ignore_index=True)
        dedupe_cols = [c for c in ["case_key", "reason_text"] if c in long_df.columns]
        if dedupe_cols:
            long_df = long_df.drop_duplicates(subset=dedupe_cols)
    else:
        long_df = pd.DataFrame()

    if not base_cases.empty or not ocr_cases.empty:
        for df in [base_cases, ocr_cases]:
            if not df.empty and "reason_count" not in df.columns:
                df["reason_count"] = 0
        base_cases = base_cases.copy() if not base_cases.empty else pd.DataFrame(columns=["case_key"])
        ocr_cases = ocr_cases.copy() if not ocr_cases.empty else pd.DataFrame(columns=["case_key"])
        if "case_key" not in base_cases.columns:
            base_cases["case_key"] = pd.NA
        if "case_key" not in ocr_cases.columns:
            ocr_cases["case_key"] = pd.NA
        base_cases["__source"] = "base"
        ocr_cases["__source"] = "ocr"
        case_df = pd.concat([base_cases, ocr_cases], ignore_index=True, sort=False)
        case_df["reason_count"] = pd.to_numeric(case_df.get("reason_count", 0), errors="coerce").fillna(0)
        case_df["__score"] = case_df["reason_count"] + (case_df["__source"] == "ocr").astype(int) * 0.001
        case_df = case_df.sort_values(["case_key", "__score"], ascending=[True, False]).drop_duplicates(subset=["case_key"], keep="first")
        case_df = case_df.drop(columns=["__source", "__score"], errors="ignore")
    else:
        case_df = pd.DataFrame()

    Path(args.out_long).parent.mkdir(parents=True, exist_ok=True)
    long_df.to_csv(args.out_long, index=False)
    case_df.to_csv(args.out_cases, index=False)

    if not long_df.empty and "primary_tag" in long_df.columns:
        tag_counts = long_df["primary_tag"].value_counts().reset_index()
        tag_counts.columns = ["tag", "count"]
    else:
        tag_counts = pd.DataFrame(columns=["tag", "count"])
    tag_counts.to_csv(args.out_tag_counts, index=False)

    source_wide = pd.read_csv(args.source_wide, low_memory=False)
    if not case_df.empty:
        case_merge = case_df[["case_key", "reason_count", "reasons_joined", "case_primary_tags", "case_top_primary_tag"]].copy()
    else:
        case_merge = pd.DataFrame(columns=["case_key", "reason_count", "reasons_joined", "case_primary_tags", "case_top_primary_tag"])

    council = source_wide["PlanningAuthority"].fillna("").astype(str).str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    app = source_wide["ApplicationNumber"].fillna("").astype(str).str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    source_wide["case_key"] = (council + "_" + app).str.lower()

    merged = source_wide.merge(case_merge, on="case_key", how="left")
    merged.to_csv(args.out_merged, index=False)

    print(f"Wrote: {args.out_long}")
    print(f"Wrote: {args.out_cases}")
    print(f"Wrote: {args.out_tag_counts}")
    print(f"Wrote: {args.out_merged}")


if __name__ == "__main__":
    main()
