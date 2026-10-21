"""Model boundary: map a versioned scheme to v3 and append an immutable run."""
from __future__ import annotations

from typing import Any

from precedent_copilot_logic import score_submission_risk

MODEL_INPUT_KEYS = {
    "PlanningAuthority", "ApplicationType", "DevelopmentDescription", "DevelopmentAddress",
    "units_total_best", "NumResidentialUnits", "max_storeys_best", "site_area_ha_best",
    "ITMEasting", "ITMNorthing", "received_year",
}


def build_model_query(site: dict[str, Any], scheme: dict[str, Any]) -> dict[str, Any]:
    """Create only submission-time v3 inputs; post-submission keys are ignored."""
    area_sqm = scheme.get("site_area_sqm")
    query = {
        "PlanningAuthority": site.get("planning_authority"),
        "ApplicationType": scheme.get("application_type") or scheme.get("proposal_type"),
        "DevelopmentDescription": scheme.get("project_description") or "",
        "DevelopmentAddress": site.get("address") or "",
        "units_total_best": scheme.get("units"),
        "NumResidentialUnits": scheme.get("units"),
        "max_storeys_best": scheme.get("max_storeys"),
        "site_area_ha_best": None if area_sqm is None else float(area_sqm) / 10000.0,
        "ITMEasting": site.get("itm_easting"),
        "ITMNorthing": site.get("itm_northing"),
        "received_year": scheme.get("submission_year"),
    }
    return {key: value for key, value in query.items() if key in MODEL_INPUT_KEYS}


def predict_and_record(repo, scheme_id: str, site: dict[str, Any], scheme: dict[str, Any], model, scenario_id: str | None = None, calibration_version: str | None = None) -> dict[str, Any]:
    query = build_model_query(site, scheme)
    score = score_submission_risk(query, model)
    if score.get("status") != "scored":
        raise ValueError(f"prediction skipped: {score.get('reason', 'unknown reason')}")
    refusal = float(score["refusal_score"])
    output = dict(score)
    output["grant_probability"] = 1.0 - refusal
    run_id = repo.record_model_run(
        scheme_id=scheme_id,
        scenario_id=scenario_id,
        model_version=str(score.get("model_version", "unknown")),
        calibration_version=calibration_version,
        input_snapshot=query,
        output=output,
    )
    output["model_run_id"] = run_id
    return output
