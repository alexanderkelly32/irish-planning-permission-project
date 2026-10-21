"""Runner: spatial PPR matching after geocoding.

For each mature scheme without confirmed sales: convert the scheme ITM site to
WGS84, find geocoded PPR rows within a radius, and confirm the strongest
(address token overlap or very close distance). Outputs confirmed spatial
links + a residual audit queue. Feeds the label rebuild.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pyproj import Transformer  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.scoring import token_similarity  # noqa: E402

ITM_TO_WGS84 = Transformer.from_crs("EPSG:2157", "EPSG:4326", always_xy=True)


def _have_sales() -> set[str]:
    have = set()
    for path in ("ppr_links_all_granted.csv", "scheme_sales_verified.csv", "scheme_sales_auto.csv"):
        p = settings.SILVER_DIR / path
        if not p.exists():
            continue
        frame = pd.read_csv(p)
        if "confidence_band" in frame.columns:
            have |= set(frame[frame["confidence_band"] == "confirmed"]["scheme_id"])
        else:
            have |= set(frame["scheme_id"])
    return have


def run() -> dict:
    cache_path = settings.SILVER_DIR / "geocode_cache.parquet"
    if not cache_path.exists():
        print("no geocode cache yet - run run_geocode_ppr.py first", flush=True)
        return {"status": "no_cache"}
    cache = pd.read_parquet(cache_path)
    cache = cache.dropna(subset=["lat", "lng"])
    cache["lat"] = cache["lat"].astype(float)
    cache["lng"] = cache["lng"].astype(float)
    print(f"geocoded rows available: {len(cache)}", flush=True)

    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    have = _have_sales()
    targets = mature[~mature["case_key"].astype(str).isin(have)]
    print(f"target schemes without sales: {len(targets)}", flush=True)

    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr = ppr[ppr["source_row_id"].isin(cache["source_row_id"])]
    merged = ppr.merge(cache[["source_row_id", "lat", "lng"]], on="source_row_id", how="inner")
    print(f"PPR rows with coordinates: {len(merged)}", flush=True)

    # Site coords: use BCMS-linked addresses if available, else register ITM.
    links_rows = []
    audit_rows = []
    for _, scheme in targets.iterrows():
        s_east = pd.to_numeric(pd.Series([scheme.get("ITMEasting")]), errors="coerce").iloc[0]
        s_north = pd.to_numeric(pd.Series([scheme.get("ITMNorthing")]), errors="coerce").iloc[0]
        if pd.isna(s_east) or pd.isna(s_north):
            continue
        s_lng, s_lat = ITM_TO_WGS84.transform(s_east, s_north)
        distance = np.hypot(merged["lng"] - s_lng, merged["lat"] - s_lat) * 111320.0  # approx metres
        nearby = merged[distance <= 400].copy()
        if nearby.empty:
            continue
        nearby["distance_metres"] = distance[distance <= 400].round(0)
        nearby["addr_sim"] = nearby["address_norm"].map(
            lambda text: token_similarity(str(scheme.get("DevelopmentAddress") or ""), text)
        )
        nearby = nearby.sort_values(["distance_metres", "addr_sim"], ascending=[True, False])
        best = nearby.head(40)
        for _, candidate in best.iterrows():
            row = {
                "scheme_id": str(scheme["case_key"]),
                "ppr_source_row_id": candidate["source_row_id"],
                "sale_date": str(candidate["sale_date_dt"])[:10],
                "price": None if pd.isna(candidate["price_num"]) else float(candidate["price_num"]),
                "address": str(candidate["address_norm"])[:90],
                "distance_metres": float(candidate["distance_metres"]),
                "address_similarity": round(float(candidate["addr_sim"]), 3),
                "not_full_market_price": int(bool(candidate["not_full_market_price_flag"])),
            }
            if candidate["distance_metres"] <= 150 and candidate["addr_sim"] >= 0.35 and not candidate["not_full_market_price_flag"]:
                row["confidence_band"] = "confirmed"
                links_rows.append(row)
            else:
                row["confidence_band"] = "candidate"
                audit_rows.append(row)

    links = pd.DataFrame(links_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    audit = pd.DataFrame(audit_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    links.to_csv(settings.SILVER_DIR / "scheme_sales_spatial.csv", index=False)
    if len(audit):
        audit.to_csv(settings.SILVER_DIR / "audit_spatial_ppr.csv", index=False)

    linked_schemes = set(links["scheme_id"]) if len(links) else set()
    candidate_schemes = set(audit["scheme_id"]) if len(audit) else set()
    summary = {
        "geocoded_rows": int(len(cache)),
        "target_schemes": int(len(targets)),
        "schemes_with_spatial_candidates": int(len(linked_schemes | candidate_schemes)),
        "confirmed_spatial_links": int(len(links)),
        "confirmed_schemes": int(len(linked_schemes)),
        "audit_rows": int(len(audit)),
    }
    (settings.SILVER_DIR / "spatial_match_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
