"""Canonical report spec (docs/Initial_Development_Risk_Report_Product_Brief.md).

Modules 6.1-6.15 with availability state per scheme; the four-class statement
language (observed fact / model estimate / analytical inference / unknown);
evidence-annotation helpers. Unsupported modules abstain cleanly - they are
marked unavailable, never padded with generic prose.
"""
from __future__ import annotations

from typing import Any

MODULES = {
    "identity_snapshot": "6.1 Scheme identity and analysis snapshot",
    "facts_pack": "6.2 Structured facts pack",
    "analytical_summary": "6.3 Analytical summary",
    "number_origin": "6.4 Where did this number come from?",
    "planning_outcome": "6.5 Planning outcome forecast",
    "refusal_reasons": "6.6 Likely refusal reasons",
    "grant_conditions": "6.7 Likely grant conditions",
    "friction_forecast": "6.8 Planning-friction forecast",
    "milestones": "6.9 Milestone forecast",
    "risk_register": "6.10 Evidence-backed risk register",
    "comparables": "6.11 Longitudinal comparable schemes",
    "unknowns": "6.12 Material unknowns",
    "next_best_evidence": "6.13 Next-best evidence",
    "scenario_frontier": "6.14 Scenario frontier",
    "cost_pressure": "6.15 Cost-pressure evidence",
}

STATEMENT_CLASSES = ("observed_fact", "model_estimate", "analytical_inference", "unknown")

V1_MUST_SHIP = [
    "identity_snapshot", "facts_pack", "planning_outcome", "number_origin",
    "refusal_reasons", "grant_conditions", "friction_forecast", "milestones",
    "risk_register", "comparables", "unknowns", "next_best_evidence",
    "scenario_frontier",
]
VALIDATED_ONLY = ["milestones_activation", "milestones_completion", "milestones_exit", "cost_pressure_modelling"]


class Statement:
    """A classified statement (brief section 4)."""

    def __init__(self, text: str, classification: str, *, evidence: str | None = None):
        if classification not in STATEMENT_CLASSES:
            raise ValueError(f"classification must be one of {STATEMENT_CLASSES}")
        self.text = text
        self.classification = classification
        self.evidence = evidence

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "classification": self.classification, "evidence": self.evidence}


def probability_statement(
    event: str,
    horizon: str,
    clock_origin: str,
    estimate: float,
    *,
    snapshot: str,
    uncertainty: str,
    model_version: str,
    coverage: str,
) -> dict[str, Any]:
    """Every probability states all eight required fields (brief section 7)."""
    return {
        "event": event,
        "horizon": horizon,
        "clock_origin": clock_origin,
        "information_snapshot": snapshot,
        "estimate": round(float(estimate), 4),
        "uncertainty": uncertainty,
        "model_version": model_version,
        "coverage_limitation": coverage,
    }


def module_availability(payload: dict[str, Any], scheme_context: dict[str, Any]) -> dict[str, str]:
    """Availability per module for one scheme: available | degraded | unavailable."""
    availability = {key: "unavailable" for key in MODULES}
    availability["identity_snapshot"] = "available" if scheme_context.get("identity_confirmed") else "degraded"
    availability["facts_pack"] = "available"
    if payload.get("probabilities"):
        availability["analytical_summary"] = "available"
    if payload.get("planning_outcome"):
        availability["planning_outcome"] = "available"
    if payload.get("drivers"):
        availability["number_origin"] = "available"
    if payload.get("refusal_reasons"):
        availability["refusal_reasons"] = "available"
    if payload.get("grant_conditions"):
        availability["grant_conditions"] = "available"
    if payload.get("friction"):
        availability["friction_forecast"] = "available"
    if payload.get("permission_timing"):
        availability["milestones"] = "degraded"  # permission timing present; later milestones validated-only
    if payload.get("risk_register"):
        availability["risk_register"] = "available"
    if payload.get("comparables"):
        availability["comparables"] = "available"
    if payload.get("unknowns"):
        availability["unknowns"] = "available"
    if payload.get("next_best_evidence"):
        availability["next_best_evidence"] = "available"
    if payload.get("scenarios"):
        availability["scenario_frontier"] = "available"
    if payload.get("cost_pressure"):
        availability["cost_pressure"] = "available" if scheme_context.get("cost_pressure_modelled") else "degraded"
    return availability


def validate_report_structure(report: dict[str, Any]) -> list[str]:
    """Structural QA: every material statement classified; probabilities carry the 8 fields."""
    errors: list[str] = []
    for key in ("as_of", "scheme_id", "modules", "statements"):
        if key not in report:
            errors.append(f"report missing key: {key}")
    for index, statement in enumerate(report.get("statements", [])):
        if not isinstance(statement, dict) or statement.get("classification") not in STATEMENT_CLASSES:
            errors.append(f"statements[{index}] missing valid classification")
        if statement.get("classification") == "model_estimate" and "estimate" in statement and "horizon" not in statement:
            errors.append(f"statements[{index}] model estimate without horizon")
    for index, prob in enumerate(report.get("probabilities", [])):
        missing = [field for field in
                   ("event", "horizon", "clock_origin", "information_snapshot", "estimate",
                    "uncertainty", "model_version", "coverage_limitation") if field not in prob]
        if missing:
            errors.append(f"probabilities[{index}] missing: {missing}")
    return errors
