#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import shutil
from pathlib import Path
from typing import Iterable

import pandas as pd


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, low_memory=False)
    return pd.DataFrame()


def _build_case_key(df: pd.DataFrame) -> pd.Series:
    council = df.get("PlanningAuthority", pd.Series("", index=df.index)).fillna("").astype(str)
    app = df.get("ApplicationNumber", pd.Series("", index=df.index)).fillna("").astype(str)
    council_clean = council.str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    app_clean = app.str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    return (council_clean + "_" + app_clean).str.lower()


def _numeric_max(a: pd.Series, b: pd.Series) -> pd.Series:
    a_num = pd.to_numeric(a, errors="coerce")
    b_num = pd.to_numeric(b, errors="coerce")
    return pd.concat([a_num, b_num], axis=1).max(axis=1, skipna=True)


def _safe_merge_left(base: pd.DataFrame, right: pd.DataFrame, on: str, cols: Iterable[str]) -> pd.DataFrame:
    keep = [c for c in cols if c in right.columns]
    if not keep:
        return base
    right_use = right[[on] + keep].drop_duplicates(subset=[on], keep="last")
    overlap = [c for c in keep if c in base.columns]
    if overlap:
        renamed = {c: f"{c}__new" for c in overlap}
        right_use = right_use.rename(columns=renamed)
        out = base.merge(right_use, on=on, how="left")
        for c in overlap:
            c_new = f"{c}__new"
            out[c] = out[c].where(out[c].notna(), out[c_new])
            out = out.drop(columns=[c_new])
        return out
    return base.merge(right_use, on=on, how="left")


def _with_inclusion_reason(df: pd.DataFrame) -> pd.Series:
    reason = pd.Series("", index=df.index, dtype="string")
    reason = reason.mask(df["is_ge10_by_units_effective"], reason + "units_effective>=10;")
    reason = reason.mask(df["is_in_legacy_ge10_master"], reason + "legacy_ge10_master;")
    reason = reason.mask(df["is_in_legacy_ge10_fi"], reason + "legacy_ge10_fi_enriched;")
    return reason.str.rstrip(";")


def _coverage_report(df: pd.DataFrame, out_by_auth: Path, out_overall: Path, generated_at: str) -> None:
    fields = [
        "units_total_best",
        "NumResidentialUnits",
        "units_total_effective",
        "reason_count",
        "reasons_joined",
        "case_top_primary_tag",
        "LinkAppDetails",
        "fi_events_count",
        "fi_request_items_count",
        "DevelopmentDescription",
    ]
    fields = [f for f in fields if f in df.columns]

    group_col = "PlanningAuthority" if "PlanningAuthority" in df.columns else None
    if group_col:
        grouped = df.groupby(group_col, dropna=False)
    else:
        grouped = [("ALL", df)]

    by_auth_rows: list[dict[str, object]] = []
    for authority, part in grouped:
        row: dict[str, object] = {
            "generated_at": generated_at,
            "PlanningAuthority": authority,
            "row_count": int(len(part)),
            "ge10_comprehensive_count": int(part["is_ge10_comprehensive_candidate"].sum())
            if "is_ge10_comprehensive_candidate" in part.columns
            else 0,
        }
        row["ge10_comprehensive_pct"] = (
            round((row["ge10_comprehensive_count"] / row["row_count"]) * 100, 2) if row["row_count"] else 0.0
        )
        for f in fields:
            non_null = int(part[f].notna().sum())
            miss_pct = round((1 - (non_null / row["row_count"])) * 100, 2) if row["row_count"] else 0.0
            row[f"{f}_non_null"] = non_null
            row[f"{f}_missing_pct"] = miss_pct
        by_auth_rows.append(row)

    by_auth = pd.DataFrame(by_auth_rows).sort_values("row_count", ascending=False)
    out_by_auth.parent.mkdir(parents=True, exist_ok=True)
    by_auth.to_csv(out_by_auth, index=False)

    overall = {
        "generated_at": generated_at,
        "row_count": int(len(df)),
        "ge10_comprehensive_count": int(df["is_ge10_comprehensive_candidate"].sum())
        if "is_ge10_comprehensive_candidate" in df.columns
        else 0,
    }
    overall["ge10_comprehensive_pct"] = (
        round((overall["ge10_comprehensive_count"] / overall["row_count"]) * 100, 2) if overall["row_count"] else 0.0
    )
    for f in fields:
        non_null = int(df[f].notna().sum())
        miss_pct = round((1 - (non_null / overall["row_count"])) * 100, 2) if overall["row_count"] else 0.0
        overall[f"{f}_non_null"] = non_null
        overall[f"{f}_missing_pct"] = miss_pct
    pd.DataFrame([overall]).to_csv(out_overall, index=False)


