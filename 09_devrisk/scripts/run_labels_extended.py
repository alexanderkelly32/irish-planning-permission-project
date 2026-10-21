"""Runner: extended pain/exit labels for the full mature granted-GE10 cohort.

Uses the all-granted cohort (grant-date fallback included), mature window
grant 2016-2022, and the all-granted BCMS/PPR links. Overwrites
pain_labels_pool.csv / exit_labels_pool.csv with the extended superset
(previous pool: 1,095; extended mature: ~1,384).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.labels.economics import benchmark_prices, build_exit_labels  # noqa: E402
from devrisk.labels.pain import build_components, component_prevalence  # noqa: E402

CENSOR = "2026-09-27"

if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    mature = mature.drop_duplicates("case_key")
    print(f"extended mature cohort: {len(mature)}", flush=True)

    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms_links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    bcms_overlay_path = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if bcms_overlay_path.exists():
        overlay = pd.read_csv(bcms_overlay_path)
        if len(overlay):
            bcms_links = pd.concat(
                [bcms_links, overlay.reindex(columns=bcms_links.columns).dropna(subset=["scheme_id", "bcms_event_id"])],
                ignore_index=True,
            ).drop_duplicates(subset=["scheme_id", "bcms_event_id"])
    bcms_links = bcms_links[bcms_links["confidence_band"] == "confirmed"]
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr_links = pd.read_csv(settings.SILVER_DIR / "ppr_links_all_granted.csv")

    # Human-verified sales (workbook pulls) + auto BCMS-estate pulls + spatial
    # geocoded matches join the confirmed link set.
    for verified_path, method in (
        (settings.SILVER_DIR / "scheme_sales_verified.csv", "human_estate_name"),
        (settings.SILVER_DIR / "scheme_sales_auto.csv", "auto_bcms_estate"),
        (settings.SILVER_DIR / "scheme_sales_spatial.csv", "spatial_geocode"),
    ):
        if verified_path.exists():
            verified = pd.read_csv(verified_path)
            if "not_full_market_price" in verified.columns:
                verified = verified[~verified["not_full_market_price"].astype(bool)]
            verified_links = verified[["scheme_id", "ppr_source_row_id"]].copy()
            verified_links["confidence_band"] = "confirmed"
            verified_links["match_method"] = method
            verified_links["reasons"] = f"{method} sales pull"
            ppr_links = pd.concat(
                [ppr_links, verified_links.reindex(columns=ppr_links.columns).dropna(subset=["scheme_id"])],
                ignore_index=True,
            ).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])

    # Exit labels for the extended cohort.
    linked_events = bcms_links.merge(
        bcms[["bcms_event_id", "commencement_date_dt", "approved_housing_body"]],
        on="bcms_event_id", how="inner",
    )
    first_commencement = {}
    ahb_flags = {}
    for scheme_id, group in linked_events.groupby("scheme_id"):
        dates = pd.to_datetime(group["commencement_date_dt"], utc=True, errors="coerce").dropna()
        if not dates.empty:
            first_commencement[str(scheme_id)] = dates.min()
        values = group["approved_housing_body"].dropna().astype(str).str.lower()
        ahb_flags[str(scheme_id)] = "yes" if values.isin({"yes", "y", "true"}).any() else ""

    schemes = mature[["case_key", "grant_date_dt", "NumResidentialUnits", "DevelopmentDescription"]].rename(
        columns={"grant_date_dt": "final_grant_date", "NumResidentialUnits": "expected_units"}
    ).copy()
    schemes["case_key"] = schemes["case_key"].astype(str)
    schemes["commencement_date"] = schemes["case_key"].map(first_commencement)
    schemes["approved_housing_body"] = schemes["case_key"].map(ahb_flags)

    exit_labels = build_exit_labels(schemes, ppr_links, ppr, censor_date=CENSOR)
    benchmarks = benchmark_prices(exit_labels, ppr)
    exit_labels = exit_labels.merge(benchmarks, on="scheme_id", how="left")
    exit_labels.to_csv(settings.SILVER_DIR / "exit_labels_pool.csv", index=False)

    labels = build_components(
        mature, bcms, bcms_links, censor_date=CENSOR,
        exit_labels=exit_labels, rule_version="pain_v2",
    )
    labels.to_csv(settings.SILVER_DIR / "pain_labels_pool.csv", index=False)

    mature_keys = set(mature["case_key"].astype(str))
    confirmed_mature = len(set(bcms_links["scheme_id"]) & mature_keys)
    summary = component_prevalence(labels)
    summary["cohort_rows"] = int(len(mature))
    summary["previous_pool"] = 1095
    summary["bcms_confirmed_schemes_total"] = int(bcms_links["scheme_id"].nunique())
    summary["bcms_confirmed_schemes_mature"] = confirmed_mature
    summary["bcms_linkage_pct_mature"] = round(confirmed_mature / len(mature) * 100, 1)
    summary["sales_linked_schemes"] = int((exit_labels["sales_linked"] > 0).sum())
    summary["label_rule_version"] = "pain_v2"
    summary["censor_date"] = CENSOR
    out = settings.SILVER_DIR / "pain_labels_pool_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
