#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd


HOUSING_KW_RE = r"\b(?:unit|units|dwelling|dwellings|house|houses|apartment|apartments|residential)\b"
MULTI_KW_RE = r"\b(?:dwellings|apartments|units|serviced sites|residential development|housing development|scheme)\b"
SINGLE_ONLY_RE = r"\b(?:a|an|one|single)\s+(?:fully\s+serviced\s+)?(?:dwelling|dwelling house|house)\b"
LARGE_NUM_RE = (
    r"\b(?:[1-9]\d{1,3})\s*(?:no(?:s|'s)?\.?\s*|number\s+of\s*|number\s+)?"
    r"(?:new\s*)?(?:units?|dwellings?|houses?|apartments?)\b"
)


def _build_case_key(df: pd.DataFrame) -> pd.Series:
    council = df.get("PlanningAuthority", pd.Series("", index=df.index)).fillna("").astype(str)
    app = df.get("ApplicationNumber", pd.Series("", index=df.index)).fillna("").astype(str)
    council_clean = council.str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    app_clean = app.str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    return (council_clean + "_" + app_clean).str.lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="extraction_of_site_data/ground_source_extracted_final_wide_comprehensive_master.csv",
    )
    parser.add_argument(
        "--output-queue",
        default="extraction_of_site_data/_reports/units_recovery_queue.csv",
    )
    parser.add_argument(
        "--output-summary",
        default="extraction_of_site_data/_reports/units_recovery_summary_by_authority.csv",
    )
    parser.add_argument("--max-rows", type=int, default=50000)
    parser.add_argument("--max-per-authority", type=int, default=3000)
    args = parser.parse_args()

    df = pd.read_csv(args.input, low_memory=False)
    if "case_key" not in df.columns:
        df["case_key"] = _build_case_key(df)

    text = df.get("DevelopmentDescription", pd.Series("", index=df.index)).fillna("").astype(str)
    units_best = pd.to_numeric(df.get("units_total_best"), errors="coerce")
    num_res = pd.to_numeric(df.get("NumResidentialUnits"), errors="coerce")

    missing_units = units_best.isna()
    has_housing_kw = text.str.contains(HOUSING_KW_RE, case=False, regex=True)
    has_multi_kw = text.str.contains(MULTI_KW_RE, case=False, regex=True)
    looks_single_only = text.str.contains(SINGLE_ONLY_RE, case=False, regex=True)
    has_large_num_signal = text.str.contains(LARGE_NUM_RE, case=False, regex=True)

    needs_recovery = missing_units & has_housing_kw & (~looks_single_only | has_multi_kw | has_large_num_signal)
    likely_ge10_signal = (num_res >= 10) | has_large_num_signal | (
        text.str.contains(
            r"\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b",
            case=False,
            regex=True,
        )
        & has_multi_kw
    )

    queue = df.loc[needs_recovery].copy()
    queue["units_missing"] = True
    queue["has_housing_keywords"] = has_housing_kw[needs_recovery].values
    queue["has_multi_unit_keywords"] = has_multi_kw[needs_recovery].values
    queue["has_large_number_signal"] = has_large_num_signal[needs_recovery].values
    queue["likely_ge10_signal"] = likely_ge10_signal[needs_recovery].fillna(False).values
    queue["recommended_action"] = "llm_units_extract"
    queue.loc[queue["has_large_number_signal"], "recommended_action"] = "regex_retry_then_llm_if_missing"

    queue["priority_score"] = (
        queue["likely_ge10_signal"].astype(int) * 100
        + queue["has_large_number_signal"].astype(int) * 50
        + queue["has_multi_unit_keywords"].astype(int) * 20
    )

    authority_gap = queue.groupby("PlanningAuthority", dropna=False).size().rename("authority_gap_count")
    queue = queue.merge(authority_gap, on="PlanningAuthority", how="left")
    queue["priority_score"] = queue["priority_score"] + (queue["authority_gap_count"].fillna(0) / 200).astype(int)

    keep_cols = [
        "case_key",
        "PlanningAuthority",
        "ApplicationNumber",
        "Decision",
        "DecisionDate",
        "ReceivedDate",
        "units_total_best",
        "NumResidentialUnits",
        "units_total_effective",
        "likely_ge10_signal",
        "recommended_action",
        "priority_score",
        "authority_gap_count",
        "DevelopmentDescription",
    ]
    keep_cols = [c for c in keep_cols if c in queue.columns]
    queue = queue[keep_cols].sort_values(
        ["priority_score", "authority_gap_count", "PlanningAuthority"],
        ascending=[False, False, True],
    )
    if args.max_per_authority and args.max_per_authority > 0 and "PlanningAuthority" in queue.columns:
        queue = queue.groupby("PlanningAuthority", dropna=False, group_keys=False).head(args.max_per_authority)
        queue = queue.sort_values(
            ["priority_score", "authority_gap_count", "PlanningAuthority"],
            ascending=[False, False, True],
        )
    if args.max_rows and args.max_rows > 0:
        queue = queue.head(args.max_rows)

    summary = (
        queue.groupby("PlanningAuthority", dropna=False)
        .agg(
            queued_cases=("case_key", "size"),
            likely_ge10_cases=("likely_ge10_signal", "sum"),
            avg_priority=("priority_score", "mean"),
        )
        .reset_index()
        .sort_values(["queued_cases", "likely_ge10_cases"], ascending=False)
    )
    summary["generated_at"] = dt.datetime.now().isoformat(timespec="seconds")

    out_q = Path(args.output_queue)
    out_s = Path(args.output_summary)
    out_q.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(out_q, index=False)
    summary.to_csv(out_s, index=False)

    print(f"Wrote: {out_q}")
    print(f"Wrote: {out_s}")
    print(f"Queue rows: {len(queue)}")
    print(f"Likely GE10 in queue: {int(queue.get('likely_ge10_signal', pd.Series(dtype=bool)).sum())}")


if __name__ == "__main__":
    main()
