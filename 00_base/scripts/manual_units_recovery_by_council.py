#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd


TARGET_AUTHORITIES = {
    "Cork County Council",
    "Dublin City Council",
    "Dun Laoghaire Rathdown County Council",
    "Fingal County Council",
    "South Dublin County Council",
    "Wexford County Council",
}

CORK_SINGLE_UNIT_TEMPLATE_WHITELIST = {
    "dwelling",
    "dwelling and garage",
    "dwelling house",
    "to construct a new dwelling house.",
    "permission to construct a new dwelling house.",
    "permission to construct a new dwelling house",
    "to construct a new dwelling house",
    "dwelling and domestic garage",
    "dwelling domestic garage and associated site works",
    "dwelling domestic garage",
    "dwelling and associated site works",
    "single storey dwelling",
    "dwellinghouse and treatment unit",
    "dwellinghouse and waste water treatment unit",
    "dwellinghouse and installation of treatment unit",
    "dwelling and septic tank",
    "dwelling and detached garage",
    "construction of dwelling house and all associated site works",
    "demolition of dwelling and construction of dwelling",
    "demolition of dwelling and construction of dwellinghouse",
}


def _build_case_key(df: pd.DataFrame) -> pd.Series:
    council = df.get("PlanningAuthority", pd.Series("", index=df.index)).fillna("").astype(str)
    app = df.get("ApplicationNumber", pd.Series("", index=df.index)).fillna("").astype(str)
    council_clean = council.str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    app_clean = app.str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    return (council_clean + "_" + app_clean).str.lower()


def _normalize_template(text: pd.Series) -> pd.Series:
    return (
        text.fillna("")
        .astype(str)
        .str.lower()
        .str.replace(r"\d+", "<n>", regex=True)
        .str.replace(r"[^a-z0-9<>\s/.-]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.slice(0, 180)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="extraction_of_site_data/ground_source_extracted_final_wide_fixed.csv",
    )
    parser.add_argument(
        "--output",
        default="extraction_of_site_data/ground_source_extracted_final_wide_fixed.csv",
    )
    parser.add_argument(
        "--report-by-council",
        default="extraction_of_site_data/_reports/units_manual_recovery_by_council.csv",
    )
    parser.add_argument(
        "--report-cases",
        default="extraction_of_site_data/_reports/units_manual_recovery_cases.csv",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.input, low_memory=False)
    if "case_key" not in df.columns:
        df["case_key"] = _build_case_key(df)

    text = df.get("DevelopmentDescription", pd.Series("", index=df.index)).fillna("").astype(str)
    text_l = text.str.lower()
    missing_units = pd.to_numeric(df.get("units_total_best"), errors="coerce").isna()
    target_auth = df.get("PlanningAuthority", pd.Series("", index=df.index)).isin(TARGET_AUTHORITIES)

    housing_kw = text_l.str.contains(
        r"\b(?:dwelling|dwellings|house|houses|apartment|apartments|unit|units|mews house|mews houses)\b",
        regex=True,
    )
    no_explicit_digits = ~text_l.str.contains(r"\d")

    exclusion_heavy_modification = text_l.str.contains(
        r"\b(?:retention|extension|alteration|change of use|attic conversion|dormer|rooflight|window|porch|renovation|refurbishment)\b",
        regex=True,
    )

    # Rule 1: obvious single new dwelling style applications.
    rule_single_new_dwelling = (
        missing_units
        & target_auth
        & housing_kw
        & no_explicit_digits
        & text_l.str.contains(
            r"\b(?:construct|construction|erect|erection|proposed|provision of|permission for)\b",
            regex=True,
        )
        & text_l.str.contains(
            r"\b(?:a|an|one|single)\b(?:[\w\-/]+\b\s+){0,6}\b(?:dwelling|dwelling house|house|mews house)\b",
            regex=True,
        )
        & ~exclusion_heavy_modification
    )

    # Rule 2: demolition/replacement with one dwelling.
    rule_demo_replace_single = (
        missing_units
        & target_auth
        & housing_kw
        & text_l.str.contains(r"\b(?:demolish|demolition|replace|replacement)\b", regex=True)
        & text_l.str.contains(
            r"\b(?:a|an|one|single)\b(?:[\w\-/]+\b\s+){0,6}\b(?:dwelling|dwelling house|house|mews house)\b",
            regex=True,
        )
    )

    # Cork-specific high-confidence short-template one-unit cases.
    normalized = _normalize_template(text)
    rule_cork_short_single_templates = (
        missing_units
        & (df.get("PlanningAuthority", pd.Series("", index=df.index)) == "Cork County Council")
        & normalized.isin(CORK_SINGLE_UNIT_TEMPLATE_WHITELIST)
    )

    fill_mask = rule_single_new_dwelling | rule_demo_replace_single | rule_cork_short_single_templates
    fill_rule = pd.Series("", index=df.index, dtype="string")
    fill_rule = fill_rule.mask(rule_single_new_dwelling, "single_new_dwelling_text_rule")
    fill_rule = fill_rule.mask(rule_demo_replace_single, "demolition_replace_single_dwelling_text_rule")
    fill_rule = fill_rule.mask(rule_cork_short_single_templates, "cork_short_single_template_text_rule")

    df.loc[fill_mask, "units_total_best"] = 1

    # Keep an explicit provenance field for this recovery pass.
    if "units_recovery_method" not in df.columns:
        df["units_recovery_method"] = pd.NA
    df.loc[fill_mask, "units_recovery_method"] = fill_rule[fill_mask]

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    recovered_cases = df.loc[fill_mask, ["case_key", "PlanningAuthority", "ApplicationNumber", "DevelopmentDescription"]].copy()
    recovered_cases["units_manual_fill"] = 1
    recovered_cases["units_recovery_method"] = fill_rule[fill_mask].values

    report_cases = Path(args.report_cases)
    report_cases.parent.mkdir(parents=True, exist_ok=True)
    recovered_cases.to_csv(report_cases, index=False)

    by_council = (
        recovered_cases.groupby("PlanningAuthority", dropna=False)
        .agg(recovered_cases=("case_key", "size"))
        .reset_index()
        .sort_values("recovered_cases", ascending=False)
    )
    by_rule = (
        recovered_cases.groupby("units_recovery_method", dropna=False)
        .agg(recovered_cases=("case_key", "size"))
        .reset_index()
        .sort_values("recovered_cases", ascending=False)
    )
    by_council["generated_at"] = dt.datetime.now().isoformat(timespec="seconds")

    report_council = Path(args.report_by_council)
    by_council.to_csv(report_council, index=False)

    report_rule = report_council.with_name("units_manual_recovery_by_rule.csv")
    by_rule.to_csv(report_rule, index=False)

    print(f"Wrote: {out}")
    print(f"Wrote: {report_cases}")
    print(f"Wrote: {report_council}")
    print(f"Wrote: {report_rule}")
    print(f"Recovered units_total_best rows: {int(fill_mask.sum())}")


if __name__ == "__main__":
    main()
