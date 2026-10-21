"""Comparable-case evidence for a proposed scenario, separate from model scoring."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from find_similar_developments import build_query_frame, find_similar_to_query, transform_rows
from precedent_copilot_logic import clean_text, normalize_cases, normalize_decision, rerank_candidates, weighted_theme_summary
from prediction_service import build_model_query
from refusal_theme_aggregation import (
    aggregate_refusal_themes_sourced,
    refusal_theme_coverage_note as build_refusal_theme_coverage_note,
)

FIELD_TO_STRUCTURED_DELTA = {
    "units": "units_total_best",
    "max_storeys": "max_storeys_best",
    "site_area_sqm": "site_area_sqm_best",
    "total_gfa_sqm": "floor_area_sqm_best",
    "private_open_space_sqm": "open_space_sqm_best",
    "communal_open_space_sqm": "open_space_sqm_best",
    "parking_spaces": "parking_spaces_best",
}
ANNOTATION_COLUMN_TO_FIELD = {
    "observed_units_delta": "units",
    "observed_storeys_delta": "max_storeys",
    "observed_site_area_sqm_delta": "site_area_sqm",
    "observed_floor_area_sqm_delta": "total_gfa_sqm",
    "observed_open_space_sqm_delta": "communal_open_space_sqm",
    "observed_parking_spaces_delta": "parking_spaces",
}


SCENARIO_FIELD_CHANGE_CATEGORIES = {
    "units": {"layout_design"},
    "max_storeys": {"layout_design"},
    "max_height_m": {"layout_design"},
    "density_units_per_ha": {"layout_design"},
    "plot_ratio": {"layout_design"},
    "site_coverage_pct": {"layout_design"},
    "front_setback_m": {"layout_design"},
    "rear_setback_m": {"layout_design"},
    "side_setback_m": {"layout_design"},
    "upper_floor_setback_m": {"layout_design"},
    "nearest_dwelling_separation_m": {"layout_design"},
    "opposing_window_separation_m": {"layout_design"},
    "total_gfa_sqm": {"layout_design"},
    "unit_mix": {"layout_design"},
    "housing_type": {"layout_design"},
    "parking_spaces": {"access_parking"},
    "bicycle_spaces": {"access_parking"},
    "vehicular_access_points": {"access_parking"},
    "private_open_space_sqm": {"open_space_amenity"},
    "communal_open_space_sqm": {"open_space_amenity"},
    "development_type": {"policy_land_use"},
    "proposal_type": {"policy_land_use"},
    "demolition_proposed": {"policy_land_use"},
}
OBSERVED_DELTA_COLUMNS = {
    "units": "observed_units_delta",
    "max_storeys": "observed_storeys_delta",
    "site_area_sqm": "observed_site_area_sqm_delta",
    "total_gfa_sqm": "observed_floor_area_sqm_delta",
    "private_open_space_sqm": "observed_open_space_sqm_delta",
    "communal_open_space_sqm": "observed_open_space_sqm_delta",
    "parking_spaces": "observed_parking_spaces_delta",
}


def build_scenario_evidence_query(site: dict[str, Any], scheme: dict[str, Any]) -> dict[str, Any]:
    """Use the same submission-time allowlist as scoring for comparable retrieval."""
    return build_model_query(site, scheme)


def select_revision_evidence_for_changes(
    evidence: pd.DataFrame,
    changed_fields: list[str] | tuple[str, ...] | set[str],
) -> pd.DataFrame:
    """Select audited revision evidence matching the categories changed by a scenario."""
    categories = sorted({
        category
        for field in changed_fields
        for category in SCENARIO_FIELD_CHANGE_CATEGORIES.get(field, set())
    })
    if evidence.empty or not categories:
        return evidence.iloc[0:0].copy()
    selected = evidence.copy()
    matched: list[str] = []
    keep: list[bool] = []
    for _, row in selected.iterrows():
        row_categories = [category for category in categories if bool(row.get(f"change_{category}", False))]
        matched.append(";".join(row_categories))
        keep.append(bool(row_categories))
    selected["matched_change_categories"] = matched
    selected = selected.loc[keep].copy()
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    selected["_confidence_order"] = selected.get("annotation_confidence", "").map(confidence_order).fillna(3)
    return selected.sort_values(["_confidence_order", "original_case_key"]).drop(columns="_confidence_order").reset_index(drop=True)


def summarize_revision_evidence_for_changes(
    evidence: pd.DataFrame,
    changed_fields: list[str] | tuple[str, ...] | set[str],
    limit: int = 3,
    scenario_delta: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build display-safe records from audited revision evidence for a scenario."""
    selected = select_revision_evidence_for_changes(evidence, changed_fields)
    scenario_delta = scenario_delta or {}
    direction_details: list[tuple[list[str], list[str]]] = []
    for _, row in selected.iterrows():
        matches: list[str] = []
        mismatches: list[str] = []
        for field, delta in scenario_delta.items():
            observed_column = OBSERVED_DELTA_COLUMNS.get(field)
            if not observed_column or observed_column not in selected.columns:
                continue
            try:
                scenario_change = float(delta.get("to")) - float(delta.get("from"))
                observed_change = float(row.get(observed_column))
            except (TypeError, ValueError):
                continue
            if pd.isna(observed_change) or scenario_change == 0:
                continue
            if (scenario_change > 0) == (observed_change > 0):
                matches.append(field)
            else:
                mismatches.append(field)
        direction_details.append((matches, mismatches))
    if len(selected):
        selected["_direction_matches"] = [len(matches) for matches, _ in direction_details]
        selected["_direction_mismatches"] = [len(mismatches) for _, mismatches in direction_details]
        selected["_direction_match_fields"] = [matches for matches, _ in direction_details]
        selected["_direction_mismatch_fields"] = [mismatches for _, mismatches in direction_details]
        confidence_order = {"high": 0, "medium": 1, "low": 2}
        selected["_confidence_order"] = selected.get("annotation_confidence", "").map(confidence_order).fillna(3)
        selected = selected.sort_values(
            ["_direction_matches", "_direction_mismatches", "_confidence_order", "original_case_key"],
            ascending=[False, True, True, True],
        ).reset_index(drop=True)
    cases: list[dict[str, object]] = []
    for _, row in selected.head(max(0, limit)).iterrows():
        cases.append({
            "original_case_key": clean_text(row.get("original_case_key")),
            "revised_case_key": clean_text(row.get("revised_case_key")),
            "original_source_url": clean_text(row.get("original_source_url")),
            "revised_source_url": clean_text(row.get("revised_source_url")),
            "source_backed_change_note": clean_text(row.get("source_backed_change_note")),
            "annotation_confidence": clean_text(row.get("annotation_confidence")),
            "evidence_scope": clean_text(row.get("evidence_scope")),
            "matched_change_categories": [
                category for category in clean_text(row.get("matched_change_categories")).split(";") if category
            ],
            "direction_match_fields": list(row.get("_direction_match_fields", [])),
            "direction_mismatch_fields": list(row.get("_direction_mismatch_fields", [])),
        })
    return {
        "matching_pair_count": int(len(selected)),
        "cases": cases,
        "disclaimer": (
            "These are manually audited refused-to-revised-to-granted examples with a related change category. "
            "Their later grant does not prove that the observed change caused permission."
        ),
    }


