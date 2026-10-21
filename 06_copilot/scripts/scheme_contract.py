"""Canonical Site/Scheme input contract and v3 field-support registry."""
from __future__ import annotations

import math
from typing import Any

FIELD_SUPPORT = {
    "units": "derived_model_active",
    "project_description": "model_active",
    "development_type": "derived_model_active",
    "proposal_type": "derived_model_active",
    "application_type": "derived_model_active",
    "submission_year": "derived_model_active",
    "max_storeys": "retrieval_only",
    "site_area_sqm": "retrieval_only",
    "max_height_m": "captured_only",
    "density_units_per_ha": "captured_only",
    "plot_ratio": "captured_only",
    "site_coverage_pct": "captured_only",
    "front_setback_m": "captured_only",
    "rear_setback_m": "captured_only",
    "side_setback_m": "captured_only",
    "upper_floor_setback_m": "captured_only",
    "nearest_dwelling_separation_m": "captured_only",
    "opposing_window_separation_m": "captured_only",
    "private_open_space_sqm": "captured_only",
    "communal_open_space_sqm": "captured_only",
    "parking_spaces": "retrieval_only",
    "bicycle_spaces": "retrieval_only",
    "vehicular_access_points": "captured_only",
    "total_gfa_sqm": "captured_only",
    "residential_gfa_sqm": "captured_only",
    "commercial_gfa_sqm": "captured_only",
    "demolition_area_sqm": "captured_only",
    "demolition_proposed": "captured_only",
    "unit_mix": "captured_only",
    "housing_type": "captured_only",
}

SITE_FIELDS = {
    "address": {"unit": None, "required": True},
    "eircode": {"unit": None, "required": False},
    "latitude": {"unit": "decimal_degrees", "required": False},
    "longitude": {"unit": "decimal_degrees", "required": False},
    "site_area_sqm": {"unit": "m2", "required": False},
    "planning_authority": {"unit": None, "required": True},
    "zoning": {"unit": None, "required": False},
    "current_use": {"unit": None, "required": False},
}

FIELD_UNITS = {
    "units": "count", "submission_year": "year", "max_storeys": "count",
    "site_area_sqm": "m2", "max_height_m": "m", "density_units_per_ha": "units_per_ha",
    "plot_ratio": "ratio", "site_coverage_pct": "percent", "front_setback_m": "m",
    "rear_setback_m": "m", "side_setback_m": "m", "upper_floor_setback_m": "m",
    "nearest_dwelling_separation_m": "m", "opposing_window_separation_m": "m",
    "private_open_space_sqm": "m2", "communal_open_space_sqm": "m2", "parking_spaces": "count",
    "bicycle_spaces": "count", "vehicular_access_points": "count", "total_gfa_sqm": "m2",
    "residential_gfa_sqm": "m2", "commercial_gfa_sqm": "m2", "demolition_area_sqm": "m2",
}

NUMERIC_RULES = {
    "units": (0, None), "submission_year": (1900, 2200), "max_storeys": (0, 100),
    "site_area_sqm": (0, None), "max_height_m": (0, 500), "density_units_per_ha": (0, 1000),
    "plot_ratio": (0, 20), "site_coverage_pct": (0, 100),
    "front_setback_m": (0, None), "rear_setback_m": (0, None), "side_setback_m": (0, None),
    "upper_floor_setback_m": (0, None), "nearest_dwelling_separation_m": (0, None),
    "opposing_window_separation_m": (0, None), "private_open_space_sqm": (0, None),
    "communal_open_space_sqm": (0, None), "parking_spaces": (0, None), "bicycle_spaces": (0, None),
    "vehicular_access_points": (0, None), "total_gfa_sqm": (0, None),
    "residential_gfa_sqm": (0, None), "commercial_gfa_sqm": (0, None), "demolition_area_sqm": (0, None),
}
STRING_FIELDS = {"development_type", "proposal_type", "application_type", "housing_type", "project_description"}
SPECIAL_FIELDS = {"demolition_proposed", "unit_mix", "provenance"}
KNOWN_FIELDS = set(NUMERIC_RULES) | STRING_FIELDS | SPECIAL_FIELDS


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def validate_scheme(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return a canonical, JSON-safe scheme snapshot and validation errors."""
    values: dict[str, Any] = {field: None for field in KNOWN_FIELDS}
    errors: list[str] = []
    for field in raw:
        if field not in KNOWN_FIELDS:
            errors.append(f"unknown field: {field}")
    for field, (minimum, maximum) in NUMERIC_RULES.items():
        parsed = _number(raw.get(field))
        values[field] = parsed
        if raw.get(field) is not None and parsed is None:
            errors.append(f"{field} must be numeric")
        if parsed is not None and (parsed < minimum or (maximum is not None and parsed > maximum)):
            errors.append(f"{field} must be between {minimum} and {maximum or 'unbounded'}")
            values[field] = None
    for field in STRING_FIELDS:
        value = raw.get(field)
        values[field] = str(value).strip() if value is not None else None
    values["demolition_proposed"] = raw.get("demolition_proposed")
    values["unit_mix"] = raw.get("unit_mix")
    values["provenance"] = raw.get("provenance") or {}
    return values, errors


def validate_site(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Validate the location record kept separate from a scheme."""
    values = {field: raw.get(field) for field in SITE_FIELDS}
    errors: list[str] = []
    for field in ("address", "planning_authority"):
        value = values[field]
        values[field] = str(value).strip() if value is not None else None
        if not values[field]:
            errors.append(f"{field} is required")
    for field, minimum, maximum in (("latitude", -90, 90), ("longitude", -180, 180), ("site_area_sqm", 0, None)):
        parsed = _number(raw.get(field))
        values[field] = parsed
        if raw.get(field) is not None and parsed is None:
            errors.append(f"{field} must be numeric")
        if parsed is not None and (parsed < minimum or (maximum is not None and parsed > maximum)):
            values[field] = None
            errors.append(f"{field} is outside its valid range")
    for field in ("eircode", "zoning", "current_use"):
        values[field] = str(raw[field]).strip() if raw.get(field) is not None else None
    return values, errors
