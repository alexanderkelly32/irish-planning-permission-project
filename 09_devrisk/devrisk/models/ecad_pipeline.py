"""ECAD-ready pipeline scaffold (point-in-polygon join + Created-Date filter +
consistency scorer).

Plugs straight in when ECAD/GeoDirectory sample data lands. Given:
  - scheme sites (ITM polygons approximated as circles; upgrade to real
    polygons when available)
  - address points with (easting, northing, created_date, address, eircode)
produces candidate address clusters per scheme, filters by created_date >
grant, and scores consistency against expected units / PPR sale dates.

Schema-agnostic: columns are mapped from the ECAD Product Guide when received;
this module defines the contract and works on synthetic fixtures now.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

ECAD_COLUMN_MAP = {
    "easting": "easting",        # ECAD geo X
    "northing": "northing",      # ECAD geo Y
    "created_date": "created_date",  # ECAD Created Date
    "address": "address",        # canonical postal address
    "eircode": "eircode",
    "building_use": "building_use",
}


def points_in_site(
    scheme: dict[str, Any],
    points: pd.DataFrame,
    *,
    radius_metres: float = 250.0,
) -> pd.DataFrame:
    """Address points inside the scheme site circle (polygon upgrade later)."""
    frame = points.copy()
    s_east = float(scheme["itm_easting"])
    s_north = float(scheme["itm_northing"])
    distance = np.hypot(frame["easting"] - s_east, frame["northing"] - s_north)
    frame["distance_metres"] = distance.round(0)
    return frame[distance <= radius_metres].copy()


def created_after_grant(candidates: pd.DataFrame, grant_date: pd.Timestamp) -> pd.DataFrame:
    frame = candidates.copy()
    frame["created_dt"] = pd.to_datetime(frame["created_date"], utc=True, errors="coerce")
    grant = pd.Timestamp(grant_date)
    if grant.tzinfo is None:
        grant = grant.tz_localize("UTC")
    frame = frame[frame["created_dt"] >= grant - pd.Timedelta(days=90)]
    frame = frame[~frame["building_use"].fillna("").astype(str).str.lower().str.contains("commercial|industrial", na=False)]
    return frame


def consistency_score(
    scheme: dict[str, Any],
    candidates: pd.DataFrame,
    ppr_sales: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Consistency: created-address count vs expected units; PPR overlap."""
    expected = float(scheme.get("units") or 0)
    n_points = int(len(candidates))
    unit_ratio = n_points / expected if expected else None
    result: dict[str, Any] = {
        "scheme_id": scheme["scheme_id"],
        "address_points_in_site": n_points,
        "expected_units": expected,
        "unit_ratio": round(unit_ratio, 3) if unit_ratio is not None else None,
        "created_date_min": str(candidates["created_dt"].min()) if n_points else None,
        "created_date_max": str(candidates["created_dt"].max()) if n_points else None,
    }
    if ppr_sales is not None and not ppr_sales.empty and n_points:
        matched = ppr_sales[ppr_sales["eircode"].isin(candidates["eircode"].dropna())]
        result["ppr_matched_of_points"] = int(len(matched))
        result["ppr_overlap_ratio"] = round(len(matched) / n_points, 3)
    return result


def scheme_fingerprint(
    scheme: dict[str, Any],
    points: pd.DataFrame,
    *,
    ppr_sales: pd.DataFrame | None = None,
    radius_metres: float = 250.0,
) -> dict[str, Any]:
    inside = points_in_site(scheme, points, radius_metres=radius_metres)
    created = created_after_grant(inside, pd.Timestamp(scheme["grant_date"]))
    return consistency_score(scheme, created, ppr_sales)
