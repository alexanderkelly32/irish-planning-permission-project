"""Runner: 4Dublin pipeline bridge for Dublin cohort schemes.

The 4Dublin pipeline carries an independently-maintained Development_Address
for Dublin schemes. Bridge register -> pipeline by Planning_Reference
(app number), then PPR-match the pipeline address for Dublin targets without
sales. Also reports Dublin completion corroboration coverage.
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
from devrisk.entity_resolution.scoring import uncommon_place_tokens  # noqa: E402
from devrisk.ingestion.npad import case_key_for  # noqa: E402

DUBLIN_AUTHORITIES = {"Dublin City Council", "Dun Laoghaire Rathdown County Council",
                      "Fingal County Council", "South Dublin County Council"}


def tokens(text: str) -> set[str]:
    return {t for t in uncommon_place_tokens(str(text or ""), STOPWORDS) if len(t) >= 3}


def app_number(raw: str) -> str:
    text = str(raw or "").strip().upper()
    text = re.sub(r"\s+", "", text)
    return text


if __name__ == "__main__":
    pipeline = pd.read_csv(settings.SILVER_DIR / "4dublin" / "pipeline_all.csv", low_memory=False)
    pipeline = pipeline[pipeline["Planning_Authority"].isin(DUBLIN_AUTHORITIES)].copy()
    pipeline["app_norm"] = pipeline["Planning_Reference"].map(app_number)
    pipeline = pipeline.dropna(subset=["Development_Address"])
    pipeline["Development_Address"] = pipeline["Development_Address"].astype(str)
    pipeline = pipeline[pipeline["Development_Address"].str.len() > 5]
    pipeline = pipeline.sort_values(["app_norm", "Year_Quarter"]).groupby("app_norm").tail(1)

    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    mature = mature[mature["PlanningAuthority"].isin(DUBLIN_AUTHORITIES)].copy()
    mature["app_norm"] = mature["ApplicationNumber"].map(app_number)

    have_sales = set()
    for path in ("scheme_sales_verified.csv", "scheme_sales_auto.csv"):
        p = settings.SILVER_DIR / path
        if p.exists():
            have_sales |= set(pd.read_csv(p)["scheme_id"])

    merged = mature.merge(pipeline[["app_norm", "Development_Address", "Units_Completed_or_Completed_an", "Activity_On_Site"]],
                          on="app_norm", how="inner", suffixes=("", "_pipe"))
    print(f"dublin mature schemes: {len(mature)} | matched in pipeline: {len(merged)}", flush=True)
    targets = merged[~merged["case_key"].astype(str).isin(have_sales)]
    print(f"pipeline-matched dublin targets without sales: {len(targets)}", flush=True)

    ppr = prepare_ppr(pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet"))
    ppr["sale_date"] = pd.to_datetime(ppr["sale_date_dt"], utc=True, errors="coerce")
    dublin_ppr = ppr[ppr["county_norm"] == "dublin"]

    confirmed_rows = []
    review_rows = []
    for _, scheme in targets.iterrows():
        scheme_id = str(scheme["case_key"])
        pipe_address = str(scheme["Development_Address"] or "")
        name_tokens = tokens(pipe_address)
        if len(name_tokens) < 2:
            continue
        overlap = dublin_ppr["tokens"].map(lambda s: len(s & name_tokens))
        candidates = dublin_ppr[overlap >= 2].copy()
        if candidates.empty:
            continue
        candidates["overlap"] = overlap[overlap >= 2]
        grant = pd.Timestamp(scheme["grant_date_dt"])
        candidates = candidates[candidates["sale_date"] >= grant - pd.Timedelta(days=180)]
        candidates = candidates[~candidates["not_full_market_price_flag"]]
        if len(candidates) < 2:
            continue
        strong = candidates[candidates["overlap"] >= 3]
        for _, candidate in (strong if len(strong) >= 2 else candidates.head(0)).iterrows():
            confirmed_rows.append({
                "scheme_id": scheme_id,
                "ppr_source_row_id": candidate["source_row_id"],
                "sale_date": str(candidate["sale_date"].date()),
                "price": None if pd.isna(candidate["price_num"]) else float(candidate["price_num"]),
                "address": str(candidate["address_norm"])[:90],
                "eircode": str(candidate["eircode"] or ""),
                "not_full_market_price": int(bool(candidate["not_full_market_price_flag"])),
                "token_overlap": int(candidate["overlap"]),
                "match_method": "4dublin_pipeline_address",
            })
        for _, candidate in candidates[candidates["overlap"] == 2].iterrows():
            review_rows.append({
                "scheme_id": scheme_id,
                "ppr_source_row_id": candidate["source_row_id"],
                "sale_date": str(candidate["sale_date"].date()),
                "price": None if pd.isna(candidate["price_num"]) else float(candidate["price_num"]),
                "address": str(candidate["address_norm"])[:90],
                "eircode": str(candidate["eircode"] or ""),
                "token_overlap": int(candidate["overlap"]),
                "pipeline_address": pipe_address[:90],
            })

    confirmed = pd.DataFrame(confirmed_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    review = pd.DataFrame(review_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    confirmed.to_csv(settings.SILVER_DIR / "scheme_sales_4dublin_auto.csv", index=False)
    review.to_csv(settings.SILVER_DIR / "audit" / "ppr_4dublin_review.csv", index=False)
    summary = {
        "dublin_mature_schemes": int(len(mature)),
        "pipeline_matched": int(len(merged)),
        "pipeline_targets_without_sales": int(len(targets)),
        "auto_confirmed_rows": int(len(confirmed)),
        "auto_confirmed_schemes": int(confirmed["scheme_id"].nunique()) if len(confirmed) else 0,
        "review_rows": int(len(review)),
    }
    (settings.SILVER_DIR / "ppr_4dublin_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
