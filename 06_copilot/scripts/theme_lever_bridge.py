"""Diagnosis-to-levers bridge: refusal themes mapped to editable variables.

The mapping is derived from data, not opinion:
- canonical revision pairs carry refusal themes (original case) plus observed deltas;
- the annotation registry carries addressed themes plus change categories.

Output: theme -> candidate levers with observed co-occurrence counts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from scenario_evidence_service import FIELD_TO_STRUCTURED_DELTA

STRUCTURED_TO_SCHEME = {column: field for field, column in FIELD_TO_STRUCTURED_DELTA.items()}
ROOT = Path(__file__).resolve().parents[2]
CANONICAL_RECORDS = ROOT / "02_development" / "current" / "canonical_revision_scheme_records.csv"
ANNOTATION_REGISTRY = ROOT / "02_development" / "current" / "revision_evidence_annotation_registry_with_links_fixed.csv"

THEME_TO_FIELD = {
    "density_scale": ["units", "max_storeys", "max_height_m", "site_coverage_pct", "plot_ratio"],
    "design_layout": ["max_storeys", "max_height_m", "upper_floor_setback_m", "front_setback_m", "rear_setback_m", "side_setback_m", "housing_type"],
    "traffic_access": ["vehicular_access_points", "parking_spaces", "front_setback_m"],
    "residential_amenity": ["nearest_dwelling_separation_m", "opposing_window_separation_m", "max_height_m", "upper_floor_setback_m"],
    "open_space_amenity": ["private_open_space_sqm", "communal_open_space_sqm"],
    "flooding_drainage": ["site_area_sqm", "communal_open_space_sqm"],
    "land_use_policy": ["development_type", "proposal_type", "housing_type"],
    "premature_or_info_gap": ["project_description"],
    "heritage_archaeology": ["demolition_proposed", "max_height_m"],
    "ecology_trees": ["demolition_proposed", "communal_open_space_sqm"],
    "water_wastewater": ["units"],
    "other": ["units", "max_storeys"],
}


def empirical_theme_levers() -> pd.DataFrame:
    """Observed theme -> changed-field links from the canonical revision pairs."""
    records = pd.read_csv(CANONICAL_RECORDS, low_memory=False)
    rows: list[dict[str, Any]] = []
    for _, record in records.iterrows():
        themes = str(record.get("refusal_themes_original") or "").split(";")
        try:
            deltas = json.loads(record.get("feature_delta_json") or "{}")
        except (TypeError, ValueError):
            deltas = {}
        observed_fields = {
            STRUCTURED_TO_SCHEME.get(field, field)
            for field in deltas.keys()
        }
        for theme in themes:
            theme = theme.strip()
            if not theme:
                continue
            for field in observed_fields:
                rows.append({"theme": theme, "field": field})
    if not rows:
        return pd.DataFrame(columns=["theme", "field", "pairs"])
    frame = pd.DataFrame(rows)
    return frame.groupby(["theme", "field"], as_index=False).size().rename(columns={"size": "pairs"}).sort_values(["theme", "pairs"], ascending=[True, False])


def build_theme_lever_bridge() -> dict[str, Any]:
    """Merge the prior map with observed co-occurrence counts."""
    observed = empirical_theme_levers()
    bridge: dict[str, Any] = {}
    for theme, fields in THEME_TO_FIELD.items():
        entries = []
        for field in fields:
            counts = observed[(observed["theme"] == theme) & (observed["field"] == field)]
            entries.append({
                "field": field,
                "observed_pairs": int(counts["pairs"].sum()) if not counts.empty else 0,
                "source": "observed_revision_pairs" if not counts.empty else "domain_map",
            })
        entries.sort(key=lambda entry: -entry["observed_pairs"])
        bridge[theme] = {
            "label": theme.replace("_", " "),
            "levers": entries,
        }
    return {
        "source_canonical_pairs": str(CANONICAL_RECORDS),
        "themes": bridge,
        "caveat": (
            "Lever mappings are planning-domain heuristics supported by observed revision-pair "
            "deltas where counts exist; they are diagnosis suggestions, not causal rules."
        ),
    }


def save_theme_lever_bridge(path: Path | None = None) -> Path:
    target = path or ROOT / "02_development" / "current" / "theme_lever_bridge.json"
    target.write_text(json.dumps(build_theme_lever_bridge(), indent=2), encoding="utf-8")
    return target


if __name__ == "__main__":
    print(json.dumps(build_theme_lever_bridge(), indent=2)[:3000])
