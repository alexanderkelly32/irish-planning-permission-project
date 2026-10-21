"""Evidence-graded recommendations for scenario changes (brief section 11).

Grades combine three independent signals, none of which is causal on its own:
- model movement (sensitivity analysis, holding other inputs constant)
- matched audited revision evidence (refused -> revised -> granted pairs)
- precedent/policy support (comparables and verified plan standards)

The UI must always render these as "modelled scenario" statements, never as
guaranteed causal effects.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

GRADE_ORDER = {"strong": 0, "moderate": 1, "weak": 2}

MIN_MODEL_MOVEMENT_PP = 2.0
MIN_REVISION_PAIRS_FOR_STRONG = 2
MIN_REVISION_PAIRS_FOR_MODERATE = 1

FIELD_TO_BAND = {
    "max_storeys": "max_storeys",
    "units": "units",
    "parking_spaces": "parking_spaces",
}

STRUCTURED_TO_SCHEME_FIELD = {
    "units_total_best": "units",
    "max_storeys_best": "max_storeys",
    "site_area_sqm_best": "site_area_sqm",
    "floor_area_sqm_best": "total_gfa_sqm",
    "open_space_sqm_best": "private_open_space_sqm",
    "parking_spaces_best": "parking_spaces",
    "cycle_parking_spaces_best": "bicycle_spaces",
    "max_height_m": "max_height_m",
    "vehicular_access_points": "vehicular_access_points",
    "nearest_dwelling_separation_m": "nearest_dwelling_separation_m",
    "opposing_window_separation_m": "opposing_window_separation_m",
    "communal_open_space_sqm": "communal_open_space_sqm",
}

MATERIAL_MAGNITUDE = {
    "units_total_best": 3.0,
    "max_storeys_best": 1.0,
    "parking_spaces_best": 2.0,
    "cycle_parking_spaces_best": 2.0,
    "open_space_sqm_best": 10.0,
    "site_area_sqm_best": 10.0,
    "floor_area_sqm_best": 20.0,
    "max_height_m": 1.0,
    "vehicular_access_points": 1.0,
    "nearest_dwelling_separation_m": 1.0,
    "opposing_window_separation_m": 1.0,
    "communal_open_space_sqm": 10.0,
}


def band_for_value(rates: dict[str, Any], field: str, value: object) -> str | None:
    """Find the cohort outcome-rate band containing a lever value."""
    if field not in FIELD_TO_BAND or not rates:
        return None
    numeric = _numeric(value)
    if numeric is None:
        return None
    bands = rates.get(FIELD_TO_BAND[field], [])
    for band in bands:
        label = band["band"]
        if "+" in label:
            low = float(label.replace("+", ""))
            if numeric >= low:
                return label
        elif "-" in label:
            low, high = label.split("-")
            if float(low) <= numeric <= float(high):
                return label
        else:
            if numeric == float(label):
                return label
    return None


def observed_rate_contrast(rates: dict[str, Any], field: str, from_value: object, to_value: object) -> str | None:
    """Render the observational before/after cohort-rate contrast for a lever change."""
    if not rates or field not in FIELD_TO_BAND:
        return None
    from_band = band_for_value(rates, field, from_value)
    to_band = band_for_value(rates, field, to_value)
    if from_band is None or to_band is None or from_band == to_band:
        return None
    bands = rates[FIELD_TO_BAND[field]]
    from_row = next((band for band in bands if band["band"] == from_band), None)
    to_row = next((band for band in bands if band["band"] == to_band), None)
    if not from_row or not to_row:
        return None
    return (
        f"Observed cohort rates: schemes like this at {to_band} were granted "
        f"{to_row['observed_grant_rate'] * 100:.1f}% of the time (n={to_row['cases']}) vs "
        f"{from_row['observed_grant_rate'] * 100:.1f}% at {from_band} (n={from_row['cases']}). "
        f"Observational, not causal - scheme mix differs between bands."
    )


def _numeric(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def direction_label(field: str, from_value: object, to_value: object) -> str:
    before = _numeric(from_value)
    after = _numeric(to_value)
    if before is None or after is None:
        return "changed"
    if after > before:
        return "increase"
    if after < before:
        return "reduce"
    return "unchanged"


def most_common_change_ranking(
    records: pd.DataFrame,
    material_magnitudes: dict[str, float] | None = None,
    exclude_case_keys: set[str] | frozenset[str] = frozenset(),
) -> list[tuple[str, str, int, int]]:
    """Empirically most-common scheme changes across canonical revision records.

    Returns (field, majority_direction, majority_count, total_count) entries sorted
    by total count. Only material deltas (>= threshold) count, mirroring the blind
    backtest. Pass ``exclude_case_keys`` for leave-one-out use.
    """
    magnitudes = material_magnitudes or MATERIAL_MAGNITUDE
    counts: dict[str, dict[str, int]] = {}
    for _, row in records.iterrows():
        if row.get("original_case_key") in exclude_case_keys:
            continue
        try:
            deltas = json.loads(str(row.get("feature_delta_json") or "{}"))
        except (TypeError, ValueError):
            continue
        if not isinstance(deltas, dict):
            continue
        for column, delta in deltas.items():
            if not isinstance(delta, dict):
                continue
            magnitude = abs(float(delta.get("delta", 0.0) or 0.0))
            if magnitude < magnitudes.get(column, 0.0):
                continue
            field = STRUCTURED_TO_SCHEME_FIELD.get(column, column)
            slot = counts.setdefault(field, {"up": 0, "down": 0})
            slot["up" if float(delta.get("delta", 0.0) or 0.0) > 0 else "down"] += 1
    ranking: list[tuple[str, str, int, int]] = []
    for field, slot in counts.items():
        total = slot["up"] + slot["down"]
        direction = "up" if slot["up"] >= slot["down"] else "down"
        ranking.append((field, direction, max(slot["up"], slot["down"]), total))
    return sorted(ranking, key=lambda entry: (-entry[3], -entry[2], entry[0]))


def field_delta_statistics(
    records: pd.DataFrame,
    material_magnitudes: dict[str, float] | None = None,
    exclude_case_keys: set[str] | frozenset[str] = frozenset(),
) -> dict[str, dict[str, dict[str, float]]]:
    """Median magnitude per (field, direction) across canonical revision records.

    Returns {field: {"up": {"count": n, "median": m}, "down": {...}}} for material
    deltas only; directions with no observations are absent.
    """
    magnitudes = material_magnitudes or MATERIAL_MAGNITUDE
    stats: dict[str, dict[str, dict[str, float]]] = {}
    for _, row in records.iterrows():
        if row.get("original_case_key") in exclude_case_keys:
            continue
        try:
            deltas = json.loads(str(row.get("feature_delta_json") or "{}"))
        except (TypeError, ValueError):
            continue
        if not isinstance(deltas, dict):
            continue
        for column, delta in deltas.items():
            if not isinstance(delta, dict):
                continue
            value = float(delta.get("delta", 0.0) or 0.0)
            magnitude = abs(value)
            if magnitude < magnitudes.get(column, 0.0):
                continue
            field = STRUCTURED_TO_SCHEME_FIELD.get(column, column)
            direction = "up" if value > 0 else "down"
            slot = stats.setdefault(field, {}).setdefault(direction, {"values": [], "count": 0.0})
            slot["values"].append(value)
            slot["count"] += 1
    for field, directions in stats.items():
        for direction, slot in directions.items():
            values = slot.pop("values")
            values.sort()
            middle = len(values) // 2
            if len(values) % 2:
                slot["median"] = round(values[middle], 2)
            else:
                slot["median"] = round((values[middle - 1] + values[middle]) / 2, 2)
    return stats


def theme_conditioned_direction(
    records: pd.DataFrame,
    field: str,
    themes: list[str],
    theme_to_field: dict[str, list[str]],
    material_magnitudes: dict[str, float] | None = None,
    min_theme_pairs: int = 2,
    exclude_case_keys: set[str] | frozenset[str] = frozenset(),
) -> str | None:
    """Majority change direction for a field among records sharing a diagnosed theme.

    Returns "up"/"down" when at least ``min_theme_pairs`` records carrying one of the
    themes changed the field materially, else None (caller falls back to the global
    majority direction).
    """
    magnitudes = material_magnitudes or MATERIAL_MAGNITUDE
    supported_fields = {field for theme in themes for field in theme_to_field.get(theme, [])}
    if field not in supported_fields:
        return None
    up = down = 0
    for _, row in records.iterrows():
        if row.get("original_case_key") in exclude_case_keys:
            continue
        row_themes = {
            part.strip() for part in str(row.get("refusal_themes_original") or "").split(";")
            if part.strip()
        }
        if not (row_themes & set(themes)):
            continue
        try:
            deltas = json.loads(str(row.get("feature_delta_json") or "{}"))
        except (TypeError, ValueError):
            continue
        if not isinstance(deltas, dict):
            continue
        for column, delta in deltas.items():
            if not isinstance(delta, dict):
                continue
            if STRUCTURED_TO_SCHEME_FIELD.get(column, column) != field:
                continue
            value = float(delta.get("delta", 0.0) or 0.0)
            if abs(value) < magnitudes.get(column, 0.0):
                continue
            if value > 0:
                up += 1
            else:
                down += 1
    if up + down < min_theme_pairs:
        return None
    return "up" if up >= down else "down"


def rerank_by_themes(
    ranking: list[tuple[str, str, int, int]],
    themes: list[str],
    theme_to_field: dict[str, list[str]],
    limit: int = 3,
    window: int = 6,
) -> list[tuple[str, str, int, int]]:
    """Re-rank the most-common changes using diagnosed refusal themes.

    Themes only re-order the top ``window`` most-common fields: a theme-supported
    field inside that window moves up (ranked by theme support, then frequency),
    and no rare theme-mapped field is promoted into the window.
    """
    if not themes:
        return ranking[:limit]
    support: dict[str, int] = {}
    for theme in themes:
        for field in theme_to_field.get(theme, []):
            support[field] = support.get(field, 0) + 1

    def key(entry: tuple[str, str, int, int]) -> tuple[float, int, int, str]:
        field, _direction, majority, total = entry
        theme_support = support.get(field, 0)
        if theme_support:
            return (-float(theme_support), -total, -majority, field)
        return (0.0, -total, -majority, field)

    windowed = sorted(ranking[:window], key=key)
    return windowed[:limit]


def suggested_levers(
    records: pd.DataFrame,
    themes: list[str],
    theme_to_field: dict[str, list[str]],
    changed_fields: set[str] | frozenset[str] = frozenset(),
    limit: int = 5,
    window: int = 8,
    exclude_case_keys: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Suggested next changes for a scenario: most-common empirical changes first,
    re-ranked by the scenario's diagnosed refusal themes. Directions use
    theme-conditioned observations where enough same-theme pairs exist, otherwise
    the global majority direction; median observed deltas come from the full
    audited record set."""
    ranking = most_common_change_ranking(records, exclude_case_keys=exclude_case_keys)
    remaining = [entry for entry in ranking if entry[0] not in changed_fields]
    reranked = rerank_by_themes(remaining, themes, theme_to_field, limit=limit, window=window)
    support: dict[str, int] = {}
    for theme in themes:
        for field in theme_to_field.get(theme, []):
            support[field] = support.get(field, 0) + 1
    stats = field_delta_statistics(records, exclude_case_keys=exclude_case_keys)
    suggestions: list[dict[str, Any]] = []
    for field, global_direction, majority, total in reranked:
        conditioned = theme_conditioned_direction(
            records, field, themes, theme_to_field, exclude_case_keys=exclude_case_keys,
        )
        direction = conditioned or global_direction
        delta_stats = stats.get(field, {}).get(direction, {})
        suggestions.append({
            "field": field,
            "direction": "increase" if direction == "up" else "reduce",
            "direction_source": "theme_conditioned" if conditioned else "global_majority",
            "majority_count": majority,
            "total_count": total,
            "theme_support": support.get(field, 0),
            "supported_by_themes": [theme for theme in themes if field in theme_to_field.get(theme, [])],
            "median_observed_delta": delta_stats.get("median"),
            "median_delta_count": int(delta_stats.get("count", 0)),
        })
    return suggestions


