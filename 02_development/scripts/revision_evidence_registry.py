"""Create an evidence-only annotation registry from manually accepted revision pairs."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from revision_change_cues import extract_review_cues


CHANGE_COLUMNS = [
    "change_layout_design",
    "change_access_parking",
    "change_open_space_amenity",
    "change_drainage_environment",
    "change_policy_land_use",
]
COMPLETED_ANNOTATION_COLUMNS = {
    "original_case_key",
    "revised_case_key",
    "annotation_status",
    "addressed_refusal_theme",
    "source_backed_change_note",
    "annotation_confidence",
    *CHANGE_COLUMNS,
}


def _observed_delta(value: object, field: str) -> float | None:
    try:
        payload = json.loads(str(value or "{}"))
        delta = payload.get(field, {}).get("delta")
        return float(delta) if delta is not None else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def build_revision_evidence_registry(accepted: pd.DataFrame) -> pd.DataFrame:
    """Make missing extraction explicit; no inferred physical intervention is created."""
    required = {"original_case_key", "revised_case_key", "feature_delta_json"}
    missing = required - set(accepted.columns)
    if missing:
        raise ValueError(f"accepted pairs missing columns: {sorted(missing)}")
    rows: list[dict[str, object]] = []
    for _, pair in accepted.iterrows():
        reason = str(pair.get("extracted_reason_for_refusal") or "").strip()
        rows.append({
            "original_case_key": pair["original_case_key"],
            "revised_case_key": pair["revised_case_key"],
            "original_source_url": pair.get("original_source_url", ""),
            "revised_source_url": pair.get("revised_source_url", ""),
            "original_description": pair.get("original_description", ""),
            "revised_description": pair.get("revised_description", ""),
            "extracted_refusal_reason": reason,
            "annotation_status": "needs_change_annotation",
            "observed_units_delta": _observed_delta(pair["feature_delta_json"], "units"),
            "observed_storeys_delta": _observed_delta(pair["feature_delta_json"], "storeys"),
            "observed_site_area_sqm_delta": _observed_delta(pair["feature_delta_json"], "site_area_sqm"),
            "observed_floor_area_sqm_delta": _observed_delta(pair["feature_delta_json"], "floor_area_sqm"),
            "observed_open_space_sqm_delta": _observed_delta(pair["feature_delta_json"], "open_space_sqm"),
            "observed_parking_spaces_delta": _observed_delta(pair["feature_delta_json"], "parking_spaces"),
            "refusal_reason_available": bool(reason),
            "automated_review_cues": ";".join(extract_review_cues(
                pair.get("original_description"), pair.get("revised_description"), reason
            )),
            "addressed_refusal_theme": "",
            "change_layout_design": "",
            "change_access_parking": "",
            "change_open_space_amenity": "",
            "change_drainage_environment": "",
            "change_policy_land_use": "",
            "source_backed_change_note": "",
            "annotation_confidence": "",
        })
    return pd.DataFrame(rows)


def summarize_observed_deltas(registry: pd.DataFrame) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for field, column in {"units": "observed_units_delta", "storeys": "observed_storeys_delta"}.items():
        values = pd.to_numeric(registry.get(column), errors="coerce")
        observed = values.notna()
        result[field] = {
            "observed_pairs": int(observed.sum()),
            "decreased": int((values[observed] < 0).sum()),
            "unchanged": int((values[observed] == 0).sum()),
            "increased": int((values[observed] > 0).sum()),
        }
    return result


def _annotation_boolean(value: object, column: str) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"{column} must contain only true/false values")


def validate_completed_annotations(annotations: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a human-completed evidence registry."""
    missing = COMPLETED_ANNOTATION_COLUMNS - set(annotations.columns)
    if missing:
        raise ValueError(f"completed annotations missing columns: {sorted(missing)}")
    validated = annotations.copy()
    if validated.duplicated(["original_case_key", "revised_case_key"]).any():
        raise ValueError("completed annotations contain duplicate revision pairs")

    for column in ["annotation_status", "addressed_refusal_theme", "annotation_confidence"]:
        validated[column] = validated[column].fillna("").astype(str).str.strip().str.lower()
    if set(validated["annotation_status"]) != {"annotated"}:
        raise ValueError("annotation_status must be annotated for every completed row")
    invalid_relationships = sorted(set(validated["addressed_refusal_theme"]) - {"yes", "partial", "unclear"})
    if invalid_relationships:
        raise ValueError(f"unsupported addressed_refusal_theme values: {invalid_relationships}")
    invalid_confidence = sorted(set(validated["annotation_confidence"]) - {"high", "medium", "low"})
    if invalid_confidence:
        raise ValueError(f"unsupported annotation_confidence values: {invalid_confidence}")
    validated["source_backed_change_note"] = validated["source_backed_change_note"].fillna("").astype(str).str.strip()
    if validated["source_backed_change_note"].eq("").any():
        raise ValueError("source_backed_change_note is required for every completed annotation")
    for column in CHANGE_COLUMNS:
        validated[column] = validated[column].map(lambda value: _annotation_boolean(value, column))
    return validated


def build_revision_intervention_evidence(annotations: pd.DataFrame) -> pd.DataFrame:
    """Export only source-backed changes that may support scenario sensitivity context."""
    validated = validate_completed_annotations(annotations)
    supported = validated["addressed_refusal_theme"].isin(["yes", "partial"])
    has_observed_change = validated[CHANGE_COLUMNS].any(axis=1)
    evidence = validated.loc[supported & has_observed_change].copy()
    evidence["evidence_scope"] = evidence["addressed_refusal_theme"].map({
        "yes": "source_supported_change",
        "partial": "partial_support",
    })
    return evidence.reset_index(drop=True)


def summarize_completed_annotations(annotations: pd.DataFrame) -> dict[str, object]:
    """Report annotation coverage without treating unclear links as intervention evidence."""
    validated = validate_completed_annotations(annotations)
    intervention = build_revision_intervention_evidence(validated)
    relationship_counts = validated["addressed_refusal_theme"].value_counts().to_dict()
    confidence_counts = validated["annotation_confidence"].value_counts().to_dict()
    change_counts = {column.removeprefix("change_"): int(validated[column].sum()) for column in CHANGE_COLUMNS}
    return {
        "annotated_pair_count": int(len(validated)),
        "intervention_evidence_pair_count": int(len(intervention)),
        "context_only_pair_count": int(len(validated) - len(intervention)),
        "addressed_refusal_theme_counts": {key: int(value) for key, value in relationship_counts.items()},
        "confidence_counts": {key: int(value) for key, value in confidence_counts.items()},
        "observed_change_category_counts": change_counts,
        "status": "sensitivity_evidence_only_not_causal",
    }
