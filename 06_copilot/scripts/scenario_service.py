"""Validated, explicit scheme mutation for scenario sensitivity analysis."""
from __future__ import annotations

from typing import Any

from scheme_contract import FIELD_SUPPORT, validate_scheme
from prediction_service import predict_and_record


class ScenarioValidationError(ValueError):
    pass


def mutate_scheme(baseline: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    if not changes:
        raise ScenarioValidationError("scenario must change at least one field")
    candidate = dict(baseline)
    candidate.update(changes)
    canonical, errors = validate_scheme(candidate)
    if errors:
        raise ScenarioValidationError("; ".join(errors))
    changed_fields = sorted(
        field for field in changes
        if canonical.get(field) != baseline.get(field)
    )
    if not changed_fields:
        raise ScenarioValidationError("scenario changes are a no-op")
    support = {
        field: "language_sensitivity" if field == "project_description" else FIELD_SUPPORT.get(field, "captured_only")
        for field in changed_fields
    }
    delta = {
        field: {"from": baseline.get(field), "to": canonical.get(field)}
        for field in changed_fields
    }
    return {"snapshot": canonical, "delta": delta, "changed_fields": changed_fields, "support": support}


def create_scored_scenario(repo, baseline_scheme_id: str, name: str, baseline: dict[str, Any], changes: dict[str, Any], site: dict[str, Any], model) -> dict[str, Any]:
    mutation = mutate_scheme(baseline, changes)
    baseline_row = repo.get_scheme(baseline_scheme_id)
    if baseline_row is None:
        raise ScenarioValidationError("baseline scheme was not found")
    scenario_scheme_id = repo.create_scheme(
        baseline_row["site_id"],
        mutation["snapshot"],
        version=repo.next_scheme_version(baseline_row["site_id"]),
        parent_scheme_id=baseline_scheme_id,
    )
    scenario_id = repo.create_scenario(
        baseline_scheme_id,
        scenario_scheme_id,
        name,
        mutation["delta"],
        mutation["snapshot"],
        mutation["support"],
    )
    score = predict_and_record(repo, scenario_scheme_id, site, mutation["snapshot"], model, scenario_id=scenario_id)
    return {**mutation, "scenario_id": scenario_id, "scenario_scheme_id": scenario_scheme_id, "score": score}
