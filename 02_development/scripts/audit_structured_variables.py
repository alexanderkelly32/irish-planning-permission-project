"""Task 1 audit: structured-variable coverage, provenance and distributions."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

REGISTER_FIELDS = {
    "units": "NumResidentialUnits",
    "site_area_ha": "AreaofSite",
    "floor_area_sqm": "FloorArea",
    "one_off_house": "OneOffHouse",
}
EXTRACTED_FIELDS = {
    "units": "units_total_best",
    "max_storeys": "max_storeys_best",
    "parking_spaces": "parking_spaces_best",
    "cycle_parking_spaces": "cycle_parking_spaces_best",
    "site_area_sqm": "site_area_sqm_best",
    "floor_area_sqm": "floor_area_sqm_best",
    "open_space_sqm": "open_space_sqm_best",
    "bed_1": "bed_1_best",
    "bed_2": "bed_2_best",
    "bed_3": "bed_3_best",
    "phase": "phase_best",
}
PLAUSIBLE_BOUNDS = {
    "units": (1.0, 2000.0),
    "max_storeys": (1.0, 80.0),
    "parking_spaces": (0.0, 5000.0),
    "cycle_parking_spaces": (0.0, 10000.0),
    "site_area_ha": (0.005, 500.0),
    "site_area_sqm": (50.0, 5_000_000.0),
    "floor_area_sqm": (10.0, 200_000.0),
    "open_space_sqm": (0.0, 200_000.0),
}


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def field_coverage(frame: pd.DataFrame, fields: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Rows, non-null count and fraction for each named field."""
    if frame.empty:
        return {}
    output: dict[str, dict[str, Any]] = {}
    for name, column in fields.items():
        if column not in frame.columns:
            output[name] = {"rows": int(len(frame)), "non_null": 0, "fraction": 0.0, "column_missing": True}
            continue
        non_null = int(pd.to_numeric(frame[column], errors="coerce").notna().sum())
        output[name] = {
            "rows": int(len(frame)),
            "non_null": non_null,
            "fraction": round(non_null / len(frame), 4),
            "column_missing": False,
        }
    return output


def grouped_coverage(frame: pd.DataFrame, field: str, group_column: str, minimum_rows: int = 5) -> pd.DataFrame:
    """Non-null fraction of a numeric field within each group."""
    if frame.empty or field not in frame.columns:
        return pd.DataFrame()
    values = pd.to_numeric(frame[field], errors="coerce")
    rows: list[dict[str, Any]] = []
    for group, indices in frame.groupby(group_column).groups.items():
        part = values.loc[indices]
        if len(part) < minimum_rows:
            continue
        rows.append({
            group_column: str(group),
            "rows": int(len(part)),
            "non_null": int(part.notna().sum()),
            "fraction": round(float(part.notna().mean()), 4),
        })
    return pd.DataFrame(rows).sort_values("rows", ascending=False)


def distribution_stats(values: pd.Series, bounds: tuple[float, float] | None = None) -> dict[str, Any]:
    """Distribution plus implausible-value counts against optional bounds."""
    parsed = pd.to_numeric(values, errors="coerce").dropna()
    if parsed.empty:
        return {"non_null": 0}
    stats = {
        "non_null": int(len(parsed)),
        "min": float(parsed.min()),
        "p25": float(parsed.quantile(0.25)),
        "median": float(parsed.median()),
        "p75": float(parsed.quantile(0.75)),
        "p95": float(parsed.quantile(0.95)),
        "max": float(parsed.max()),
    }
    if bounds is not None:
        low, high = bounds
        stats["implausible_below_min"] = int((parsed < low).sum())
        stats["implausible_above_max"] = int((parsed > high).sum())
    return stats


def distribution_table(frame: pd.DataFrame, fields: dict[str, str], bounds: dict[str, tuple[float, float]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for name, column in fields.items():
        row = {"field": name, "column": column}
        if column not in frame.columns:
            row.update({"non_null": 0, "column_missing": True})
        else:
            row.update(distribution_stats(frame[column], bounds.get(name)))
        rows.append(row)
    return pd.DataFrame(rows)


def recommend_ready_fields(
    register_coverage: dict[str, dict[str, Any]],
    extracted_coverage: dict[str, dict[str, Any]],
    minimum_fraction: float = 0.25,
    minimum_rows: int = 3000,
) -> dict[str, Any]:
    """Recommend which variables can be modelled immediately, based only on coverage."""
    ready: list[dict[str, str]] = []
    needs_extraction: list[dict[str, str]] = []
    for name, metrics in register_coverage.items():
        if metrics["column_missing"]:
            continue
        if metrics["non_null"] >= minimum_rows and metrics["fraction"] >= minimum_fraction:
            ready.append({"variable": name, "tier": "register", "fraction": metrics["fraction"]})
        else:
            needs_extraction.append({"variable": name, "tier": "register", "fraction": metrics["fraction"]})
    for name, metrics in extracted_coverage.items():
        if metrics["column_missing"]:
            needs_extraction.append({"variable": name, "tier": "extracted", "fraction": 0.0, "reason": "column missing"})
            continue
        if metrics["non_null"] >= minimum_rows and metrics["fraction"] >= minimum_fraction:
            ready.append({"variable": name, "tier": "extracted", "fraction": metrics["fraction"]})
        else:
            needs_extraction.append({"variable": name, "tier": "extracted", "fraction": metrics["fraction"]})
    return {
        "ready_to_model": sorted(ready, key=lambda item: -item["fraction"]),
        "needs_extraction_or_low_coverage": sorted(
            needs_extraction, key=lambda item: (item.get("reason", ""), -item["fraction"])
        ),
        "absent_entirely": [
            "max_height_m", "density_units_per_ha_structured", "plot_ratio_structured",
            "front_setback_m", "rear_setback_m", "side_setback_m", "upper_floor_setback_m",
            "nearest_dwelling_separation_m", "opposing_window_separation_m", "vehicular_access_points",
        ],
        "rule": f"minimum_fraction={minimum_fraction}, minimum_rows={minimum_rows}",
    }


def derive_density_plot_ratio(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive density and plot-ratio proxies where both source fields exist."""
    out = frame.copy()
    units = pd.to_numeric(out.get("NumResidentialUnits"), errors="coerce")
    area = pd.to_numeric(out.get("AreaofSite"), errors="coerce")
    floor = pd.to_numeric(out.get("FloorArea"), errors="coerce")
    out["density_units_per_ha"] = np.where(area > 0, units / area, np.nan)
    out["plot_ratio_proxy"] = np.where(area > 0, floor / (area * 10000.0), np.nan)
    return out
