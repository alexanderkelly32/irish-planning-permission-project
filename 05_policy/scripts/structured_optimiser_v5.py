"""v5 structured optimiser helpers: planner-report joins and v5 feature design.

The v5 candidate adds planner-report-extracted variables (metre heights,
separations, access points, setbacks, open space) to the v4 text-free
structured cohort. Values are used only where extraction records exist;
missing flags make coverage explicit for the estimator.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from structured_optimiser import build_cohort

ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "02_development" / "source_data" / "planner_reports"

AUTHORITY_CODE_MAP = {
    "KildareCC": "Kildare County Council",
    "LaoisCC": "Laois County Council",
    "LimerickCC": "Limerick County Council",
    "LouthCC": "Louth County Council",
    "MeathCC": "Meath County Council",
    "TipperaryCC": "Tipperary County Council",
    "WaterfordCCC": "Waterford City and County Council",
}

REPORT_COLUMN_MAP = {
    "doc_max_storeys": "report_storeys",
    "doc_max_height_m": "report_max_height_m",
    "doc_nearest_dwelling_separation_m": "report_nearest_dwelling_separation_m",
    "doc_opposing_window_separation_m": "report_opposing_window_separation_m",
    "doc_vehicular_access_points": "report_vehicular_access_points",
    "doc_cycle_parking_spaces": "report_cycle_parking_spaces",
    "doc_front_setback_m": "report_front_setback_m",
    "doc_communal_open_space_sqm": "report_communal_open_space_sqm",
    "doc_private_open_space_sqm": "report_private_open_space_sqm",
    "doc_parking_spaces": "report_parking_spaces",
}

V5_NUMERIC = [
    "log_units",
    "storeys",
    "log_site_area_sqm",
    "log_floor_area_sqm",
    "density_units_per_ha",
    "plot_ratio_proxy",
    "log_parking_spaces",
    "log_open_space_sqm",
    "log_max_height_m",
    "log_nearest_dwelling_separation_m",
    "log_opposing_window_separation_m",
    "log_vehicular_access_points",
    "log_cycle_parking_spaces",
    "log_front_setback_m",
    "received_year",
]
V5_MISSING_FLAGS = [
    "units_missing",
    "site_area_missing",
    "floor_area_missing",
    "parking_missing",
    "open_space_missing",
    "height_missing",
    "separation_missing",
    "window_missing",
    "access_missing",
    "cycle_missing",
    "setback_missing",
]
AUTHORITY_FEATURE = "authority_ordinal"
V5_FEATURES = [*V5_NUMERIC, *V5_MISSING_FLAGS, AUTHORITY_FEATURE]


def map_report_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Rename doc_* columns to report_* names and coerce numerics."""
    out = frame.copy()
    for column, target in REPORT_COLUMN_MAP.items():
        if column in out.columns:
            out[target] = pd.to_numeric(out[column], errors="coerce")
    return out


def load_planner_reports(reports_dir: Path | None = None) -> pd.DataFrame:
    """Concat all council report extractions; add join keys and per-column
    numeric filters."""
    base = reports_dir or REPORTS_DIR
    frames: list[pd.DataFrame] = []
    for csv_path in sorted(base.rglob("report_ocr_extractions.csv")):
        frame = pd.read_csv(csv_path, low_memory=False)
        frame["_authority"] = AUTHORITY_CODE_MAP.get(csv_path.parent.name, csv_path.parent.name)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    merged["app_number"] = merged["case_key"].astype(str).str.strip()
    return map_report_columns(merged)


def dedupe_reports(reports: pd.DataFrame) -> pd.DataFrame:
    """One row per (authority, app) with per-column first-non-null fill."""
    columns = [*REPORT_COLUMN_MAP.values()]
    existing = [column for column in columns if column in reports.columns]
    keep = ["_authority", "app_number", *existing]
    frame = reports[keep].copy()
    frame["_non_null"] = frame[existing].notna().sum(axis=1)
    frame = frame.sort_values(["_authority", "app_number", "_non_null"], ascending=[True, True, False])
    deduped = frame.groupby(["_authority", "app_number"], as_index=False).first()
    for column in existing:
        first = frame.groupby(["_authority", "app_number"])[column].first().reset_index()
        deduped = deduped.drop(columns=[column]).merge(first, on=["_authority", "app_number"], how="left")
    return deduped.drop(columns="_non_null")