def _write_delta_vs_latest(current_report: Path, latest_report: Path, out_delta: Path) -> bool:
    if not latest_report.exists() or latest_report.stat().st_size == 0:
        return False

    cur = pd.read_csv(current_report)
    prev = pd.read_csv(latest_report)
    if "PlanningAuthority" not in cur.columns or "PlanningAuthority" not in prev.columns:
        return False

    cur = cur.set_index("PlanningAuthority")
    prev = prev.set_index("PlanningAuthority")
    joined = cur.join(prev, how="outer", lsuffix="_new", rsuffix="_prev")
    delta = pd.DataFrame(index=joined.index)

    for col in [
        "row_count",
        "ge10_comprehensive_count",
        "units_total_best_missing_pct",
        "NumResidentialUnits_missing_pct",
        "units_total_effective_missing_pct",
        "reason_count_missing_pct",
        "LinkAppDetails_missing_pct",
    ]:
        c_new = f"{col}_new"
        c_prev = f"{col}_prev"
        if c_new in joined.columns and c_prev in joined.columns:
            delta[col] = joined[c_new].fillna(0) - joined[c_prev].fillna(0)

    if delta.empty:
        return False

    delta = delta.reset_index().rename(columns={"index": "PlanningAuthority"})
    out_delta.parent.mkdir(parents=True, exist_ok=True)
    delta.to_csv(out_delta, index=False)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wide-base",
        default="extraction_of_site_data/ground_source_extracted_final_wide_fixed.csv",
    )
    parser.add_argument(
        "--wide-refusal",
        default="extraction_of_site_data/ground_source_extracted_final_wide_with_refusal_reasons_llm.csv",
    )
    parser.add_argument(
        "--legacy-ge10-master",
        default="extraction_of_site_data/greater_than_10_units_with_refusal_reasons_master.csv",
    )
    parser.add_argument(
        "--legacy-ge10-fi",
        default="extraction_of_site_data/greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv",
    )
    parser.add_argument(
        "--out-master",
        default="extraction_of_site_data/ground_source_extracted_final_wide_comprehensive_master.csv",
    )
    parser.add_argument(
        "--out-ge10",
        default="extraction_of_site_data/greater_than_10_units_comprehensive_master.csv",
    )
    parser.add_argument(
        "--out-coverage-by-authority",
        default="extraction_of_site_data/_reports/comprehensive_coverage_by_authority.csv",
    )
    parser.add_argument(
        "--out-coverage-overall",
        default="extraction_of_site_data/_reports/comprehensive_coverage_overall.csv",
    )
    parser.add_argument(
        "--latest-coverage-by-authority",
        default="extraction_of_site_data/_reports/comprehensive_coverage_by_authority_latest.csv",
    )
    parser.add_argument(
        "--out-coverage-delta",
        default="extraction_of_site_data/_reports/comprehensive_coverage_delta_vs_latest.csv",
    )
    args = parser.parse_args()

    generated_at = dt.datetime.now().isoformat(timespec="seconds")

    base = _read_csv_if_exists(Path(args.wide_base))
    if base.empty:
        raise FileNotFoundError(f"Base wide file missing or empty: {args.wide_base}")

    base["case_key"] = _build_case_key(base)

    refusal = _read_csv_if_exists(Path(args.wide_refusal))
    if not refusal.empty:
        refusal["case_key"] = _build_case_key(refusal)
        refusal_cols = [
            "reason_count",
            "reasons_joined",
            "case_primary_tags",
            "case_top_primary_tag",
        ]
        base = _safe_merge_left(base, refusal, on="case_key", cols=refusal_cols)

    legacy_ge10 = _read_csv_if_exists(Path(args.legacy_ge10_master))
    if not legacy_ge10.empty:
        if "case_key" not in legacy_ge10.columns:
            legacy_ge10["case_key"] = _build_case_key(legacy_ge10)
        legacy_ge10_keys = set(legacy_ge10["case_key"].dropna().astype(str).str.lower())
    else:
        legacy_ge10_keys = set()

    legacy_fi = _read_csv_if_exists(Path(args.legacy_ge10_fi))
    if not legacy_fi.empty:
        if "case_key" not in legacy_fi.columns:
            legacy_fi["case_key"] = _build_case_key(legacy_fi)
        legacy_fi_keys = set(legacy_fi["case_key"].dropna().astype(str).str.lower())

        extra_cols = [
            c
            for c in legacy_fi.columns
            if c.startswith("fi_") and c not in {"case_key"}
        ]
        if extra_cols:
            base = _safe_merge_left(base, legacy_fi, on="case_key", cols=extra_cols)
    else:
        legacy_fi_keys = set()

    base["units_total_effective"] = _numeric_max(base.get("units_total_best"), base.get("NumResidentialUnits"))
    base["is_ge10_by_units_total_best"] = pd.to_numeric(base.get("units_total_best"), errors="coerce").ge(10).fillna(False)
    base["is_ge10_by_num_residential_units"] = (
        pd.to_numeric(base.get("NumResidentialUnits"), errors="coerce").ge(10).fillna(False)
    )
    base["is_ge10_by_units_effective"] = pd.to_numeric(base["units_total_effective"], errors="coerce").ge(10).fillna(False)
    base["is_in_legacy_ge10_master"] = base["case_key"].isin(legacy_ge10_keys)
    base["is_in_legacy_ge10_fi"] = base["case_key"].isin(legacy_fi_keys)
    base["is_ge10_comprehensive_candidate"] = (
        base["is_ge10_by_units_effective"] | base["is_in_legacy_ge10_master"] | base["is_in_legacy_ge10_fi"]
    )
    base["ge10_inclusion_reason"] = _with_inclusion_reason(base)

    out_master = Path(args.out_master)
    out_master.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(out_master, index=False)

    ge10 = base[base["is_ge10_comprehensive_candidate"]].copy()
    out_ge10 = Path(args.out_ge10)
    out_ge10.parent.mkdir(parents=True, exist_ok=True)
    ge10.to_csv(out_ge10, index=False)

    out_cov_auth = Path(args.out_coverage_by_authority)
    out_cov_overall = Path(args.out_coverage_overall)
    _coverage_report(base, out_cov_auth, out_cov_overall, generated_at)

    latest_cov = Path(args.latest_coverage_by_authority)
    out_delta = Path(args.out_coverage_delta)
    wrote_delta = _write_delta_vs_latest(out_cov_auth, latest_cov, out_delta)

    # Keep both current report and a "latest" snapshot for next-run deltas.
    shutil.copyfile(out_cov_auth, latest_cov)

    print(f"Wrote: {out_master}")
    print(f"Wrote: {out_ge10}")
    print(f"Wrote: {out_cov_auth}")
    print(f"Wrote: {out_cov_overall}")
    if wrote_delta:
        print(f"Wrote: {out_delta}")
    print(f"Comprehensive GE10 candidates: {int(ge10.shape[0])}")


if __name__ == "__main__":
    main()