def grade_evidence(model_movement_pp: float | None, revision_pairs: int, annotation_verified: int, precedent_support: bool, policy_support: bool) -> str:
    """Map the three signals onto Strong/Moderate/Weak/None."""
    if model_movement_pp is None or abs(model_movement_pp) < MIN_MODEL_MOVEMENT_PP:
        return "none"
    moved = abs(model_movement_pp) >= MIN_MODEL_MOVEMENT_PP
    if moved and (revision_pairs >= MIN_REVISION_PAIRS_FOR_STRONG or (annotation_verified >= 1 and precedent_support)) and (precedent_support or policy_support):
        return "strong"
    if moved and (revision_pairs >= MIN_REVISION_PAIRS_FOR_MODERATE or precedent_support or policy_support):
        return "moderate"
    if moved:
        return "weak"
    return "none"


def build_recommendation(
    field: str,
    delta: dict[str, object],
    structured_delta_pp: float | None,
    v3_delta_pp: float | None,
    revision_pairs: int,
    annotation_verified: int,
    precedent_support: bool,
    policy_support: bool,
    scheme_field: str | None = None,
) -> dict[str, Any]:
    """Build one graded recommendation line for a changed field."""
    label_field = scheme_field or field
    direction = direction_label(field, delta.get("from"), delta.get("to"))
    movement = structured_delta_pp if structured_delta_pp is not None else v3_delta_pp
    grade = grade_evidence(movement, revision_pairs, annotation_verified, precedent_support, policy_support)
    reasons: list[str] = []
    if movement is not None and abs(movement) >= MIN_MODEL_MOVEMENT_PP:
        reasons.append(
            f"modelled refusal risk changes by {movement:+.1f} percentage points "
            f"({'structured candidate' if structured_delta_pp is not None else 'v3 baseline'})"
        )
    if revision_pairs:
        reasons.append(
            f"{revision_pairs} audited refused-to-revised-to-granted pair(s) changed {field} in the same direction"
        )
    if annotation_verified:
        reasons.append(f"{annotation_verified} annotation-verified change note(s) with source links")
    if precedent_support:
        reasons.append("comparable-case support available")
    if policy_support:
        reasons.append("verified policy-standard comparison available")
    if grade == "none":
        reasons.append("no material modelled movement")
    wording = {
        "strong": "Evidence strength: Strong",
        "moderate": "Evidence strength: Moderate",
        "weak": "Evidence strength: Weak (model movement only)",
        "none": "No recommendation (below modelled-movement threshold)",
    }[grade]
    return {
        "field": field,
        "direction": direction,
        "model_movement_pp": movement,
        "grade": grade,
        "grade_label": wording,
        "reasons": reasons,
    }