def join_planner_features(cohort: pd.DataFrame, reports: pd.DataFrame) -> pd.DataFrame:
    """Join deduped planner-report values onto the cohort by authority + app number."""
    if reports.empty:
        joined = cohort.copy()
    else:
        deduped = dedupe_reports(reports)
        cohort_keys = cohort.copy()
        cohort_keys["app_number"] = cohort_keys["ApplicationNumber"].fillna("").astype(str).str.strip()
        cohort_keys["_authority"] = cohort_keys["PlanningAuthority"]
        joined = cohort_keys.merge(deduped, on=["_authority", "app_number"], how="left")
        joined = joined.drop(columns=["_authority", "app_number"])
    return _derive_v5_features(joined)


def _optional_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _derive_v5_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    report_storeys = _optional_numeric(out, "report_storeys").where(
        lambda s: s.between(1, 40)
    )
    if "storeys" in out.columns:
        out["storeys"] = report_storeys.fillna(pd.to_numeric(out["storeys"], errors="coerce"))

    report_parking = _optional_numeric(out, "report_parking_spaces").where(
        lambda s: s.between(0, 5000)
    )
    if "parking_spaces_best" in out.columns:
        description_parking_raw = pd.to_numeric(out["parking_spaces_best"], errors="coerce").where(
            lambda s: s.between(0, 5000)
        )
        out["log_parking_spaces"] = np.log1p(
            report_parking.fillna(description_parking_raw).clip(lower=0).fillna(0)
        )

    height = _optional_numeric(out, "report_max_height_m").where(
        lambda s: s.between(2, 150)
    )
    separation = _optional_numeric(out, "report_nearest_dwelling_separation_m").where(
        lambda s: s.between(0, 300)
    )
    window = _optional_numeric(out, "report_opposing_window_separation_m").where(
        lambda s: s.between(0, 300)
    )
    access = _optional_numeric(out, "report_vehicular_access_points").where(
        lambda s: s.between(0, 12)
    )
    cycle = _optional_numeric(out, "report_cycle_parking_spaces").where(
        lambda s: s.between(0, 2000)
    )
    setback = _optional_numeric(out, "report_front_setback_m").where(
        lambda s: s.between(0, 100)
    )

    out["log_max_height_m"] = np.log1p(height.clip(lower=0))
    out["log_nearest_dwelling_separation_m"] = np.log1p(separation.clip(lower=0))
    out["log_opposing_window_separation_m"] = np.log1p(window.clip(lower=0))
    out["log_vehicular_access_points"] = np.log1p(access.clip(lower=0))
    out["log_cycle_parking_spaces"] = np.log1p(cycle.clip(lower=0))
    out["log_front_setback_m"] = np.log1p(setback.clip(lower=0))

    out["height_missing"] = height.isna().astype(int)
    out["separation_missing"] = separation.isna().astype(int)
    out["window_missing"] = window.isna().astype(int)
    out["access_missing"] = access.isna().astype(int)
    out["cycle_missing"] = cycle.isna().astype(int)
    out["setback_missing"] = setback.isna().astype(int)
    report_columns = [
        "report_storeys", "report_max_height_m", "report_nearest_dwelling_separation_m",
        "report_opposing_window_separation_m", "report_vehicular_access_points",
        "report_cycle_parking_spaces", "report_front_setback_m",
        "report_communal_open_space_sqm", "report_private_open_space_sqm",
        "report_parking_spaces",
    ]
    present = [column for column in report_columns if column in out.columns]
    out["report_joined"] = out[present].notna().any(axis=1).astype(int) if present else 0
    return out


def build_v5_cohort(source: pd.DataFrame, reports: pd.DataFrame | None = None) -> pd.DataFrame:
    """v4 cohort plus planner-report variables; storeys prefer report values."""
    cohort = build_cohort(source)
    joined = join_planner_features(cohort, reports if reports is not None else pd.DataFrame())
    return joined.reset_index(drop=True)
