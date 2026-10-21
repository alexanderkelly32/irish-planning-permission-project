"""Model-driver explanation for the frozen v4-full planning model
(product brief 6.4 — "Where did this number come from?").

Extracts exact native-scale (log-odds) contributions from the frozen
LogisticRegression, groups sparse text features into traceable themes,
computes one-at-a-time counterfactuals (labelled sensitivity, never summed as
independent), and exposes the calibration mapping. Every driver row carries
its feature, subject value, contribution, direction and feature group; the
narrative generator must not invent drivers absent from this payload.
"""
from __future__ import annotations

import re
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .. import settings

FEATURE_GROUPS = {
    "description_text": {"pattern": re.compile(r"^txt__"), "label": "Description text"},
    "authority_type": {"pattern": re.compile(r"^cat__"), "label": "Authority and application type"},
    "comparables": {"pattern": re.compile(r"^comp_"), "label": "Comparable applications"},
    "flood": {"pattern": re.compile(r"^(flood|coastal|fluvial)"), "label": "Flood and coastal context"},
    "plan_themes": {"pattern": re.compile(r"^(plan_theme|log_plan|policy_plan)"), "label": "Development-plan themes"},
    "history_context": {"pattern": re.compile(r"^(log_|.*prior.*|.*_refusal_rate|.*_count|applicant_)"), "label": "Planning history context"},
    "density_design": {"pattern": re.compile(r"^(density|floor_area|site_sqm|avg_unit|landuse)"), "label": "Density and design"},
    "demographics": {"pattern": re.compile(r"^(log_pop_density|owner_share|private_rent_share|la_rent_share|septic_share|cars_per_hh|no_car_share|is_urban)"), "label": "Area demographics"},
    "scheme_scale": {"pattern": re.compile(r"^(log_units|log_site_area_sqm|log_floor_area_sqm|units_missing|received_year)"), "label": "Scheme scale and vintage"},
    "other": {"pattern": re.compile(r"."), "label": "Other structured features"},
}


def load_artifact():
    artifact = joblib.load(settings.FROZEN_MODEL_JOBLIB)
    return artifact


def _text_token_from_name(name: str) -> str:
    return name.split("__", 1)[1] if "__" in name else name


def _group_of(name: str) -> str:
    for group, spec in FEATURE_GROUPS.items():
        if spec["pattern"].match(name):
            return group
    return "other"


def explain(proposal: dict[str, Any], artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    """Native-scale contribution payload for one proposal.

    proposal: the same dict consumed by the frozen model (authority,
    description, units, site_area_sqm, floor_area_sqm, itm coords, year).
    Returns the structured payload required by brief 6.4.
    """
    from model_feature_builder import build_feature_row, score_proposal

    artifact = artifact or load_artifact()
    preprocessor = artifact["ranking_model"].named_steps[next(iter(artifact["ranking_model"].named_steps))]
    classifier = artifact["ranking_model"].named_steps[list(artifact["ranking_model"].named_steps.keys())[-1]]

    frame = build_feature_row(proposal)
    input_frame = frame[artifact["feature_columns"]]
    transformed = preprocessor.transform(input_frame)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    feature_names = preprocessor.get_feature_names_out()

    coefs = np.asarray(classifier.coef_).ravel()
    contributions = coefs * transformed.ravel()
    logit = float(np.sum(contributions) + classifier.intercept_[0])
    raw_score = float(1.0 / (1.0 + np.exp(-logit)))

    rows = []
    for name, value, contribution in zip(feature_names, transformed.ravel(), contributions, strict=False):
        if abs(contribution) < 1e-12:
            continue
        rows.append({
            "feature": str(name),
            "group": _group_of(name),
            "contribution_log_odds": round(float(contribution), 6),
            "subject_value": round(float(value), 6),
            "token": _text_token_from_name(name) if name.startswith("txt__") else None,
        })
    table = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["feature", "group", "contribution_log_odds", "subject_value", "token"])

    groups = {}
    for group, part in table.groupby("group"):
        groups[group] = {
            "label": FEATURE_GROUPS[group]["label"],
            "net_contribution_log_odds": round(float(part["contribution_log_odds"].sum()), 6),
            "n_features": int(len(part)),
        }

    top_up = table.nlargest(10, "contribution_log_odds").to_dict(orient="records")
    top_down = table.nsmallest(10, "contribution_log_odds").to_dict(orient="records")

    counterfactuals = []
    for group, spec in FEATURE_GROUPS.items():
        mask = np.array([_group_of(str(name)) == group for name in feature_names])
        if not mask.any():
            continue
        reduced = float(np.sum(contributions[~mask]) + classifier.intercept_[0])
        reduced_score = float(1.0 / (1.0 + np.exp(-reduced)))
        counterfactuals.append({
            "group": group,
            "label": spec["label"],
            "removed_log_odds": round(float(np.sum(contributions[mask])), 6),
            "raw_score_without_group": round(reduced_score, 4),
            "raw_score_delta_pp": round((raw_score - reduced_score) * 100, 2),
            "sensitivity_label": "one-at-a-time counterfactual; not a causal claim",
        })

    scored = score_proposal(proposal)
    payload = {
        "native_logit": round(logit, 6),
        "raw_ranking_score": round(raw_score, 6),
        "calibrated_probability": scored["refusal_probability"],
        "risk_band": scored["risk_band"],
        "intercept": round(float(classifier.intercept_[0]), 6),
        "group_contributions": groups,
        "top_raising": top_up,
        "top_lowering": top_down,
        "counterfactuals": counterfactuals,
        "model_version": artifact["model_version"],
        "feature_count": int(len(feature_names)),
    }
    return payload


def narrative_facts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic driver facts for the narrative (brief 6.4 questions)."""
    facts = []
    raising = [row for row in payload["top_raising"] if row["group"] == "description_text"][:3]
    for row in raising:
        facts.append({
            "claim": f"description token '{row['token']}' raised the model estimate",
            "contribution_log_odds": row["contribution_log_odds"],
            "evidence": "description text (TF-IDF feature)",
            "class": "model_estimate",
        })
    for group, info in payload["group_contributions"].items():
        facts.append({
            "claim": f"{info['label']} group net contribution {info['net_contribution_log_odds']:+.4f} log-odds",
            "contribution_log_odds": info["net_contribution_log_odds"],
            "evidence": "native-scale model contribution",
            "class": "model_estimate",
        })
    return facts
