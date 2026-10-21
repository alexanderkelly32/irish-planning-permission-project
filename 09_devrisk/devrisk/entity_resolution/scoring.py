"""Entity resolution: BCMS/PPR candidate generation and transparent scoring.

Brief section 10: generate candidates with broad cheap rules, score with
exposed features (never bury them), band into confirmed/probable/ambiguous/
rejected. Only confirmed links may enter training; probable links are for
sensitivity analysis only.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

CONFIDENCE_BANDS = ("confirmed", "probable", "ambiguous", "rejected")


def normalize_reference(value: Any) -> str:
    """Canonicalise an application reference for cross-source matching."""
    if value is None:
        return ""
    text = re.sub(r"[^a-z0-9]", "", str(value).lower())
    return text


def normalize_address(value: Any) -> str:
    """Non-destructive Irish address normalisation (token preserving)."""
    if value is None:
        return ""
    text = str(value).lower()
    text = re.sub(r"\s+", " ", text)
    text = text.replace(",", " ").replace("no.", "no ").replace("'", "")
    tokens = [token for token in text.split(" ") if token]
    return " ".join(tokens)


def address_tokens(value: str) -> set[str]:
    tokens = normalize_address(value).split(" ")
    return {token for token in tokens if len(token) >= 3}


def token_similarity(left: str, right: str) -> float:
    """Jaccard over normalised address tokens."""
    left_set = address_tokens(left)
    right_set = address_tokens(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def uncommon_place_tokens(value: str, stopwords: set[str] | None = None) -> set[str]:
    stopwords = stopwords or {
        "the", "road", "street", "avenue", "estate", "no", "number", "close", "court",
        "lane", "park", "drive", "groves", "grove", "way", "house", "houses",
        "development", "site", "lands", "townland", "co", "county",
    }
    return {token for token in address_tokens(value) if token not in stopwords}


def units_difference_abs(planning_units: Any, bcms_units: Any) -> float | None:
    left = pd.to_numeric(pd.Series([planning_units]), errors="coerce").iloc[0]
    right = pd.to_numeric(pd.Series([bcms_units]), errors="coerce").iloc[0]
    if pd.isna(left) or pd.isna(right):
        return None
    return float(abs(left - right))


def units_difference_ratio(planning_units: Any, bcms_units: Any) -> float | None:
    left = pd.to_numeric(pd.Series([planning_units]), errors="coerce").iloc[0]
    right = pd.to_numeric(pd.Series([bcms_units]), errors="coerce").iloc[0]
    if pd.isna(left) or pd.isna(right) or max(abs(left), abs(right)) == 0:
        return None
    return float(abs(left - right) / max(abs(left), abs(right)))


def distance_metres(easting1: Any, northing1: Any, easting2: Any, northing2: Any) -> float | None:
    values = pd.to_numeric(pd.Series([easting1, northing1, easting2, northing2]), errors="coerce")
    if values.isna().any():
        return None
    e1, n1, e2, n2 = values.tolist()
    return float(np.hypot(e2 - e1, n2 - n1))


def generate_bcms_candidates(
    scheme: dict[str, Any],
    bcms: pd.DataFrame,
    *,
    buffer_metres: float = 500.0,
    max_unit_ratio_diff: float = 0.5,
    county_required: bool = True,
    scheme_county: str | None = None,
) -> pd.DataFrame:
    """Broad, cheap candidate rules for one scheme against the BCMS silver frame.

    Uses only spatial proximity, unit-count tolerance, address token overlap
    and county agreement. Every candidate row keeps its source identifiers so
    scoring stays transparent. Silver columns: itm_easting/itm_northing,
    county, address_full, dwellings_total, planning_reference,
    description_raw, commencement_date_dt.
    """
    frame = bcms.copy()
    if county_required and scheme_county:
        county_col = frame["county"].fillna("").astype(str)
        frame = frame[county_col.str.lower() == str(scheme_county).lower()]
        if frame.empty:
            frame = bcms.copy()  # county may be missing in source; fall back and flag later
    if {"itm_easting", "itm_northing"}.issubset(set(frame.columns)):
        east = pd.to_numeric(frame["itm_easting"], errors="coerce")
        north = pd.to_numeric(frame["itm_northing"], errors="coerce")
        s_east = pd.to_numeric(pd.Series([scheme.get("itm_easting")]), errors="coerce").iloc[0]
        s_north = pd.to_numeric(pd.Series([scheme.get("itm_northing")]), errors="coerce").iloc[0]
        if not pd.isna(s_east) and not pd.isna(s_north):
            dist = np.hypot(east - s_east, north - s_north)
            frame = frame[dist <= buffer_metres].copy()
            frame["distance_metres"] = dist[dist <= buffer_metres].round(1)

    scheme_address = str(scheme.get("address") or "")
    if scheme_address:
        frame["address_token_similarity"] = frame.get("address_full", pd.Series("", index=frame.index)).fillna("").astype(str).map(
            lambda value: token_similarity(scheme_address, value)
        )
    scheme_units = scheme.get("units")
    if scheme_units is not None and "dwellings_total" in frame.columns:
        frame["unit_ratio_diff"] = pd.to_numeric(frame["dwellings_total"], errors="coerce").map(
            lambda value: units_difference_ratio(scheme_units, value)
        )
        frame["unit_abs_diff"] = pd.to_numeric(frame["dwellings_total"], errors="coerce").map(
            lambda value: units_difference_abs(scheme_units, value)
        )
        frame = frame[frame["unit_ratio_diff"].fillna(0.0) <= max_unit_ratio_diff]

    return frame.reset_index(drop=True)


def score_bcms_candidate(scheme: dict[str, Any], row: pd.Series) -> dict[str, Any]:
    """Exposed match features for one scheme/BCMS candidate pair (section 10.3)."""
    features: dict[str, Any] = {}
    features["distance_metres"] = row.get("distance_metres", np.nan)
    features["address_token_similarity"] = round(float(row.get("address_token_similarity", 0.0)), 4)
    scheme_address = normalize_address(scheme.get("address") or "")
    row_address = normalize_address(row.get("address_full") or row.get("Address") or "")
    features["address_token_similarity_full"] = round(token_similarity(scheme_address, row_address), 4)
    features["uncommon_place_agreement"] = int(
        bool(uncommon_place_tokens(scheme_address) & uncommon_place_tokens(row_address))
    )
    features["unit_abs_diff"] = None if pd.isna(row.get("unit_abs_diff", np.nan)) else float(row["unit_abs_diff"])
    features["unit_ratio_diff"] = None if pd.isna(row.get("unit_ratio_diff", np.nan)) else float(row["unit_ratio_diff"])
    row_reference = row.get("planning_reference") or row.get("CN_Commencement_Notice_No") or ""
    features["exact_reference_match"] = int(
        bool(scheme.get("application_reference"))
        and normalize_reference(scheme.get("application_reference"))
        and normalize_reference(scheme.get("application_reference")) in normalize_reference(row_reference)
    )
    features["county_match"] = int(
        str(scheme.get("county") or "").lower() == str(row.get("county") or row.get("County") or "").lower()
    )
    description = row.get("description_raw") or row.get("CN_Main_Works") or ""
    features["planning_reference_in_text"] = int(
        bool(scheme.get("application_reference"))
        and str(scheme.get("application_reference"))[:4].lower()
        in str(description).lower()
    )
    return features


def confidence_band(features: dict[str, Any], thresholds: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    """Transparent confidence banding from exposed match features.

    thresholds (defaults):
      confirmed: exact reference match, or (distance <= 250m AND uncommon
                 place-name agreement AND unit_ratio_diff <= 0.25)
      probable:  distance <= 500m AND address_token_similarity >= 0.4, no
                 material conflicts
      ambiguous: anything plausible remaining
      rejected:  hard conflicts (county mismatch + no textual link, or
                 impossible chronology)

    Returns (band, reasons). Reason list is kept for the audit workbook.
    """
    thresholds = thresholds or {}
    confirmed = thresholds.get(
        "confirmed",
        {"max_distance": 250.0, "max_unit_ratio_diff": 0.25, "require_place_agreement": True},
    )
    probable = thresholds.get(
        "probable",
        {"max_distance": 500.0, "min_token_similarity": 0.4},
    )
    distance = features.get("distance_metres")
    unit_ratio = features.get("unit_ratio_diff")
    token_sim = features.get("address_token_similarity_full", 0.0) or 0.0
    reasons: list[str] = []

    if features.get("county_match") == 0 and not features.get("planning_reference_in_text") and not features.get("exact_reference_match"):
        return "rejected", ["county mismatch without textual link"]
    if features.get("exact_reference_match"):
        return "confirmed", ["exact reference match"]
    if (
        distance is not None
        and not pd.isna(distance)
        and float(distance) <= confirmed["max_distance"]
        and unit_ratio is not None
        and unit_ratio <= confirmed["max_unit_ratio_diff"]
        and features.get("uncommon_place_agreement")
    ):
        return "confirmed", ["close distance", "unit agreement", "uncommon place-name agreement"]
    if distance is not None and not pd.isna(distance) and float(distance) <= probable["max_distance"] and token_sim >= probable["min_token_similarity"]:
        return "probable", ["distance within buffer", "address token similarity"]
    if distance is not None and not pd.isna(distance):
        reasons.append("distance only within buffer")
    if unit_ratio is not None and unit_ratio <= 0.5:
        reasons.append("unit count compatible")
    if features.get("uncommon_place_agreement"):
        reasons.append("place-name agreement without other support")
    if reasons:
        return "ambiguous", reasons
    return "rejected", ["no supporting signal"]
