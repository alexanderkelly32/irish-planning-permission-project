"""Document extraction contracts (brief section 11).

The planning_friction_v1 JSON contract constrains every LLM extraction:
evidence spans for every material field, unknown distinct from absent,
versioned prompts, deterministic retry/failure logging. No unsupported
free-text conclusions; no training on unreviewed LLM labels until audit
precision is known.
"""
from __future__ import annotations

import json
from typing import Any

SCHEMA_VERSION = "planning_friction_v1"

EVENT_TYPES = {
    "further_information_request",
    "clarification_request",
    "first_party_appeal",
    "third_party_appeal",
    "judicial_review",
    "withdrawal",
    "material_amendment",
    "extension_of_duration",
    "completion_event",
}

RISK_FACTOR_TYPES = {
    "wastewater_dependency",
    "flood_mitigation",
    "archaeology",
    "protected_structure",
    "basement_works",
    "demolition",
    "abnormal_ground",
    "offsite_infrastructure",
    "major_road_works",
    "grid_dependency",
    "complex_phasing",
    "precommencement_conditions",
}

REQUIRED_TOP_KEYS = {"schema_version", "application_reference", "events", "risk_factors"}


def validate_extraction(payload: dict[str, Any]) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be an object"]
    for key in REQUIRED_TOP_KEYS:
        if key not in payload:
            errors.append(f"missing required key: {key}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if "events" in payload:
        for index, event in enumerate(payload["events"]):
            if not isinstance(event, dict):
                errors.append(f"events[{index}] not an object")
                continue
            if event.get("event_type") not in EVENT_TYPES:
                errors.append(f"events[{index}] unknown event_type: {event.get('event_type')}")
            if not event.get("evidence"):
                errors.append(f"events[{index}] missing evidence spans")
            else:
                for span in event["evidence"]:
                    if not isinstance(span, dict) or "page" not in span or "quote" not in span:
                        errors.append(f"events[{index}] evidence span missing page/quote")
            if "confidence" in event and not (0 <= float(event["confidence"]) <= 1):
                errors.append(f"events[{index}] confidence outside [0,1]")
    if "risk_factors" in payload:
        for index, factor in enumerate(payload["risk_factors"]):
            if not isinstance(factor, dict):
                errors.append(f"risk_factors[{index}] not an object")
                continue
            if factor.get("type") not in RISK_FACTOR_TYPES:
                errors.append(f"risk_factors[{index}] unknown type: {factor.get('type')}")
            if factor.get("status") not in {"present", "absent", "unknown"}:
                errors.append(f"risk_factors[{index}] status must be present/absent/unknown")
            if factor.get("status") == "present" and not factor.get("evidence"):
                errors.append(f"risk_factors[{index}] present without evidence")
    return errors


def minimal_template(application_reference: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "application_reference": application_reference,
        "events": [],
        "risk_factors": [],
    }


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
