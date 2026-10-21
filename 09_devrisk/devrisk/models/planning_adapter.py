"""Non-invasive integration with the frozen v4-full planning model.

The frozen artifact (05_policy/current/model_v4/national_residential_v4_full.joblib)
is never modified or retrained. This adapter imports the existing scoring path
(05_policy/scripts/model_feature_builder.score_proposal) and re-exposes it as a
versioned prediction interface for the development-risk engine.

Downstream models may consume this score only when it is generated out-of-fold
or time-safely for historical rows (brief section 15.6).
"""
from __future__ import annotations

import sys
from typing import Any

from .. import settings


def _ensure_planning_scripts_on_path() -> None:
    if str(settings.PLANNING_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(settings.PLANNING_SCRIPTS_DIR))


def score_planning(proposal: dict[str, Any]) -> dict[str, Any]:
    """Score one proposal with the frozen model. Returns the model's own dict."""
    _ensure_planning_scripts_on_path()
    from model_feature_builder import score_proposal  # noqa: PLC0415

    return score_proposal(proposal)


def frozen_model_version() -> str:
    import json

    manifest = json.loads(settings.FROZEN_MANIFEST_JSON.read_text(encoding="utf-8"))
    return str(manifest.get("model_version", "unknown"))


def proposal_from_application(
    *,
    authority: str,
    description: str,
    units: int | None,
    site_area_sqm: float | None = None,
    floor_area_sqm: float | None = None,
    itm_easting: float | None = None,
    itm_northing: float | None = None,
    submission_year: int | None = None,
) -> dict[str, Any]:
    """Build a frozen-model proposal dict from a historical application row.

    Submission-time fields only. `submission_year` must be the application's
    received year so history features stay time-safe at query time.
    """
    proposal: dict[str, Any] = {
        "authority": authority,
        "description": description or "",
        "units": units,
    }
    if site_area_sqm is not None:
        proposal["site_area_sqm"] = site_area_sqm
    if floor_area_sqm is not None:
        proposal["floor_area_sqm"] = floor_area_sqm
    if itm_easting is not None:
        proposal["itm_easting"] = itm_easting
    if itm_northing is not None:
        proposal["itm_northing"] = itm_northing
    if submission_year is not None:
        proposal["submission_year"] = submission_year
    return proposal
