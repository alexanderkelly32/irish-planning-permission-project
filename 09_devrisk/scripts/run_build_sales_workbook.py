"""Runner: sales-matching workbook for human assistance.

One row per mature granted GE10 scheme (ranked: BCMS-linked and larger first),
pre-filled with everything we know, plus empty columns for the analyst:
estate/marketing names (as they appear in PPR addresses), eircode, sellable
units, build-to-sell flag and notes. The filled workbook feeds run_pull_sales.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.ppr_matching import STOPWORDS  # noqa: E402
from devrisk.entity_resolution.scoring import uncommon_place_tokens  # noqa: E402

if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    confirmed = links[links["confidence_band"] == "confirmed"]

    linked_events = confirmed.merge(
        bcms[["bcms_event_id", "address_full", "eircode", "town", "project_name"]],
        on="bcms_event_id", how="inner",
    )
    agg = linked_events.groupby("scheme_id").agg(
        bcms_address=("address_full", "first"),
        bcms_project_name=("project_name", lambda s: " | ".join(s.dropna().astype(str).unique()[:2])),
        bcms_eircode=("eircode", lambda s: " | ".join(s[s.fillna("").astype(str).str.strip().ne("")].astype(str).unique()[:3])),
        bcms_town=("town", "first"),
    )
    mature = mature.merge(agg, left_on="case_key", right_index=True, how="left")

    units = pd.to_numeric(mature["NumResidentialUnits"], errors="coerce")
    mature["size_band"] = pd.cut(units, bins=[-np.inf, 29, 99, 249, np.inf], labels=["10-29", "30-99", "100-249", "250+"])
    mature["_priority_units"] = units.fillna(0)

    def suggested_estate(row):
        candidates = []
        for text in (row.get("bcms_project_name") or "", row.get("bcms_address") or ""):
            for token in uncommon_place_tokens(text, STOPWORDS):
                if token not in candidates:
                    candidates.append(token)
        return " | ".join(candidates[:6])

    mature["suggested_estate_tokens"] = mature.apply(suggested_estate, axis=1)
    mature = mature.sort_values(["_priority_units"], ascending=False)

    workbook = pd.DataFrame({
        "scheme_id": mature["case_key"].astype(str),
        "authority": mature["PlanningAuthority"],
        "grant_year": mature["grant_year"],
        "units": units,
        "register_address": mature["DevelopmentAddress"].fillna(""),
        "description": mature["DevelopmentDescription"].fillna("").str.slice(0, 120),
        "bcms_linked": mature["bcms_address"].notna().astype(int),
        "bcms_address": mature["bcms_address"].fillna(""),
        "bcms_project_name": mature["bcms_project_name"].fillna(""),
        "bcms_eircode": mature["bcms_eircode"].fillna(""),
        "suggested_estate_tokens": mature["suggested_estate_tokens"].fillna(""),
        "estate_name_1": "",
        "estate_name_2": "",
        "estate_name_3": "",
        "eircode": "",
        "sellable_units": "",
        "is_build_to_sell": "",
        "notes": "",
    })
    out = settings.SILVER_DIR / "sales_workbook.csv"
    workbook.to_csv(out, index=False)
    print(f"workbook -> {out} ({len(workbook)} rows)")
    print(f"  BCMS-linked: {int(workbook['bcms_linked'].sum())}; with suggested tokens: {int(workbook['suggested_estate_tokens'].str.strip().ne('').sum())}")