def summarize_canonical_revision_evidence(
    records: pd.DataFrame,
    changed_fields: list[str] | tuple[str, ...] | set[str],
    scenario_delta: dict[str, dict[str, object]] | None = None,
    limit: int = 3,
) -> dict[str, object]:
    """Aggregate observed change statistics over the audited canonical revision pairs.

    Statistics describe what audited resubmissions actually changed before their
    later grant; they are association evidence, never proof of causation.
    """
    scenario_delta = scenario_delta or {}
    if records is None or records.empty:
        return {"pair_count": 0, "field_groups": [], "disclaimer": ""}
    disclaimer = (
        "Statistics are computed over manually audited refused-to-revised-to-granted pairs. "
        "An observed change is associated with a later grant; it does not prove that the "
        "change caused permission."
    )
    field_groups: list[dict[str, object]] = []
    for field in sorted(set(changed_fields)):
        structured_field = FIELD_TO_STRUCTURED_DELTA.get(field)
        matched: list[dict[str, object]] = []
        for _, row in records.iterrows():
            try:
                deltas = json.loads(row.get("feature_delta_json") or "{}")
            except (TypeError, ValueError):
                deltas = {}
            observed = None
            if structured_field and structured_field in deltas:
                observed = float(deltas[structured_field]["delta"])
            else:
                try:
                    annotation_deltas = json.loads(row.get("annotation_observed_delta_json") or "{}")
                except (TypeError, ValueError):
                    annotation_deltas = {}
                for annotated_column, annotated_delta in annotation_deltas.items():
                    if ANNOTATION_COLUMN_TO_FIELD.get(annotated_column) == field:
                        observed = float(annotated_delta)
                        break
            if observed is None:
                continue
            citation = " ".join(
                part for part in [
                    clean_text(row.get("planning_authority")),
                    clean_text(row.get("revised_case_key")),
                ] if part
            )
            matched.append({
                "original_case_key": clean_text(row.get("original_case_key")),
                "revised_case_key": clean_text(row.get("revised_case_key")),
                "citation": citation,
                "observed_delta": observed,
                "refusal_themes": clean_text(row.get("refusal_themes_original")),
                "annotation_confidence": clean_text(row.get("annotation_confidence")),
                "source_backed_change_note": clean_text(row.get("source_backed_change_note")),
                "linkage_tier": clean_text(row.get("linkage_tier")),
                "original_source_url": clean_text(row.get("original_source_url")),
                "revised_source_url": clean_text(row.get("revised_source_url")),
            })
        if not matched:
            field_groups.append({
                "field": field,
                "matched_count": 0,
                "same_direction_count": 0,
                "median_delta": None,
                "examples": [],
                "note": "No audited revision pair has an observed structured delta for this field.",
            })
            continue
        scenario_change = None
        scenario_entry = scenario_delta.get(field)
        if scenario_entry is not None:
            try:
                scenario_change = float(scenario_entry.get("to")) - float(scenario_entry.get("from"))
            except (TypeError, ValueError):
                scenario_change = None
        same_direction = [
            record for record in matched
            if scenario_change is None or (scenario_change != 0 and (record["observed_delta"] > 0) == (scenario_change > 0))
        ]
        if scenario_change is not None and scenario_change != 0:
            same_direction.sort(key=lambda record: abs(record["observed_delta"] - scenario_change))
        else:
            same_direction.sort(key=lambda record: -abs(record["observed_delta"]))
        deltas = [record["observed_delta"] for record in matched]
        field_groups.append({
            "field": field,
            "matched_count": len(matched),
            "same_direction_count": len(same_direction),
            "median_delta": round(float(pd.Series(deltas).median()), 2),
            "examples": same_direction[:limit],
            "note": (
                f"{len(same_direction)} audited pairs changed {field} in the same direction as this "
                f"scenario; median observed delta {round(float(pd.Series(deltas).median()), 2)}."
            ) if matched else "",
        })
    return {
        "pair_count": int(len(records)),
        "field_groups": field_groups,
        "disclaimer": disclaimer,
    }


