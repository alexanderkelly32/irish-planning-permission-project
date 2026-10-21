"""PPR matching: link scheme address sets to Property Price Register transactions.

Chain: scheme -> confirmed BCMS link -> BCMS address/eircode/project name ->
PPR transactions. PPR has no planning reference, so linking is probabilistic
(brief section 10.6): eircode exact match, address token similarity, uncommon
estate-name agreement, county agreement, sale-date chronology (sale cannot
predate commencement/grant), price plausibility. Confidence bands as in
section 10.4; only confirmed links enter labels; coverage reported separately.

Performance note: PPR tokens are precomputed once per snapshot; candidate
generation is vectorised over the county subset.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .scoring import address_tokens, normalize_address, token_similarity, uncommon_place_tokens

STOPWORDS = {
    "the", "road", "street", "avenue", "estate", "no", "number", "close", "court",
    "lane", "park", "drive", "groves", "grove", "way", "house", "houses",
    "development", "site", "lands", "townland", "co", "county", "apartment",
    "apartments", "terrace", "mews", "walk", "view", "wood", "lawn", "green",
    "heights", "gardens", "crescent", "square", "rise", "hall", "lodge",
}


def build_scheme_address_sets(
    bcms_events: pd.DataFrame,
    bcms_links: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    """One address set per scheme from confirmed BCMS links."""
    confirmed = bcms_links[bcms_links["confidence_band"] == "confirmed"]
    merged = confirmed.merge(
        bcms_events[
            ["bcms_event_id", "address_full", "eircode", "town", "street",
             "project_name", "county", "commencement_date_dt"]
        ],
        on="bcms_event_id",
        how="inner",
    )
    sets: dict[str, list[dict[str, Any]]] = {}
    for scheme_id, group in merged.groupby("scheme_id"):
        addresses = []
        for _, row in group.iterrows():
            addresses.append({
                "address_full": str(row.get("address_full") or ""),
                "eircode": str(row.get("eircode") or "").strip(),
                "town": str(row.get("town") or "").strip(),
                "street": str(row.get("street") or "").strip(),
                "project_name": str(row.get("project_name") or "").strip(),
                "county": str(row.get("county") or "").strip(),
                "commencement_date": row.get("commencement_date_dt"),
            })
        sets[str(scheme_id)] = addresses
    return sets


def prepare_ppr(ppr: pd.DataFrame) -> pd.DataFrame:
    """Precompute token sets once per snapshot (vectorised)."""
    frame = ppr.copy()
    frame["tokens"] = frame["address_norm"].fillna("").map(lambda text: frozenset(address_tokens(text)))
    frame["uncommon_tokens"] = frame["address_norm"].fillna("").map(
        lambda text: frozenset(uncommon_place_tokens(text, STOPWORDS))
    )
    frame["eircode_norm"] = frame["eircode"].fillna("").map(_normalize_eircode)
    return frame


def _normalize_eircode(value: str) -> str:
    return str(value).strip().upper().replace(" ", "").replace("-", "")


def _routing_key(value: str) -> str:
    """Eircode routing key (first 3 chars); 'dublin 14' -> 'D14'."""
    import re

    text = str(value).strip().upper().replace(" ", "").replace("-", "")
    match = re.search(r"^([A-Z]{1}\d{2})", text)
    if match:
        return match.group(1)
    match = re.search(r"DUBLIN(\d{1,2})$", text)
    if match:
        return "D" + match.group(1).zfill(2)
    return ""


def build_register_fallback_sets(
    cohort: pd.DataFrame,
    covered_schemes: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Fallback address sets from the register for schemes without BCMS sets."""
    fallback: dict[str, list[dict[str, Any]]] = {}
    for _, row in cohort.iterrows():
        scheme_id = str(row["case_key"])
        if scheme_id in covered_schemes:
            continue
        fallback[scheme_id] = [{
            "address_full": str(row.get("DevelopmentAddress") or ""),
            "eircode": str(row.get("DevelopmentPostcode") or "").strip(),
            "town": "",
            "street": "",
            "project_name": "",
            "county": _county_from_authority(row.get("PlanningAuthority")),
            "commencement_date": None,
            "grant_date": row.get("GrantDate"),
        }]
    return fallback


def _county_from_authority(authority: object) -> str:
    text = str(authority or "").lower()
    for county in ("carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
                   "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
                   "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
                   "waterford", "westmeath", "wexford", "wicklow"):
        if county in text:
            return county
    return ""


