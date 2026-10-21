"""Runner: PPR matching for the BCMS multi-estate / single-token schemes we
skipped in the auto-pull (the 'BCMS says Tullow Road but houses marketed as
X' cases). Each BCMS notice's own name set is matched separately with town
anchor + chronology; tight matches auto-confirm.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.ppr_matching import STOPWORDS, prepare_ppr  # noqa: E402
from devrisk.entity_resolution.scoring import address_tokens, uncommon_place_tokens  # noqa: E402

COUNTY_WORDS = {
    "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
    "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
    "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
    "waterford", "westmeath", "wexford", "wicklow",
}


def clean_tokens(text: str) -> set[str]:
    return {t for t in uncommon_place_tokens(str(text or ""), STOPWORDS) if re.fullmatch(r"[a-z0-9]+", t)}


if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = pd.read_csv(settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv")
    links = pd.concat([links, overlay.reindex(columns=links.columns)], ignore_index=True)
    confirmed_links = links[links["confidence_band"] == "confirmed"]

    have_sales = set()
    for path in ("scheme_sales_verified.csv", "scheme_sales_auto.csv", "scheme_sales_register_name_auto.csv", "scheme_sales_description_name_auto.csv"):
        p = settings.SILVER_DIR / path
        if p.exists():
            have_sales |= set(pd.read_csv(p)["scheme_id"])

    targets = mature[~mature["case_key"].astype(str).isin(have_sales)].copy()
    linked_events = confirmed_links.merge(
        bcms[["bcms_event_id", "address_full", "eircode", "town", "street", "project_name"]],
        on="bcms_event_id", how="inner",
    )
    target_events = linked_events[linked_events["scheme_id"].isin(targets["case_key"].astype(str))]
    print(f"target schemes with BCMS notices: {target_events['scheme_id'].nunique()}", flush=True)

    ppr = prepare_ppr(pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet"))
    ppr["sale_date"] = pd.to_datetime(ppr["sale_date_dt"], utc=True, errors="coerce")

    scheme_meta = {str(row["case_key"]): row for _, row in mature.iterrows()}
    confirmed_rows = []
    review_rows = []
    for scheme_id, group in target_events.groupby("scheme_id"):
        scheme = scheme_meta[scheme_id]
        county = next((c for c in COUNTY_WORDS if c in str(scheme["PlanningAuthority"]).lower()), "")
        frame = ppr[ppr["county_norm"] == county] if county else ppr
        if frame.empty:
            continue
        grant = pd.Timestamp(scheme["grant_date_dt"])
        towns = set()
        for value in group["town"].dropna().astype(str):
            towns |= clean_tokens(value)
        for _, notice in group.iterrows():
            street_tokens = clean_tokens(notice["street"])
            name_set = clean_tokens(notice["address_full"]) - COUNTY_WORDS - towns - street_tokens
            project_set = clean_tokens(notice["project_name"]) - COUNTY_WORDS - towns
            for name_tokens in (name_set, project_set):
                if not name_tokens or all(len(t) < 4 for t in name_tokens):
                    continue
                required = min(len(name_tokens), 2)
                overlap = frame["tokens"].map(lambda s: len(s & name_tokens))
                candidates = frame[overlap >= required].copy()
                if candidates.empty:
                    continue
                candidates["overlap"] = overlap[overlap >= required]
                candidates = candidates[candidates["sale_date"] >= grant - pd.Timedelta(days=180)]
                if candidates.empty:
                    continue
                # anchor: town tokens or the register address's uncommon tokens
                anchors = towns | (clean_tokens(scheme["DevelopmentAddress"]) - COUNTY_WORDS)
                if anchors:
                    anchor_hit = candidates["tokens"].map(lambda s: len(s & anchors) >= 1)
                    candidates = candidates[anchor_hit]
                if candidates.empty:
                    continue
                for _, candidate in candidates.iterrows():
                    row = {
                        "scheme_id": scheme_id,
                        "ppr_source_row_id": candidate["source_row_id"],
                        "sale_date": str(candidate["sale_date"].date()),
                        "price": None if pd.isna(candidate["price_num"]) else float(candidate["price_num"]),
                        "address": str(candidate["address_norm"])[:90],
                        "eircode": str(candidate["eircode"] or ""),
                        "not_full_market_price": int(bool(candidate["not_full_market_price_flag"])),
                        "token_overlap": int(candidate["overlap"]),
                        "bcms_name": " ".join(sorted(name_tokens)),
                        "match_method": "bcms_notice_name",
                    }
                    if len(name_tokens) >= 2 and candidate["overlap"] >= 2 and not candidate["not_full_market_price_flag"]:
                        confirmed_rows.append(row)
                    else:
                        row["verdict"] = ""
                        row["verdict_note"] = ""
                        review_rows.append(row)

    confirmed = pd.DataFrame(confirmed_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    review = pd.DataFrame(review_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    confirmed.to_csv(settings.SILVER_DIR / "scheme_sales_bcms_notice_auto.csv", index=False)
    review.to_csv(settings.SILVER_DIR / "audit" / "ppr_bcms_notice_review.csv", index=False)
    summary = {
        "auto_confirmed_rows": int(len(confirmed)),
        "auto_confirmed_schemes": int(confirmed["scheme_id"].nunique()) if len(confirmed) else 0,
        "review_rows": int(len(review)),
        "review_schemes": int(review["scheme_id"].nunique()) if len(review) else 0,
    }
    (settings.SILVER_DIR / "ppr_bcms_notice_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