def summarize_scenario_evidence(
    ranked: pd.DataFrame,
    top_k: int = 8,
    refusal_index: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Return auditable, compact evidence; never infer a recommendation from outcomes."""
    selected = ranked.head(max(0, top_k)).copy()
    if selected.empty:
        return {
            "comparable_count": 0,
            "outcome_mix": {"granted": 0, "refused": 0, "other": 0},
            "refusal_themes": [],
            "refusal_theme_coverage_note": "",
            "top_comparables": [],
        }

    decisions = selected.get("decision_normalized", selected.get("Decision", "")).map(normalize_decision)
    outcome_mix = {
        "granted": int(decisions.eq("GRANTED").sum()),
        "refused": int(decisions.eq("REFUSED").sum()),
        "other": int((~decisions.isin(["GRANTED", "REFUSED"])).sum()),
    }
    refused = selected[decisions.eq("REFUSED")]
    if refusal_index is not None:
        aggregation = aggregate_refusal_themes_sourced(refused, refusal_index, limit=4)
        refusal_themes = aggregation["themes"]
        refusal_theme_coverage_note = build_refusal_theme_coverage_note(aggregation)
    else:
        refusal_themes = weighted_theme_summary(refused)
        refusal_theme_coverage_note = ""
    case_columns = [
        "case_key", "PlanningAuthority", "ApplicationNumber", "Decision",
        "hybrid_score", "similarity", "match_reasons", "source_url",
    ]
    top_comparables: list[dict[str, object]] = []
    for _, row in selected.iterrows():
        case = {column: row.get(column) for column in case_columns if column in selected.columns}
        case["citation"] = " ".join(
            part for part in [
                clean_text(row.get("PlanningAuthority")),
                clean_text(row.get("ApplicationNumber")),
                f"({clean_text(row.get('Decision'))})" if clean_text(row.get("Decision")) else "",
            ] if part
        )
        top_comparables.append(case)
    return {
        "comparable_count": int(len(selected)),
        "outcome_mix": outcome_mix,
        "refusal_themes": refusal_themes,
        "refusal_theme_coverage_note": refusal_theme_coverage_note,
        "top_comparables": top_comparables,
    }


def retrieve_scenario_evidence(
    cases: pd.DataFrame,
    artifacts: Any,
    case_matrix: Any,
    site: dict[str, Any],
    scheme: dict[str, Any],
    top_k: int = 8,
    refusal_index: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Retrieve and re-rank precedent cases for the exact mutated scheme snapshot."""
    query = build_scenario_evidence_query(site, scheme)
    prepared_cases = cases.copy()
    for column, default in {
        "reason_count": 0,
        "fi_request_items_count": 0,
        "max_storeys_best": None,
        "site_area_ha_best": None,
        "ITMEasting": None,
        "ITMNorthing": None,
        "fi_resolved_url": "",
        "LinkAppDetails": "",
        "reasons_joined": "",
        "fi_request_items_joined": "",
        "extraction_source": "",
        "extraction_method": "",
        "fi_request_extraction_status": "",
    }.items():
        if column not in prepared_cases:
            prepared_cases[column] = default
    normalized_cases = normalize_cases(prepared_cases)
    query_frame = build_query_frame(normalized_cases, **query)
    candidates = find_similar_to_query(
        normalized_cases,
        case_matrix,
        transform_rows(query_frame, artifacts),
        top_k=max(top_k * 6, 120),
    )
    ranked = rerank_candidates(candidates, query)
    selected = ranked.head(top_k).copy()
    return {
        "query": query,
        "ranked": selected,
        "summary": summarize_scenario_evidence(selected, top_k=top_k, refusal_index=refusal_index),
    }
