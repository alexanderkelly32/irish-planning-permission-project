"""Runner: PPR linkage, exit labels and price benchmarks for the pool cohort.

Chain: scheme -> confirmed BCMS link -> BCMS address/eircode -> PPR
transactions. Only confirmed PPR links feed labels; coverage reported
separately. Outputs exit_labels_pool.csv, ppr_links_pool.csv and
price_benchmarks_pool.csv plus a summary JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.ppr_matching import (  # noqa: E402
    build_register_fallback_sets,
    build_scheme_address_sets,
    confidence_band_ppr,
    generate_ppr_candidates,
    prepare_ppr,
    score_ppr_candidate,
)
from devrisk.labels.economics import benchmark_prices, build_exit_labels  # noqa: E402

CENSOR_DATE = "2026-09-27"

if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    pool = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_pool.parquet")
    cohort = register[register["case_key"].isin(pool["case_key"])].drop_duplicates("case_key").copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms_links = pd.read_csv(settings.SILVER_DIR / "bcms_links_conservative_pool.csv")
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr_prepared = prepare_ppr(ppr)

    address_sets = build_scheme_address_sets(bcms, bcms_links)
    fallback_sets = build_register_fallback_sets(cohort, set(address_sets.keys()))
    address_sets = {**address_sets, **fallback_sets}
    print(f"schemes with address sets (BCMS + register fallback): {len(address_sets)}", flush=True)

    first_commencement = {}
    ahb_flags = {}
    linked_events = bcms_links[bcms_links["confidence_band"] == "confirmed"].merge(
        bcms[["bcms_event_id", "commencement_date_dt", "approved_housing_body"]],
        on="bcms_event_id", how="inner",
    )
    for scheme_id, group in linked_events.groupby("scheme_id"):
        dates = pd.to_datetime(group["commencement_date_dt"], utc=True, errors="coerce").dropna()
        if not dates.empty:
            first_commencement[str(scheme_id)] = dates.min()
        ahb_values = group["approved_housing_body"].dropna().astype(str).str.lower()
        ahb_flags[str(scheme_id)] = "yes" if ahb_values.isin({"yes", "y", "true"}).any() else ""

    link_rows = []
    for scheme_id, address_set in address_sets.items():
        candidates = generate_ppr_candidates(address_set, ppr_prepared)
        for _, candidate in candidates.head(60).iterrows():
            features = score_ppr_candidate(address_set, candidate)
            band, reasons = confidence_band_ppr(features)
            link_rows.append({
                "scheme_id": scheme_id,
                "ppr_source_row_id": candidate["source_row_id"],
                "confidence_band": band,
                "reasons": "; ".join(reasons),
                **features,
            })
    ppr_links = pd.DataFrame(link_rows)
    ppr_links.to_csv(settings.SILVER_DIR / "ppr_links_pool.csv", index=False)
    print("ppr link candidates:", len(ppr_links), "confirmed:",
          int((ppr_links["confidence_band"] == "confirmed").sum()), flush=True)

    schemes = cohort[
        ["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription"]
    ].rename(columns={
        "GrantDate": "final_grant_date",
        "NumResidentialUnits": "expected_units",
    }).copy()
    schemes["case_key"] = schemes["case_key"].astype(str)
    schemes["commencement_date"] = schemes["case_key"].map(first_commencement)
    schemes["approved_housing_body"] = schemes["case_key"].map(ahb_flags)

    exit_labels = build_exit_labels(schemes, ppr_links, ppr, censor_date=CENSOR_DATE)
    benchmarks = benchmark_prices(exit_labels, ppr)
    exit_labels = exit_labels.merge(benchmarks, on="scheme_id", how="left")

    exit_labels.to_csv(settings.SILVER_DIR / "exit_labels_pool.csv", index=False)

    linked_schemes = int((exit_labels["sales_linked"] > 0).sum())
    eligible = int(exit_labels["sales_eligible"].sum())
    summary = {
        "censor_date": CENSOR_DATE,
        "schemes": int(len(exit_labels)),
        "schemes_with_bcms_address_sets": len(address_sets),
        "ppr_link_candidates": int(len(ppr_links)),
        "confirmed_ppr_links": int((ppr_links["confidence_band"] == "confirmed").sum()),
        "schemes_with_confirmed_sales": linked_schemes,
        "sales_eligible_schemes": eligible,
        "sales_linkage_coverage": round(linked_schemes / max(1, len(exit_labels)), 4),
        "first_sale_before_grant_violations": int(
            (pd.to_datetime(exit_labels["first_sale_date"], utc=True, errors="coerce")
             < pd.to_datetime(cohort.set_index("case_key").reindex(exit_labels["scheme_id"])["GrantDate"].to_numpy(), utc=True)).sum()
        ),
    }
    out = settings.SILVER_DIR / "exit_labels_pool_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
