"""Submission-time structured features with explicit missingness indicators."""
from __future__ import annotations

import numpy as np
import pandas as pd

STRUCTURED_NUMERIC = [
    "log_submitted_units",
    "log_site_area_ha",
    "log_floor_area_sqm",
    "density_units_per_ha",
    "plot_ratio_proxy",
    "units_missing",
    "area_missing",
    "floor_area_missing",
]


def add_structured_scheme_features(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    units = pd.to_numeric(out.get("NumResidentialUnits"), errors="coerce")
    area_ha = pd.to_numeric(out.get("AreaofSite"), errors="coerce")
    floor_area = pd.to_numeric(out.get("FloorArea"), errors="coerce")
    units = units.where(units >= 0)
    area_ha = area_ha.where(area_ha > 0)
    floor_area = floor_area.where(floor_area >= 0)
    out["units_missing"] = units.isna().astype(float)
    out["area_missing"] = area_ha.isna().astype(float)
    out["floor_area_missing"] = floor_area.isna().astype(float)
    out["log_submitted_units"] = np.log1p(units)
    out["log_site_area_ha"] = np.log1p(area_ha)
    out["log_floor_area_sqm"] = np.log1p(floor_area)
    out["density_units_per_ha"] = units / area_ha
    out["plot_ratio_proxy"] = floor_area / (area_ha * 10000.0)
    return out
