"""Runner: townland geocoder for PPR rows (offline, from OSi open data).

PPR addresses frequently mention townlands ("Bunratty West", "Moodoge"). This
looks up townland names in each PPR address (n-gram matching against the OSi
townlands table) and assigns the townland centroid (ITM) as approximate
coordinates. Then spatial-matches PPR rows to cohort schemes.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

RAW_CSV = settings.RAW_DIR / "townlands_100m.csv"
TOWNLAND_TABLE = settings.SILVER_DIR / "townland_centroids.parquet"
GEOCODE_OUT = settings.SILVER_DIR / "ppr_townland_geocode.parquet"


def build_townland_table() -> pd.DataFrame:
    frame = pd.read_csv(RAW_CSV, usecols=["TD_ENGLISH", "COUNTY", "CENTROID_X", "CENTROID_Y"], low_memory=False)
    frame["name_norm"] = frame["TD_ENGLISH"].fillna("").astype(str).str.lower().str.strip()
    frame["county_norm"] = frame["COUNTY"].fillna("").astype(str).str.lower().str.strip()
    table = frame[frame["name_norm"].ne("")].copy()
    table = table.drop_duplicates(subset=["name_norm", "county_norm"], keep="first")
    table.to_parquet(TOWNLAND_TABLE, index=False)
    return table


def geocode_ppr() -> pd.DataFrame:
    table = pd.read_parquet(TOWNLAND_TABLE)
    names = set(table["name_norm"])
    multi = {name for name in names if " " in name}
    # county-qualified lookup to disambiguate common names
    by_name = {name: group for name, group in table.groupby("name_norm")}

    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr["sale_date"] = pd.to_datetime(ppr["sale_date_dt"], utc=True, errors="coerce")
    ppr = ppr[ppr["sale_date"] >= pd.Timestamp("2016-06-01", tz="UTC")]

    rows = []
    for _, row in ppr.iterrows():
        address = str(row["address_norm"] or "").lower()
        tokens = [t for t in re.split(r"[^a-z']+", address) if len(t) >= 3]
        if not tokens:
            continue
        county = str(row["county_norm"] or "")
        matched = None
        # try 3- and 2-token n-grams first (multi-word townlands), then 1-token
        for n in (3, 2, 1):
            found = False
            for i in range(len(tokens) - n + 1):
                ngram = " ".join(tokens[i:i + n])
                if ngram not in names:
                    continue
                group = by_name[ngram]
                if county and any(group["county_norm"] == county):
                    match_row = group[group["county_norm"] == county].iloc[0]
                else:
                    match_row = group.iloc[0]
                matched = (ngram, match_row["CENTROID_X"], match_row["CENTROID_Y"], match_row["county_norm"])
                found = True
                break
            if found:
                break
        if matched:
            rows.append({
                "source_row_id": row["source_row_id"],
                "townland": matched[0],
                "itm_easting": float(matched[1]),
                "itm_northing": float(matched[2]),
                "townland_county": matched[3],
            })
    frame = pd.DataFrame(rows)
    frame.to_parquet(GEOCODE_OUT, index=False)
    return frame


if __name__ == "__main__":
    table = build_townland_table()
    print(f"townlands loaded: {len(table)}", flush=True)
    geocoded = geocode_ppr()
    summary = {
        "townlands": int(len(table)),
        "ppr_rows_townland_geocoded": int(len(geocoded)),
        "out_path": str(GEOCODE_OUT),
    }
    (settings.SILVER_DIR / "townland_geocode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
