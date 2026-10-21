"""Runner: register-address PPR name matcher (underexploited signal).

For every scheme without confirmed sales, match PPR rows in the same county
that share >=2 uncommon tokens with the REGISTER's own DevelopmentAddress
(not just BCMS) - the register often names the estate directly ("The Mill
Race, Co. Carlow"). Chronology: sale >= grant - 180d. Strong matches
(token overlap >= 3 or overlap >= 2 + town anchor) are auto-confirmed;
weaker ones go to the review queue.
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
from devrisk.entity_resolution.ppr_matching import STOPWORDS, prepare_ppr  # noqa: E402
from devrisk.entity_resolution.scoring import address_tokens, uncommon_place_tokens  # noqa: E402

COUNTY_WORDS = {
    "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
    "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
    "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
    "waterford", "westmeath", "wexford", "wicklow",
}


def county_of(authority: str) -> str:
    text = str(authority or "").lower()
    for county in COUNTY_WORDS:
        if county in text:
            return county
    return ""


if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()

    have_sales = set()
    for path in ("scheme_sales_verified.csv", "scheme_sales_auto.csv"):
        p = settings.SILVER_DIR / path
        if p.exists():
            have_sales |= set(pd.read_csv(p)["scheme_id"])
    targets = mature[~mature["case_key"].astype(str).isin(have_sales)]
    print(f"targets without sales: {len(targets)}", flush=True)

    ppr = prepare_ppr(pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet"))
    ppr["sale_date"] = pd.to_datetime(ppr["sale_date_dt"], utc=True, errors="coerce")

    confirmed_rows = []
    review_rows = []
    for _, scheme in targets.iterrows():
        scheme_id = str(scheme["case_key"])
        address = str(scheme.get("DevelopmentAddress") or "")
        tokens = uncommon_place_tokens(address, STOPWORDS) - COUNTY_WORDS
        tokens = {t for t in tokens if len(t) >= 3}
        if len(tokens) < 2:
            continue
        county = county_of(scheme["PlanningAuthority"])
        frame = ppr[ppr["county_norm"] == county] if county else ppr
        if frame.empty:
            continue
        overlap = frame["uncommon_tokens"].map(lambda s: len(s & tokens))
        candidates = frame[overlap >= 2].copy()
        if candidates.empty:
            continue
        candidates["overlap"] = overlap[overlap >= 2]
        grant = pd.Timestamp(scheme["grant_date_dt"])
        candidates = candidates[candidates["sale_date"] >= grant - pd.Timedelta(days=180)]
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
                "match_method": "register_address_tokens",
            }
            if candidate["overlap"] >= 3 and not candidate["not_full_market_price_flag"]:
                confirmed_rows.append(row)
            else:
                row["verdict"] = ""
                row["verdict_note"] = ""
                review_rows.append(row)

    confirmed = pd.DataFrame(confirmed_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    review = pd.DataFrame(review_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    confirmed.to_csv(settings.SILVER_DIR / "scheme_sales_register_name_auto.csv", index=False)
    review.to_csv(settings.SILVER_DIR / "audit" / "ppr_register_name_review.csv", index=False)

    summary = {
        "auto_confirmed_rows": int(len(confirmed)),
        "auto_confirmed_schemes": int(confirmed["scheme_id"].nunique()) if len(confirmed) else 0,
        "review_rows": int(len(review)),
        "review_schemes": int(review["scheme_id"].nunique()) if len(review) else 0,
        "note": "auto = register-address token overlap >= 3 + chronology; review = overlap 2",
    }
    (settings.SILVER_DIR / "ppr_register_name_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