def grade_scenario(
    changed_fields: list[str],
    delta: dict[str, dict[str, object]],
    structured_scores: dict[str, float] | None,
    v3_scores: dict[str, float] | None,
    canonical_summary: dict[str, Any] | None,
    policy_comparison: bool = False,
) -> list[dict[str, Any]]:
    """Grade every changed field in a scenario."""
    recommendations: list[dict[str, Any]] = []
    canonical_summary = canonical_summary or {}
    groups = {group["field"]: group for group in canonical_summary.get("field_groups", [])}
    for field in sorted(changed_fields):
        field_delta = delta.get(field, {})
        structured_delta_pp = None
        if structured_scores and "before" in structured_scores and "after" in structured_scores:
            structured_delta_pp = (structured_scores["after"] - structured_scores["before"]) * 100.0
        v3_delta_pp = None
        if v3_scores and "before" in v3_scores and "after" in v3_scores:
            v3_delta_pp = (v3_scores["after"] - v3_scores["before"]) * 100.0
        group = groups.get(field, {})
        revision_pairs = int(group.get("same_direction_count", 0))
        annotation_verified = int(group.get("annotation_verified", 0))
        precedent_support = bool(group.get("matched_count", 0))
        recommendations.append(build_recommendation(
            field,
            field_delta,
            structured_delta_pp,
            v3_delta_pp,
            revision_pairs,
            annotation_verified,
            precedent_support,
            policy_comparison and field in {
                "communal_open_space_sqm", "private_open_space_sqm", "site_area_sqm", "parking_spaces",
            },
        ))
    return sorted(recommendations, key=lambda item: GRADE_ORDER.get(item["grade"], 9))
