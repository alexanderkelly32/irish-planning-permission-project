"""Runner: rebuild exit + pain label pools from CURRENT link sets (v2).

Exit labels: scheme_sales_verified.csv (830 schemes incl. this week's
BCMS-notice-name matches) -> build_exit_labels. Pain labels: ALL confirmed
BCMS links (all_granted + verdict overlay + conservative pool) ->
build_components. Same censor date and rule version (pain_v2). Overwrites
exit_labels_pool.csv / pain_labels_pool.csv; the timing model scripts then
pick up ~2.2x the sale-link coverage and 83.8% BCMS linkage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.labels.economics import benchmark_prices, build_exit_labels  # noqa: E402
from devrisk.labels.pain import build_components, component_prevalence  # noqa: E402

CENSOR_DATE = "2026-09-27"


def load_confirmed_bcms_links() -> pd.DataFrame:
    frames = []
    for path in ("bcms_links_all_granted.csv", "bcms_links_conservative_pool.csv"):
        p = settings.SILVER_DIR / path
        if p.exists():
            frames.append(pd.read_csv(p))
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        overlay_frame = pd.read_csv(overlay)
        base_cols = [c for c in frames[0].columns if c != "confidence_band"]
        if "verdict" in overlay_frame.columns:
            overlay_frame = overlay_frame.rename(columns={"verdict": "confidence_band"})
        if "bcms_event_id" not in overlay_frame.columns and "candidate_event_id" in overlay_frame.columns:
            overlay_frame = overlay_frame.rename(columns={"candidate_event_id": "bcms_event_id"})
        overlay_frame = overlay_frame[["scheme_id", "bcms_event_id", "confidence_band"]]
        frames.append(overlay_frame)
    links = pd.concat(frames, ignore_index=True)
    links["scheme_id"] = links["scheme_id"].astype(str)
    links["bcms_event_id"] = links["bcms_event_id"].astype(str)
    return links[links["confidence_band"] == "confirmed"].drop_duplicates(subset=["scheme_id", "bcms_event_id"])


if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    pool = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_pool.parquet")
    cohort = register[register["case_key"].isin(pool["case_key"])].drop_duplicates("case_key").copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms["bcms_event_id"] = bcms["bcms_event_id"].astype(str)

    links = load_confirmed_bcms_links()
    print(f"confirmed BCMS links: {len(links)} rows, {links['scheme_id'].nunique()} schemes", flush=True)

    linked_events = links.merge(
        bcms[["bcms_event_id", "commencement_date_dt", "approved_housing_body"]],
        on="bcms_event_id", how="inner",
    )
    first_commencement = {}
    ahb_flags = {}
    for scheme_id, group in linked_events.groupby("scheme_id"):
        dates = pd.to_datetime(group["commencement_date_dt"], utc=True, errors="coerce").dropna()
        if not dates.empty:
            first_commencement[str(scheme_id)] = dates.min()
        ahb_values = group["approved_housing_body"].dropna().astype(str).str.lower()
        ahb_flags[str(scheme_id)] = "yes" if ahb_values.isin({"yes", "y", "true"}).any() else ""

    sales = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv")
    sales["scheme_id"] = sales["scheme_id"].astype(str)
    sales["ppr_source_row_id"] = sales["ppr_source_row_id"].astype(str)
    # Label hygiene: only VERIFIED rows feed labels; pending/promoted-band
    # rows are candidate pulls awaiting human verdicts.
    if "verification_status" in sales.columns:
        sales = sales[~sales["verification_status"].fillna("verified_prior").eq("pending")]
    pool_keys = set(cohort["case_key"].astype(str))
    sales = sales[sales["scheme_id"].isin(pool_keys)].copy()
    ppr_links = sales[["scheme_id", "ppr_source_row_id"]].assign(confidence_band="confirmed")
    print(f"verified sales rows in pool: {len(ppr_links)} ({sales['scheme_id'].nunique()} schemes)", flush=True)

    schemes = cohort[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription"]].rename(
        columns={"GrantDate": "final_grant_date", "NumResidentialUnits": "expected_units"}
    ).copy()
    schemes["case_key"] = schemes["case_key"].astype(str)
    schemes["commencement_date"] = schemes["case_key"].map(first_commencement)
    schemes["approved_housing_body"] = schemes["case_key"].map(ahb_flags)

    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr["source_row_id"] = ppr["source_row_id"].astype(str)

    exit_labels = build_exit_labels(schemes, ppr_links, ppr, censor_date=CENSOR_DATE)
    benchmarks = benchmark_prices(exit_labels, ppr)
    exit_labels = exit_labels.merge(benchmarks, on="scheme_id", how="left")
    exit_labels.to_csv(settings.SILVER_DIR / "exit_labels_pool.csv", index=False)

    exit_summary = {
        "censor_date": CENSOR_DATE,
        "schemes": int(len(exit_labels)),
        "sales_linked_schemes": int((exit_labels["sales_linked"] > 0).sum()),
        "sales_eligible_schemes": int(exit_labels["sales_eligible"].sum()),
        "sales_linkage_coverage": round(float((exit_labels["sales_linked"] > 0).sum() / max(1, len(exit_labels))), 4),
        "first_sale_dated": int(exit_labels["first_sale_date"].notna().sum()),
        "below_market_25pct": int(exit_labels["below_market_25pct"].fillna(0).sum()),
    }
    (settings.SILVER_DIR / "exit_labels_pool_summary.json").write_text(json.dumps(exit_summary, indent=2), encoding="utf-8")
    print(json.dumps(exit_summary, indent=2))

    labels = build_components(
        cohort, bcms, links, censor_date=CENSOR_DATE,
        exit_labels=exit_labels, rule_version="pain_v2",
    )
    labels.to_csv(settings.SILVER_DIR / "pain_labels_pool.csv", index=False)

    summary = component_prevalence(labels)
    summary["cohort_rows"] = int(len(cohort))
    summary["confirmed_link_schemes"] = int(links["scheme_id"].nunique())
    summary["activation_linked"] = int(labels["activation_linked"].sum())
    summary["linkage_coverage"] = round(float(links["scheme_id"].nunique() / max(1, len(cohort))), 4)
    summary["label_rule_version"] = "pain_v2"
    summary["censor_date"] = CENSOR_DATE
    summary["sales_linked_schemes"] = exit_summary["sales_linked_schemes"]
    (settings.SILVER_DIR / "pain_labels_pool_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
