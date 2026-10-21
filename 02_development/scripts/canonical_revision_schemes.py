"""Canonical Scheme records for audited refused-to-revised-to-granted pairs."""
from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

SCHEME_FIELDS = [
    "units_total_best",
    "max_storeys_best",
    "site_area_sqm_best",
    "floor_area_sqm_best",
    "open_space_sqm_best",
    "parking_spaces_best",
    "cycle_parking_spaces_best",
]
DELTA_COLUMNS = {
    "units_total_best": "observed_units_delta",
    "max_storeys_best": "observed_storeys_delta",
    "site_area_sqm_best": "observed_site_area_sqm_delta",
    "floor_area_sqm_best": "observed_floor_area_sqm_delta",
    "open_space_sqm_best": "observed_open_space_sqm_delta",
    "parking_spaces_best": "observed_parking_spaces_delta",
}
PAIR_EXTRACTION_FIELD_MAP = {
    "max_storeys": "max_storeys_best",
    "parking_spaces": "parking_spaces_best",
    "cycle_parking_spaces": "cycle_parking_spaces_best",
    "open_space_sqm": "open_space_sqm_best",
    "max_height_m": "max_height_m",
    "vehicular_access_points": "vehicular_access_points",
    "nearest_dwelling_separation_m": "nearest_dwelling_separation_m",
    "opposing_window_separation_m": "opposing_window_separation_m",
    "communal_open_space_sqm": "communal_open_space_sqm",
}
REQUIRED_PAIR_COLUMNS = {
    "original_case_key",
    "revised_case_key",
    "manual_review_status",
    "original_received_date",
    "revised_received_date",
    "linkage_tier",
}


def normalize_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if pd.notna(parsed) else None


def scheme_id(case_key: object) -> str:
    return f"scheme_{normalize_key(case_key)}"


