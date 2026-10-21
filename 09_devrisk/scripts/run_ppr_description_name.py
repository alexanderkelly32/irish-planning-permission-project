"""Runner: description-based estate-name extraction -> PPR match.

Many descriptions name the development ("to be known as Oakfield Manor").
Extract those names, match PPR rows in the county, auto-confirm strong
matches. Free signal we hold in the register text itself.
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
from devrisk.entity_resolution.scoring import address_tokens  # noqa: E402

COUNTY_WORDS = {
    "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
    "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
    "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
    "waterford", "westmeath", "wexford", "wicklow",
}

NAME_PATTERNS = [
    re.compile(r"(?:to be|being|will be|is|are)\s+(?:known|named|called)\s+as\s+[\"']?([A-Z][A-Za-z'&.\- ]{3,60})[\"']?", re.IGNORECASE),
    re.compile(r"(?:the development|the scheme|the proposed development)\s+(?:known|called)\s+(?:as\s+)?[\"']?([A-Z][A-Za-z'&.\- ]{3,60})[\"']?", re.IGNORECASE),
    re.compile(r"[\"']([A-Z][A-Za-z'&.\- ]{3,40}?\s(?:Estate|Park|Manor|Heights|Wood|Grove|Drive|Crescent|Close|View|Lodge|Gardens|Court|Avenue|Green|Fields|Grange|Abbey|Hill|Vale|Rise|Dene|Glen))[\"']", re.IGNORECASE),
    re.compile(r"\b(?:named|entitled)\s+[\"']?([A-Z][A-Za-z'&.\- ]{3,40}?\s(?:Estate|Park|Manor|Heights|Wood|Grove|Drive|Crescent|Close|View|Lodge|Gardens|Court|Avenue|Green|Fields|Grange|Abbey|Hill|Vale|Rise|Dene|Glen))\b", re.IGNORECASE),
]


def extract_name(description: str) -> str | None:
    for pattern in NAME_PATTERNS:
        match = pattern.search(str(description or ""))
        if match:
            name = match.group(1).strip().strip(".,'\" ")
            tokens = [t for t in name.split() if t.lower() not in {"the", "a", "an", "of"}]
            if 2 <= len(tokens) <= 5:
                return " ".join(tokens)
            if 1 <= len(tokens) <= 5 and len(tokens[0]) >= 5:
                return tokens[0]
    return None


if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    have_sales = set()
    for path in ("scheme_sales_verified.csv", "scheme_sales_auto.csv"):
        p = settings.SILVER_DIR / path
        if p.exists():
            have_sales |= set(pd.read_csv(p)["scheme_id"])
    targets = mature[~mature["case_key"].astype(str).isin(have_sales)].copy()
    targets["estate_name"] = targets["DevelopmentDescription"].map(extract_name)
    named = targets[targets["estate_name"].notna()]
    print(f"schemes with description-named estate: {len(named)}", flush=True)

    ppr = prepare_ppr(pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet"))
    ppr["sale_date"] = pd.to_datetime(ppr["sale_date_dt"], utc=True, errors="coerce")

    confirmed_rows = []
    review_rows = []
    for _, scheme in named.iterrows():
        scheme_id = str(scheme["case_key"])
        name_tokens = address_tokens(scheme["estate_name"])
        county = next((c for c in COUNTY_WORDS if c in str(scheme["PlanningAuthority"]).lower()), "")
        frame = ppr[ppr["county_norm"] == county] if county else ppr
        if frame.empty or not name_tokens:
            continue
        overlap = frame["tokens"].map(lambda s: len(s & name_tokens))
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
                "estate_name": scheme["estate_name"],
                "match_method": "description_estate_name",
            }
            if candidate["overlap"] >= min(len(name_tokens), 3) and not candidate["not_full_market_price_flag"]:
                confirmed_rows.append(row)
            else:
                row["verdict"] = ""
                row["verdict_note"] = ""
                review_rows.append(row)

    confirmed = pd.DataFrame(confirmed_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    review = pd.DataFrame(review_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    confirmed.to_csv(settings.SILVER_DIR / "scheme_sales_description_name_auto.csv", index=False)
    review.to_csv(settings.SILVER_DIR / "audit" / "ppr_description_name_review.csv", index=False)
    summary = {
        "description_named_schemes": int(len(named)),
        "auto_confirmed_rows": int(len(confirmed)),
        "auto_confirmed_schemes": int(confirmed["scheme_id"].nunique()) if len(confirmed) else 0,
        "review_rows": int(len(review)),
        "review_schemes": int(review["scheme_id"].nunique()) if len(review) else 0,
    }
    (settings.SILVER_DIR / "ppr_description_name_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
