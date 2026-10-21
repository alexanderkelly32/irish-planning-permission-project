"""Runner: master manual-review workbook (the human labelling pipeline).

One row per mature pool scheme, ranked (uncovered sales first, then
larger), pre-filled with everything known: addresses, BCMS names, applicant,
eplanning URL, current links, top PPR candidates. Fill columns are blank.
CSV + XLSX. This replaces algorithmic attribution: every filled row becomes
a human label.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    for column in ("DevelopmentAddress", "DevelopmentDescription"):
        if column not in mature.columns:
            mature[column] = ""
    base_links = pd.read_csv(settings.ROOT / "01_flood" / "current" / "ge10_with_flooding.csv",
                             usecols=["PlanningAuthority", "ApplicationNumber", "LinkAppDetails"], low_memory=False)
    mature = mature.drop(columns=[c for c in ("LinkAppDetails",) if c in mature.columns])
    mature = mature.merge(base_links, on=["PlanningAuthority", "ApplicationNumber"], how="left")

    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    bcms_meta = confirmed.merge(bcms[["bcms_event_id", "address_full", "town", "project_name", "eircode"]],
                                on="bcms_event_id", how="inner")
    agg = bcms_meta.groupby("scheme_id").agg(
        bcms_names=("project_name", lambda s: " | ".join(s.dropna().astype(str).unique()[:2])),
        bcms_address=("address_full", "first"),
        bcms_eircode=("eircode", lambda s: " | ".join(s[s.fillna("").astype(str).str.strip().ne("")].astype(str).unique()[:2])),
    )
    mature = mature.merge(agg, left_on="case_key", right_index=True, how="left")

    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    mature = mature.merge(applicants[["case_key", "applicant_name"]], on="case_key", how="left")

    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    exit_labels["case_key"] = exit_labels["scheme_id"].astype(str)
    mature = mature.merge(exit_labels[["case_key", "sales_linked", "first_sale_date", "sales_eligible"]], on="case_key", how="left")

    candidates = pd.read_csv(settings.SILVER_DIR / "phase_sales_candidates.csv") if (settings.SILVER_DIR / "phase_sales_candidates.csv").exists() else pd.DataFrame()
    cand_agg = candidates.groupby("development_id").agg(
        top_candidates=("address", lambda s: " | ".join(s.dropna().astype(str).head(5))),
        candidate_count=("address", "size"),
    ) if len(candidates) else pd.DataFrame()
    mature = mature.merge(cand_agg, left_on="case_key", right_index=True, how="left")

    units = pd.to_numeric(mature["NumResidentialUnits"], errors="coerce")
    mature["_units"] = units.fillna(0)
    mature["_uncovered"] = mature["sales_linked"].fillna(0).eq(0).astype(int)
    mature = mature.sort_values(["_uncovered", "_units"], ascending=[False, False])

    workbook = pd.DataFrame({
        "row": np.arange(1, len(mature) + 1),
        "case_key": mature["case_key"].astype(str),
        "authority": mature["PlanningAuthority"],
        "grant_year": mature["grant_year"],
        "units": units,
        "register_address": mature["DevelopmentAddress"].fillna("").str.slice(0, 110),
        "description": mature["DevelopmentDescription"].fillna("").str.slice(0, 140),
        "bcms_names": mature["bcms_names"].fillna(""),
        "bcms_address": mature["bcms_address"].fillna("").str.slice(0, 110),
        "bcms_eircode": mature["bcms_eircode"].fillna(""),
        "applicant": mature["applicant_name"].fillna(""),
        "current_sales_linked": mature["sales_linked"].fillna(0).astype(int),
        "current_first_sale": mature["first_sale_date"].fillna(""),
        "eplanning_url": mature["LinkAppDetails"].fillna(""),
        "ppr_candidate_addresses": mature["top_candidates"].fillna(""),
        "estate_name_1": "",
        "estate_name_2": "",
        "estate_name_3": "",
        "first_sale_date_seen": "",
        "n_phases_seen": "",
        "phase_notes": "",
        "notes": "",
    })
    out_csv = settings.SILVER_DIR / "manual_review_workbook.csv"
    out_xlsx = settings.SILVER_DIR / "manual_review_workbook.xlsx"
    workbook.to_csv(out_csv, index=False)
    workbook.to_excel(out_xlsx, index=False)
    summary = {
        "rows": int(len(workbook)),
        "uncovered_first": int(workbook["current_sales_linked"].eq(0).sum()),
        "out_csv": str(out_csv),
        "out_xlsx": str(out_xlsx),
    }
    (settings.SILVER_DIR / "manual_review_workbook_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
