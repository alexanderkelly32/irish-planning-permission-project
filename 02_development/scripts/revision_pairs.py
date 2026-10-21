"""Conservative refused-to-revised-to-granted candidate generation."""
from __future__ import annotations

import json
import re
from itertools import product

import numpy as np
import pandas as pd

STOPWORDS = {"the", "and", "with", "for", "from", "site", "development", "proposed", "permission"}
DELTA_COLUMNS = {
    "units": "units_total_best",
    "storeys": "max_storeys_best",
    "site_area_sqm": "site_area_sqm_best",
    "floor_area_sqm": "floor_area_sqm_best",
    "open_space_sqm": "open_space_sqm_best",
    "parking_spaces": "parking_spaces_best",
    "cycle_parking_spaces": "cycle_parking_spaces_best",
}
MAX_ADDRESS_GROUP_SIZE = 2


def normalize_address(value: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def normalize_outcome(value: object) -> str:
    text = str(value or "").upper()
    if "REFUS" in text:
        return "REFUSED"
    if "GRANT" in text or "CONDITIONAL" in text or "UNCONDITIONAL" in text:
        return "GRANTED"
    return "OTHER"


def base_application_reference(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
    return re.sub(r"(?:f?ep|e\d*)$", "", text)


def is_administrative_event_reference(value: object) -> bool:
    """Identify application-number forms used for extensions and other events.

    These are decisions on an earlier permission, not a fresh submitted scheme, so
    they must not be treated as a refused-to-revised-to-granted pair.
    """
    text = re.sub(r"\s+", "", str(value or "").lower())
    return bool(re.search(r"(?:/|\d)(?:f?ep(?:\(\d+\)|\d*(?:/\d+)?)?|e\d*)$", text))


def token_similarity(left: object, right: object) -> float:
    tokens = lambda value: {x for x in re.findall(r"[a-z0-9]{3,}", str(value or "").lower()) if x not in STOPWORDS}
    a, b = tokens(left), tokens(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def _number(row: pd.Series, column: str) -> float | None:
    value = pd.to_numeric(row.get(column), errors="coerce")
    return None if pd.isna(value) else float(value)


def _pair_row(original: pd.Series, revised: pd.Series, method: str, similarity: float) -> dict[str, object]:
    deltas: dict[str, dict[str, float | None]] = {}
    observed = 0
    for label, column in DELTA_COLUMNS.items():
        before, after = _number(original, column), _number(revised, column)
        if before is not None and after is not None:
            observed += 1
            deltas[label] = {"from": before, "to": after, "delta": after - before}
    same_site_confidence = 0.98 if method == "site_id" else min(0.90, 0.45 + 0.35 * similarity)
    change_confidence = observed / len(DELTA_COLUMNS)
    return {
        "original_case_key": original["case_key"],
        "revised_case_key": revised["case_key"],
        "original_outcome": "REFUSED",
        "revised_outcome": "GRANTED",
        "original_received_date": str(original["received_date_dt"].date()),
        "revised_received_date": str(revised["received_date_dt"].date()),
        "original_description": original.get("DevelopmentDescription"),
        "revised_description": revised.get("DevelopmentDescription"),
        "normalized_address": original.get("address_key"),
        "match_method": method,
        "description_similarity": round(similarity, 4),
        "confidence_same_project": round(same_site_confidence, 3),
        "confidence_change_extraction": round(change_confidence, 3),
        "units_delta": deltas.get("units", {}).get("delta"),
        "storeys_delta": deltas.get("storeys", {}).get("delta"),
        "feature_delta_json": json.dumps(deltas, sort_keys=True),
        "extracted_reason_for_refusal": original.get("reasons_joined"),
        "extracted_response_to_refusal": revised.get("fi_request_items_joined"),
        "original_source_url": original.get("LinkAppDetails") or original.get("fi_resolved_url"),
        "revised_source_url": revised.get("LinkAppDetails") or revised.get("fi_resolved_url"),
    }


def build_revision_pairs(data: pd.DataFrame, minimum_description_similarity: float = 0.30) -> pd.DataFrame:
    frame = data.copy()
    frame["case_key"] = frame["case_key"].fillna("").astype(str)
    frame["received_date_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["outcome"] = frame["Decision"].map(normalize_outcome)
    frame["authority_key"] = frame["PlanningAuthority"].fillna("").astype(str).str.strip().str.lower()
    frame["address_key"] = frame["DevelopmentAddress"].map(normalize_address)
    reference_source = frame["ApplicationNumber"] if "ApplicationNumber" in frame.columns else frame["case_key"]
    frame["application_reference_base"] = reference_source.map(base_application_reference)
    frame["is_administrative_event"] = reference_source.map(is_administrative_event_reference)
    frame = frame[frame["received_date_dt"].notna() & frame["case_key"].ne("")].copy()
    pairs: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    def add_candidates(group: pd.DataFrame, method: str) -> None:
        refusals = group[group["outcome"] == "REFUSED"]
        grants = group[group["outcome"] == "GRANTED"]
        for original, revised in product(refusals.to_dict("records"), grants.to_dict("records")):
            original, revised = pd.Series(original), pd.Series(revised)
            if revised["received_date_dt"] <= original["received_date_dt"]:
                continue
            if original["is_administrative_event"] or revised["is_administrative_event"]:
                continue
            if original["application_reference_base"] and original["application_reference_base"] == revised["application_reference_base"]:
                continue
            key = (original["case_key"], revised["case_key"])
            if key in seen:
                continue
            similarity = token_similarity(original.get("DevelopmentDescription"), revised.get("DevelopmentDescription"))
            if method == "address_description" and similarity < minimum_description_similarity:
                continue
            seen.add(key)
            pairs.append(_pair_row(original, revised, method, similarity))

    if "SiteId" in frame.columns:
        for _, group in frame[frame["SiteId"].notna()].groupby(["authority_key", "SiteId"], dropna=True):
            if len(group) > 1:
                add_candidates(group, "site_id")
    fallback = frame[frame["address_key"].str.len().ge(8) & frame["authority_key"].ne("")]
    for _, group in fallback.groupby(["authority_key", "address_key"]):
        if len(group) == MAX_ADDRESS_GROUP_SIZE:
            add_candidates(group, "address_description")
    return pd.DataFrame(pairs).sort_values(["confidence_same_project", "original_received_date"], ascending=[False, True]).reset_index(drop=True) if pairs else pd.DataFrame()
