"""Experimental structured-optimiser scoring service (never replaces v3)."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_PATH = ROOT / "05_policy" / "current" / "model_structured_candidate" / "structured_optimiser_candidate.joblib"


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def build_structured_features(site: dict[str, Any], scheme: dict[str, Any], bundle: dict[str, Any]) -> pd.DataFrame:
    """Map a scheme snapshot onto the candidate's feature space."""
    medians = bundle["feature_medians"]
    units = _number(scheme.get("units"))
    area_sqm = _number(scheme.get("site_area_sqm"))
    floor_sqm = _number(scheme.get("total_gfa_sqm"))
    parking = _number(scheme.get("parking_spaces"))
    open_space = _number(scheme.get("communal_open_space_sqm"))
    if open_space is None:
        open_space = _number(scheme.get("private_open_space_sqm"))
    storeys = _number(scheme.get("max_storeys"))
    year = _number(scheme.get("submission_year")) or 2025.0
    authority = str(site.get("planning_authority") or "")
    reverse_map = {value: key for key, value in bundle["authority_map"].items()}
    authority_ordinal = float(reverse_map.get(authority, int(medians.get("authority_ordinal", 0.0))))

    area_ha = area_sqm / 10000.0 if area_sqm else None
    density = units / area_ha if (units and area_ha) else None
    plot_ratio = floor_sqm / (area_sqm) if (floor_sqm and area_sqm) else None

    features = {
        "log_units": np.log1p(units) if units is not None else medians.get("log_units", 0.0),
        "storeys": storeys if storeys is not None else medians.get("storeys", 2.0),
        "log_site_area_sqm": np.log1p(area_sqm) if area_sqm else medians.get("log_site_area_sqm", 0.0),
        "log_floor_area_sqm": np.log1p(floor_sqm) if floor_sqm else medians.get("log_floor_area_sqm", 0.0),
        "density_units_per_ha": density if density else medians.get("density_units_per_ha", 0.0),
        "plot_ratio_proxy": plot_ratio if plot_ratio else medians.get("plot_ratio_proxy", 0.0),
        "log_parking_spaces": np.log1p(parking) if parking is not None else medians.get("log_parking_spaces", 0.0),
        "log_open_space_sqm": np.log1p(open_space) if open_space is not None else medians.get("log_open_space_sqm", 0.0),
        "units_missing": 0.0 if units is not None else 1.0,
        "site_area_missing": 0.0 if area_sqm else 1.0,
        "floor_area_missing": 0.0 if floor_sqm else 1.0,
        "parking_missing": 0.0 if parking is not None else 1.0,
        "open_space_missing": 0.0 if open_space is not None else 1.0,
        "received_year": year,
        "authority_ordinal": authority_ordinal,
    }
    return pd.DataFrame([{column: features.get(column, 0.0) for column in bundle["feature_columns"]}])


def score_structured(site: dict[str, Any], scheme: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """Score a scheme with the experimental structured candidate."""
    features = build_structured_features(site, scheme, bundle)
    refusal = float(bundle["pipeline"].predict_proba(features)[:, 1][0])
    return {
        "status": "scored",
        "model_version": bundle["model_version"],
        "refusal_probability": round(refusal, 4),
        "grant_probability": round(1.0 - refusal, 4),
        "feature_snapshot": features.iloc[0].to_dict(),
        "experimental": True,
    }


def sensitivity_sweeps(site: dict[str, Any], scheme: dict[str, Any], bundle: dict[str, Any]) -> dict[str, list[dict[str, float]]]:
    """Sweep storeys, units and parking, recomputing features at each point.

    Features are rebuilt from the variant scheme each time, so sweeping units at a
    fixed site area moves density consistently instead of leaving features in a
    contradictory state.
    """
    baseline = dict(scheme)
    sweeps: dict[str, list[dict[str, float]]] = {}
    for field, values in [
        ("max_storeys", [1, 2, 3, 4, 5, 6, 8, 10, 12]),
        ("units", [10, 20, 30, 40, 60, 80, 100, 150]),
        ("parking_spaces", [0, 5, 10, 20, 30, 40, 60, 80]),
    ]:
        rows = []
        for value in values:
            variant = {**baseline, field: float(value)}
            score = score_structured(site, variant, bundle)
            rows.append({"value": value, "refusal_probability": score["refusal_probability"]})
        sweeps[field] = rows
    return sweeps


def load_structured_bundle(path: str | Path | None = None) -> dict[str, Any]:
    import joblib

    source = Path(path) if path else CANDIDATE_PATH
    if not source.exists():
        raise FileNotFoundError(f"structured candidate bundle not found: {source}")
    return joblib.load(source)
