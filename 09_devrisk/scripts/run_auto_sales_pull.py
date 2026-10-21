"""Runner: automated sales pull for all BCMS-linked mature schemes.

Estate names come from the linked BCMS records (project name + address
uncommon tokens) - no human work. Same hardened matcher as the workbook pull:
estate-token match + town/street anchor + county filter + chronology.
Uncertain cases (weak single tokens, no town anchor) are skipped and can
fall back to the human workbook. Merges with human-verified sales.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.ppr_matching import STOPWORDS, prepare_ppr  # noqa: E402
from devrisk.entity_resolution.scoring import address_tokens, uncommon_place_tokens  # noqa: E402

CENSOR = "2026-09-27"

COUNTY_WORDS = {
    "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
    "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
    "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
    "waterford", "westmeath", "wexford", "wicklow",
}


def _norm_eircode(value: str) -> str:
    return str(value).strip().upper().replace(" ", "").replace("-", "")


def _county(authority: str) -> str:
    text = str(authority or "").lower()
    for county in COUNTY_WORDS:
        if county in text:
            return county
    return ""


def auto_pull() -> dict:
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    confirmed = links[links["confidence_band"] == "confirmed"]
    ppr_prepared = prepare_ppr(pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet"))

    existing = pd.read_csv(settings.SILVER_DIR / "ppr_links_all_granted.csv")
    have_sales = set(existing[existing["confidence_band"] == "confirmed"]["scheme_id"])
    verified_path = settings.SILVER_DIR / "scheme_sales_verified.csv"
    if verified_path.exists():
        have_sales |= set(pd.read_csv(verified_path)["scheme_id"])

    linked_events = confirmed.merge(
        bcms[["bcms_event_id", "address_full", "eircode", "town", "street", "project_name"]],
        on="bcms_event_id", how="inner",
    )
    import re as _re

    def _clean_tokens(text: str) -> set[str]:
        return {token for token in uncommon_place_tokens(str(text or ""), STOPWORDS) if _re.fullmatch(r"[a-z0-9]+", token)}

    street_tokens_by_event = {
        event_id: _clean_tokens(street)
        for event_id, street in linked_events.set_index("bcms_event_id")["street"].fillna("").items()
    }
    rows = []
    matched_schemes = 0
    skipped = 0
    multi_estate_skipped = 0
    for scheme_id, group in linked_events.groupby("scheme_id"):
        if scheme_id in have_sales:
            continue
        scheme = mature[mature["case_key"].astype(str) == scheme_id]
        if scheme.empty:
            continue
        scheme = scheme.iloc[0]

        # SDZ / SHD / area-based applications cover many estates; skip for human review.
        description = str(scheme.get("DevelopmentDescription") or "").lower()
        if any(pattern in description for pattern in (
            "strategic development zone", "strategic housing development", " sdz", " shd",
        )):
            multi_estate_skipped += 1
            continue

        towns: set[str] = set()
        for value in group["town"].dropna().astype(str):
            towns |= _clean_tokens(value)
        towns = {token for token in towns if token not in STOPWORDS}
        # Per-notice estate-name sets (not unioned): a PPR row must match ONE set.
        # Town, county and STREET tokens are excluded - road-level BCMS
        # addresses ("Tullow Road, Carlow") must not turn the road into an
        # estate name.
        name_sets = []
        for _, notice in group.iterrows():
            event_id = notice["bcms_event_id"]
            street_tokens = street_tokens_by_event.get(event_id, set())
            for text in (str(notice["address_full"] or ""), str(notice["project_name"] or "")):
                tokens = _clean_tokens(text) - COUNTY_WORDS - towns - street_tokens
                if tokens and all(len(token) >= 3 for token in tokens):
                    name_sets.append(frozenset(tokens))
        name_sets = [s for s in {frozenset(s) for s in name_sets} if s]

        # Multi-estate detection: any two sets sharing < 50% tokens -> ambiguous.
        ambiguous = False
        for i in range(len(name_sets)):
            for j in range(i + 1, len(name_sets)):
                a, b = name_sets[i], name_sets[j]
                if a != b:
                    overlap = len(a & b) / max(1, min(len(a), len(b)))
                    if overlap < 0.5 and not (a <= b or b <= a):
                        ambiguous = True
        if ambiguous:
            multi_estate_skipped += 1
            continue

        eircodes = {_norm_eircode(value) for value in group["eircode"].dropna().astype(str) if _norm_eircode(value)}
        # Single-token estate names are too risky without an eircode (they
        # capture whole localities); require >= 2 tokens per name set.
        name_sets = [s for s in name_sets if len(s) >= 2]
        if not name_sets and not eircodes:
            skipped += 1
            continue
        register_tokens = uncommon_place_tokens(str(scheme.get("DevelopmentAddress") or ""), STOPWORDS)
        anchors = (towns - COUNTY_WORDS) | (register_tokens - COUNTY_WORDS)
        anchors = {token for token in anchors if token not in STOPWORDS and len(token) >= 3}

        if not name_sets:
            skipped += 1
            continue

        county = _county(scheme["PlanningAuthority"])
        frame = ppr_prepared[ppr_prepared["county_norm"] == county] if county else ppr_prepared
        if frame.empty:
            skipped += 1
            continue

        def matches_one_set(tokens: frozenset) -> bool:
            return any(len(tokens & name_set) >= min(len(name_set), 2) for name_set in name_sets)

        token_hits = frame["tokens"].map(matches_one_set)
        anchor_hits = frame["tokens"].map(lambda tokens: len(tokens & anchors) >= 1) if anchors else pd.Series(True, index=frame.index)
        eircode_hit = frame["eircode"].fillna("").map(_norm_eircode).isin(eircodes) if eircodes else pd.Series(False, index=frame.index)
        mask = eircode_hit | (token_hits & anchor_hits)
        candidates = frame[mask].copy()
        if candidates.empty:
            skipped += 1
            continue

        candidates["sale_date"] = pd.to_datetime(candidates["sale_date_dt"], utc=True, errors="coerce")
        candidates = candidates.dropna(subset=["sale_date"])
        grant = pd.Timestamp(scheme["grant_date_dt"])
        candidates = candidates[candidates["sale_date"] >= grant - pd.Timedelta(days=180)]
        if candidates.empty:
            skipped += 1
            continue

        matched_schemes += 1
        for _, transaction in candidates.iterrows():
            rows.append({
                "scheme_id": scheme_id,
                "ppr_source_row_id": transaction["source_row_id"],
                "sale_date": str(transaction["sale_date"].date()),
                "price": None if pd.isna(transaction["price_num"]) else float(transaction["price_num"]),
                "address": str(transaction["address_norm"])[:100],
                "eircode": str(transaction["eircode"] or ""),
                "not_full_market_price": int(bool(transaction["not_full_market_price_flag"])),
                "match_method": "auto_bcms_estate",
            })

    sales = pd.DataFrame(rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    out = settings.SILVER_DIR / "scheme_sales_auto.csv"
    sales.to_csv(out, index=False)

    summary = {
        "bcms_linked_mature": int(len(linked_events["scheme_id"].unique())),
        "already_with_sales": int(len(have_sales)),
        "auto_matched_new_schemes": matched_schemes,
        "skipped_uncertain": skipped,
        "skipped_multi_estate_or_sdz": multi_estate_skipped,
        "auto_sales_rows": int(len(sales)),
        "out_path": str(out),
    }
    (settings.SILVER_DIR / "scheme_sales_auto_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    auto_pull()