def generate_ppr_candidates(
    address_set: list[dict[str, Any]],
    ppr_prepared: pd.DataFrame,
    *,
    min_address_similarity: float = 0.35,
) -> pd.DataFrame:
    """Broad candidate rules: county + (eircode OR uncommon-token overlap)."""
    if not address_set:
        return pd.DataFrame()
    county = next((item["county"] for item in address_set if item["county"]), "")
    frame = ppr_prepared[ppr_prepared["county_norm"] == county.lower()] if county else ppr_prepared
    if frame.empty:
        return pd.DataFrame()

    eircodes = {_normalize_eircode(item["eircode"]) for item in address_set if item["eircode"]}
    routing_keys = {_routing_key(item["eircode"]) for item in address_set if item["eircode"]}
    scheme_tokens = set()
    for item in address_set:
        scheme_tokens |= address_tokens(item["address_full"]) | address_tokens(item["project_name"])
    uncommon = scheme_tokens - STOPWORDS

    token_overlap = frame["tokens"].map(lambda tokens: len(tokens & scheme_tokens))
    uncommon_overlap = frame["uncommon_tokens"].map(lambda tokens: len(tokens & uncommon))
    eircode_hit = frame["eircode_norm"].isin(eircodes) if eircodes else pd.Series(False, index=frame.index)
    routing_hit = frame["eircode_norm"].map(_routing_key).isin(routing_keys) if routing_keys else pd.Series(False, index=frame.index)

    mask = (token_overlap >= 2) | (uncommon_overlap >= 1) | eircode_hit | (routing_hit & (uncommon_overlap >= 1))
    candidates = frame[mask].copy()
    if candidates.empty:
        return candidates
    candidates["eircode_match"] = eircode_hit[mask].astype(int)
    candidates["routing_key_match"] = routing_hit[mask].astype(int)
    candidates["uncommon_token_overlap"] = uncommon_overlap[mask]
    candidates["token_overlap"] = token_overlap[mask]

    scheme_address_sets = [address_tokens(item["address_full"]) for item in address_set]
    scheme_address_joined = " ".join(item["address_full"] for item in address_set)
    candidates["address_token_similarity"] = candidates["address_norm"].map(
        lambda text: _jaccard(address_tokens(text), scheme_tokens)
    )
    candidates["address_similarity_max"] = candidates["tokens"].map(
        lambda tokens: max((len(tokens & s) / max(1, len(tokens | s)) for s in scheme_address_sets), default=0.0)
    )
    # Eircode hits are exempt from the similarity gate: an exact eircode on a
    # new estate identifies the scheme even when address forms differ.
    candidates = candidates[
        (candidates["address_token_similarity"] >= min_address_similarity) | (candidates["eircode_match"] == 1)
    ]
    return candidates.reset_index(drop=True)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def score_ppr_candidate(address_set: list[dict[str, Any]], row: pd.Series) -> dict[str, Any]:
    anchors = []
    for item in address_set:
        if pd.notna(item.get("commencement_date")):
            anchors.append(pd.Timestamp(item["commencement_date"]))
        if pd.notna(item.get("grant_date")):
            anchors.append(pd.Timestamp(item["grant_date"]))
    earliest_anchor = min(anchors) if anchors else None
    sale_date = row.get("sale_date_dt")
    sale_after_commencement = None
    if earliest_anchor is not None and pd.notna(sale_date):
        sale_ts = pd.Timestamp(sale_date)
        if sale_ts.tzinfo is None:
            sale_ts = sale_ts.tz_localize("UTC")
        earliest = earliest_anchor
        if earliest.tzinfo is None:
            earliest = earliest.tz_localize("UTC")
        sale_after_commencement = int(sale_ts >= earliest)
    features = {
        "eircode_match": int(row.get("eircode_match", 0)),
        "routing_key_match": int(row.get("routing_key_match", 0)),
        "uncommon_token_overlap": int(row.get("uncommon_token_overlap", 0)),
        "address_token_similarity": round(float(row.get("address_token_similarity", 0.0)), 4),
        "address_similarity_max": round(float(row.get("address_similarity_max", 0.0)), 4),
        "sale_after_commencement": sale_after_commencement,
        "price": None if pd.isna(row.get("price_num", np.nan)) else float(row["price_num"]),
        "not_full_market_price": int(bool(row.get("not_full_market_price_flag", False))),
        "address_norm": str(row.get("address_norm", "")),
        "sale_date": str(row.get("sale_date_dt", "")),
    }
    return features


def confidence_band_ppr(features: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    full_market = not features.get("not_full_market_price")
    if features.get("eircode_match") and features.get("sale_after_commencement") == 1:
        reasons.append("eircode exact + chronology")
        return ("confirmed", reasons) if full_market else ("probable", reasons)
    if features.get("eircode_match"):
        reasons.append("eircode exact (chronology unknown)")
        return ("probable", reasons) if full_market else ("rejected", reasons)
    if (
        features.get("uncommon_token_overlap", 0) >= 1
        and features.get("address_token_similarity", 0.0) >= 0.5
        and features.get("sale_after_commencement") == 1
    ):
        reasons.append("uncommon estate-name agreement + address similarity + chronology")
        return ("confirmed", reasons) if full_market else ("probable", reasons)
    if (
        features.get("routing_key_match")
        and features.get("uncommon_token_overlap", 0) >= 1
        and features.get("sale_after_commencement") == 1
    ):
        reasons.append("routing-key match + estate-name agreement + chronology")
        return ("probable", reasons) if full_market else ("rejected", reasons)
    if features.get("address_token_similarity", 0.0) >= 0.6:
        reasons.append("high address token similarity")
        return ("probable", reasons) if full_market else ("rejected", reasons)
    return "rejected", ["insufficient evidence"]
