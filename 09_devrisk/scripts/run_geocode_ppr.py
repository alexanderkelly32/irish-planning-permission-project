"""Runner: resumable Nominatim geocoding of PPR candidate rows.

Geocodes only PPR rows that can plausibly belong to a mature scheme (clean
town token + county + post-grant). State is a JSON keyed by PPR row hash;
resume-safe; 1.1s delay (Nominatim usage policy); results cached per address.
Run: python run_geocode_ppr.py --limit N   (overnight: large N, resumable)
"""
from __future__ import annotations

import argparse
import json
import re as _re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.ppr_matching import STOPWORDS  # noqa: E402
from devrisk.entity_resolution.scoring import address_tokens, uncommon_place_tokens  # noqa: E402

STATE_PATH = settings.SILVER_DIR / "geocode_state.json"
CACHE_PATH = settings.SILVER_DIR / "geocode_cache.parquet"
USER_AGENT = "planning-risk-review/1.0 (local personal research; contact: local)"


def clean_towns() -> set[str]:
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    towns = set()
    for value in bcms["town"].dropna().astype(str):
        tokens = address_tokens(value)
        towns |= {t for t in tokens if _re.fullmatch(r"[a-z]{3,}", t) and t not in STOPWORDS}
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    for value in cohort["DevelopmentAddress"].dropna().astype(str):
        tokens = uncommon_place_tokens(value, STOPWORDS)
        towns |= {t for t in tokens if _re.fullmatch(r"[a-z]{4,}", t)}
    counties = {
        "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
        "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
        "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
        "waterford", "westmeath", "wexford", "wicklow",
    }
    return towns - counties


def uncovered_scheme_towns() -> set[str]:
    """Towns of mature schemes that still lack confirmed sales - the only rows
    worth geocoding for discovery."""
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    have_sales = set()
    for path in ("ppr_links_all_granted.csv", "scheme_sales_verified.csv", "scheme_sales_auto.csv", "scheme_sales_spatial.csv"):
        p = settings.SILVER_DIR / path
        if not p.exists() or p.stat().st_size == 0:
            continue
        try:
            frame = pd.read_csv(p)
        except pd.errors.EmptyDataError:
            continue
        if "confidence_band" in frame.columns:
            have_sales |= set(frame[frame["confidence_band"] == "confirmed"]["scheme_id"])
        else:
            have_sales |= set(frame["scheme_id"])
    targets = mature[~mature["case_key"].astype(str).isin(have_sales)]

    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay_path = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay_path.exists():
        links = pd.concat([links, pd.read_csv(overlay_path).reindex(columns=links.columns)], ignore_index=True)
    linked = links[links["confidence_band"] == "confirmed"].merge(
        bcms[["bcms_event_id", "town"]], on="bcms_event_id", how="inner"
    )
    towns: set[str] = set()
    for scheme_id, group in linked.groupby("scheme_id"):
        if scheme_id not in set(targets["case_key"].astype(str)):
            continue
        for value in group["town"].dropna().astype(str):
            towns |= {t for t in address_tokens(value) if _re.fullmatch(r"[a-z]{3,}", t) and t not in STOPWORDS}
    for value in targets["DevelopmentAddress"].dropna().astype(str):
        tokens = uncommon_place_tokens(value, STOPWORDS)
        towns |= {t for t in tokens if _re.fullmatch(r"[a-z]{4,}", t)}
    counties = {
        "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
        "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
        "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
        "waterford", "westmeath", "wexford", "wicklow",
    }
    return towns - counties


def build_queue(towns: set[str]) -> pd.DataFrame:
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr["sale_date"] = pd.to_datetime(ppr["sale_date_dt"], utc=True, errors="coerce")
    ppr = ppr[ppr["sale_date"] >= pd.Timestamp("2016-06-01", tz="UTC")]
    ppr_tokens = ppr["address_norm"].fillna("").map(address_tokens)
    mask = ppr_tokens.map(lambda tokens: bool(tokens & towns))
    return ppr[mask][["source_row_id", "row_hash", "address", "address_norm", "county_norm"]].copy()


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"done": {}, "failed": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def geocode(address: str) -> tuple[float | None, float | None]:
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": f"{address}, Ireland",
            "format": "json",
            "limit": 1,
            "bounded": 1,
            "viewbox": "-10.8,51.3,-5.8,55.4",
            "countrycodes": "ie",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    results = response.json() or []
    if not results:
        return None, None
    return float(results[0]["lat"]), float(results[0]["lon"])


def run(limit: int) -> dict:
    towns = uncovered_scheme_towns()
    queue = build_queue(towns)
    state = load_state()
    pending = queue[~queue["row_hash"].isin(state["done"]) & ~queue["row_hash"].isin(state["failed"])]
    processed = 0
    for _, row in pending.iterrows():
        if processed >= limit:
            break
        try:
            lat, lng = geocode(row["address_norm"])
            state["done"][row["row_hash"]] = {
                "lat": lat, "lng": lng,
                "address": row["address_norm"][:120],
                "source_row_id": row["source_row_id"],
            }
        except Exception as error:  # noqa: BLE001
            state["failed"][row["row_hash"]] = f"{type(error).__name__}: {str(error)[:150]}"
        processed += 1
        if processed % 25 == 0:
            save_state(state)
            print(f"processed {processed}/{limit}; done={len(state['done'])} failed={len(state['failed'])}", flush=True)
        time.sleep(1.1)
    save_state(state)

    cache_rows = [
        {"row_hash": key, "source_row_id": value["source_row_id"], "lat": value["lat"], "lng": value["lng"], "address": value["address"]}
        for key, value in state["done"].items()
    ]
    if cache_rows:
        pd.DataFrame(cache_rows).to_parquet(CACHE_PATH, index=False)

    summary = {
        "queue_total": int(len(queue)),
        "done": int(len(state["done"])),
        "failed": int(len(state["failed"])),
        "remaining": int(len(queue) - len(state["done"]) - len(state["failed"])),
        "cache_path": str(CACHE_PATH),
        "state_path": str(STATE_PATH),
    }
    (settings.SILVER_DIR / "geocode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    run(args.limit)