def load_accepted_pairs(queue: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_PAIR_COLUMNS.difference(queue.columns)
    if missing:
        raise ValueError(f"queue is missing columns: {', '.join(sorted(missing))}")
    return queue[queue["manual_review_status"].fillna("").astype(str).str.strip().str.lower() == "accepted"].copy()


def structured_lookup(structured: pd.DataFrame) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for _, row in structured.iterrows():
        key = normalize_key(row.get("case_key"))
        if not key:
            continue
        lookup[key] = {
            field: _number(row.get(field))
            for field in SCHEME_FIELDS
            if field in structured.columns
        }
    return lookup


def build_pair_deltas(original: dict[str, Any], revised: dict[str, Any]) -> dict[str, dict[str, float]]:
    deltas: dict[str, dict[str, float]] = {}
    for field in SCHEME_FIELDS:
        before = original.get(field)
        after = revised.get(field)
        if before is not None and after is not None:
            deltas[field] = {"from": before, "to": after, "delta": round(after - before, 6)}
    return deltas


def annotation_lookup(annotations: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if annotations is None or annotations.empty:
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for _, row in annotations.iterrows():
        key = (
            normalize_key(row.get("original_case_key")),
            normalize_key(row.get("revised_case_key")),
        )
        lookup[key] = {
            "extracted_refusal_reason": str(row.get("extracted_refusal_reason") or ""),
            "addressed_refusal_theme": str(row.get("addressed_refusal_theme") or ""),
            "source_backed_change_note": str(row.get("source_backed_change_note") or ""),
            "annotation_confidence": str(row.get("annotation_confidence") or ""),
            "observed_deltas": {
                field: _number(row.get(column))
                for field, column in DELTA_COLUMNS.items()
                if column in annotations.columns and pd.notna(row.get(column))
            },
        }
    return lookup


def refusal_theme_lookup(refusal_master: pd.DataFrame | None) -> dict[str, str]:
    if refusal_master is None or refusal_master.empty or "case_key" not in refusal_master.columns:
        return {}
    lookup: dict[str, str] = {}
    for _, row in refusal_master.iterrows():
        key = normalize_key(row.get("case_key"))
        tags = str(row.get("case_primary_tags") or row.get("case_top_primary_tag") or "")
        if key and tags:
            lookup[key] = tags
    return lookup


def pair_extraction_lookup(extractions: pd.DataFrame | None) -> dict[tuple[str, str], dict[str, dict[str, float]]]:
    """Deltas from the two-sided description extraction, keyed by (original, revised)."""
    if extractions is None or extractions.empty:
        return {}
    lookup: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    for _, row in extractions.iterrows():
        key = (
            normalize_key(row.get("original_case_key")),
            normalize_key(row.get("revised_case_key")),
        )
        if not key[0] or not key[1]:
            continue
        deltas: dict[str, dict[str, float]] = {}
        for field, column in PAIR_EXTRACTION_FIELD_MAP.items():
            before = _number(row.get(f"original_{field}"))
            after = _number(row.get(f"revised_{field}"))
            if before is not None and after is not None and before != after:
                deltas[column] = {"from": before, "to": after, "delta": round(after - before, 6)}
        if deltas:
            existing = lookup.get(key, {})
            existing.update(deltas)
            lookup[key] = existing
    return lookup


def build_canonical_records(
    accepted: pd.DataFrame,
    structured: pd.DataFrame,
    refusal_master: pd.DataFrame | None = None,
    annotations: pd.DataFrame | None = None,
    pair_extractions: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Build one canonical record per accepted pair; never fabricate deltas.

    Deltas come from the structured extraction (first), then from the two-sided
    description extraction where the structured source had no value; the
    annotation registry provides verified change notes.
    """
    structured_rows = structured_lookup(structured)
    annotation_rows = annotation_lookup(annotations)
    refusal_themes = refusal_theme_lookup(refusal_master)
    pair_rows = pair_extraction_lookup(pair_extractions)
    records: list[dict[str, Any]] = []
    for _, pair in accepted.iterrows():
        original_key = normalize_key(pair.get("original_case_key"))
        revised_key = normalize_key(pair.get("revised_case_key"))
        original_fields = structured_rows.get(original_key, {})
        revised_fields = structured_rows.get(revised_key, {})
        structured_deltas = build_pair_deltas(original_fields, revised_fields)
        pair_deltas = pair_rows.get((original_key, revised_key), {})
        for column, delta in pair_deltas.items():
            if column not in structured_deltas:
                structured_deltas[column] = delta
        annotation = annotation_rows.get((original_key, revised_key), {})
        annotation_deltas = annotation.get("observed_deltas", {})
        structured_observed = len(structured_deltas)
        annotation_verified = bool(annotation)
        confidence_change_extraction = (
            "annotation_verified" if annotation_verified else
            "structured_observed" if structured_observed else
            "description_only"
        )
        records.append({
            "original_scheme_id": scheme_id(pair.get("original_case_key")),
            "revised_scheme_id": scheme_id(pair.get("revised_case_key")),
            "original_case_key": str(pair.get("original_case_key") or ""),
            "revised_case_key": str(pair.get("revised_case_key") or ""),
            "planning_authority": str(pair.get("planning_authority") or ""),
            "original_received_date": str(pair.get("original_received_date") or ""),
            "revised_received_date": str(pair.get("revised_received_date") or ""),
            "gap_days": _number(pair.get("gap_days")),
            "original_outcome": "REFUSED",
            "revised_outcome": "GRANTED",
            "linkage_tier": str(pair.get("linkage_tier") or ""),
            "feature_delta_json": json.dumps(structured_deltas, sort_keys=True),
            "refusal_themes_original": refusal_themes.get(original_key, ""),
            "structured_fields_observed": structured_observed,
            "extracted_refusal_reason": annotation.get("extracted_refusal_reason", ""),
            "addressed_refusal_theme": annotation.get("addressed_refusal_theme", ""),
            "annotation_confidence": annotation.get("annotation_confidence", ""),
            "source_backed_change_note": annotation.get("source_backed_change_note", ""),
            "annotation_observed_delta_json": json.dumps(annotation_deltas, sort_keys=True),
            "original_source_url": str(pair.get("original_source_url") or ""),
            "revised_source_url": str(pair.get("revised_source_url") or ""),
            "confidence_same_project": "audited_accepted",
            "confidence_change_extraction": confidence_change_extraction,
        })
    return records


def build_delta_rows(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        structured = json.loads(record["feature_delta_json"])
        for field, delta in structured.items():
            rows.append({
                "original_scheme_id": record["original_scheme_id"],
                "revised_scheme_id": record["revised_scheme_id"],
                "field": field,
                "original_value": delta["from"],
                "revised_value": delta["to"],
                "delta": delta["delta"],
                "source": "structured",
            })
        annotated = json.loads(record["annotation_observed_delta_json"])
        for field, delta in annotated.items():
            rows.append({
                "original_scheme_id": record["original_scheme_id"],
                "revised_scheme_id": record["revised_scheme_id"],
                "field": field,
                "original_value": None,
                "revised_value": None,
                "delta": delta,
                "source": "annotation_registry",
            })
    return pd.DataFrame(rows)


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"pair_count": 0}
    frame = pd.DataFrame(records)
    structured_counts: dict[str, int] = {}
    for record in records:
        for field in json.loads(record["feature_delta_json"]):
            structured_counts[field] = structured_counts.get(field, 0) + 1
    return {
        "pair_count": int(len(records)),
        "by_tier": frame["linkage_tier"].value_counts().to_dict(),
        "with_structured_deltas": int((frame["structured_fields_observed"] > 0).sum()),
        "structured_delta_field_counts": structured_counts,
        "annotation_verified": int((frame["confidence_change_extraction"] == "annotation_verified").sum()),
        "with_refusal_themes": int(frame["refusal_themes_original"].fillna("").astype(str).str.strip().ne("").sum()),
        "caveat": (
            "Deltas are recorded only where both sides were observed in the structured extraction "
            "or in the audited annotation registry. Missing fields are never zero-filled."
        ),
    }
