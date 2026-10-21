"""Runner: townland-based spatial matching -> consolidated PPR review pack.

Matches townland-geocoded PPR rows to cohort schemes within 1km, excludes
schemes with existing confirmed sales, ranks candidates by distance + address
similarity, and writes the review queue (top 5 per scheme).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.scoring import address_tokens  # noqa: E402

if __name__ == "__main__":
    geocoded = pd.read_parquet(settings.SILVER_DIR / "ppr_townland_geocode.parquet")
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    mature["easting"] = pd.to_numeric(mature["ITMEasting"], errors="coerce")
    mature["northing"] = pd.to_numeric(mature["ITMNorthing"], errors="coerce")
    mature = mature.dropna(subset=["easting", "northing"])
    mature["addr_tokens"] = mature["DevelopmentAddress"].fillna("").map(address_tokens)

    have_sales = set()
    for path in ("scheme_sales_verified.csv", "scheme_sales_auto.csv"):
        p = settings.SILVER_DIR / path
        if p.exists():
            have_sales |= set(pd.read_csv(p)["scheme_id"])

    targets = mature[~mature["case_key"].astype(str).isin(have_sales)]
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr = ppr[ppr["source_row_id"].isin(geocoded["source_row_id"])]
    merged = ppr.merge(geocoded, on="source_row_id", how="inner")
    merged["sale_date"] = pd.to_datetime(merged["sale_date_dt"], utc=True, errors="coerce")

    rows = []
    for _, scheme in targets.iterrows():
        scheme_id = str(scheme["case_key"])
        distance = np.hypot(merged["itm_easting"] - scheme["easting"], merged["itm_northing"] - scheme["northing"])
        nearby = merged[distance <= 1000].copy()
        if nearby.empty:
            continue
        nearby["distance_metres"] = distance[distance <= 1000].round(0)
        nearby["addr_sim"] = nearby["address_norm"].map(
            lambda text: len(address_tokens(text) & set(scheme["addr_tokens"])) / max(1, len(address_tokens(text)))
        )
        nearby = nearby.sort_values(["distance_metres"]).head(5)
        for _, candidate in nearby.iterrows():
            rows.append({
                "scheme_id": scheme_id,
                "scheme_address": str(scheme["DevelopmentAddress"])[:80],
                "ppr_source_row_id": candidate["source_row_id"],
                "ppr_address": str(candidate["address_norm"])[:90],
                "townland": candidate["townland"],
                "sale_date": str(candidate["sale_date"])[:10],
                "price": None if pd.isna(candidate["price_num"]) else float(candidate["price_num"]),
                "distance_metres": float(candidate["distance_metres"]),
                "address_similarity": round(float(candidate["addr_sim"]), 3),
                "not_full_market_price": int(bool(candidate["not_full_market_price_flag"])),
                "verdict": "",
                "verdict_note": "",
            })

    queue = pd.DataFrame(rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    queue.to_csv(settings.SILVER_DIR / "audit" / "ppr_townland_candidates.csv", index=False)
    summary = {
        "candidate_rows": int(len(queue)),
        "schemes_with_candidates": int(queue["scheme_id"].nunique()) if len(queue) else 0,
        "schemes_within_400m": int((queue["distance_metres"] <= 400).sum()) if len(queue) else 0,
        "out_path": str(settings.SILVER_DIR / "audit" / "ppr_townland_candidates.csv"),
    }
    (settings.SILVER_DIR / "townland_match_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
