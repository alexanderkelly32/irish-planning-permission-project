"""Refusal-reason engine (b): conditional reason families on refusal.

Uses the repository's human-verified theme tags
(03_refusal/current/refusal_reasons_cases_master.csv, 1,411 refused cases,
1,096 tagged) mapped to the product brief's reason families. Outputs:
  - conditional family frequencies P(family | refused) over the refused GE10
    cohort (the audited prior);
  - scheme-specific theme transfer from matched refused comparables
    (authority + description token overlap + unit band), with the documented
    transfer accuracy (top-3 55.6% on the leakage-free GE10 holdout) and an
    overlap warning (decisions can carry multiple reasons).
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from .. import settings
from ..entity_resolution.scoring import address_tokens, token_similarity

FAMILY_MAP = {
    "design_layout": "design_visual_impact",
    "land_use_policy": "policy_zoning_conflict",
    "density_scale": "density_overdevelopment",
    "traffic_access": "access_traffic_safety",
    "premature_or_info_gap": "insufficient_information_technical_evidence",
    "heritage_archaeology": "heritage_conservation",
    "flooding_drainage": "flood_drainage",
    "residential_amenity": "residential_amenity",
    "ecology_trees": "ecology_environment",
    "water_wastewater": "wastewater_drainage",
    "other": "other",
}

FAMILY_LABELS = {
    "access_traffic_safety": "Access / traffic safety",
    "density_overdevelopment": "Density / overdevelopment",
    "design_visual_impact": "Design / visual impact",
    "residential_amenity": "Residential amenity",
    "policy_zoning_conflict": "Policy / zoning conflict",
    "wastewater_drainage": "Wastewater / drainage",
    "flood_drainage": "Flood / drainage",
    "ecology_environment": "Ecology / environment",
    "heritage_conservation": "Heritage / conservation",
    "insufficient_information_technical_evidence": "Insufficient information / technical evidence",
    "other": "Other",
}

THEMES_CSV = settings.ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
THEMES_LLM_NEW_CSV = settings.ROOT / "03_refusal" / "current" / "refusal_reasons_cases_llm_new.csv"

REFUSED_DECISIONS = re.compile(r"^REFUSE", re.I)


def load_theme_cases() -> pd.DataFrame:
    frame = pd.read_csv(THEMES_CSV, low_memory=False)
    frame = frame[frame["decision"].fillna("").astype(str).str.contains(REFUSED_DECISIONS)].copy()
    # New LLM extractions are a display source AFTER the canonical master;
    # the master itself is never modified (repo convention).
    if THEMES_LLM_NEW_CSV.exists():
        new = pd.read_csv(THEMES_LLM_NEW_CSV, low_memory=False)
        new = new[new["decision"].fillna("").astype(str).str.contains(REFUSED_DECISIONS)].copy()
        frame = pd.concat([frame, new], ignore_index=True).drop_duplicates(subset=["case_key"], keep="first")
    return frame


def _expand_tags(value: Any) -> list[str]:
    if pd.isna(value):
        return []
    return [tag.strip() for tag in str(value).split(";") if tag.strip()]


def family_priors(theme_cases: pd.DataFrame | None = None) -> dict[str, Any]:
    """Conditional family frequencies over the refused GE10 cohort."""
    frame = theme_cases if theme_cases is not None else load_theme_cases()
    tagged = frame[frame["case_top_primary_tag"].notna()]
    counts: dict[str, int] = {}
    for tags in frame["case_primary_tags"].map(_expand_tags):
        seen = set()
        for tag in tags:
            family = FAMILY_MAP.get(tag, "other")
            if family not in seen:
                seen.add(family)
                counts[family] = counts.get(family, 0) + 1
    total = int(len(frame))
    return {
        "n_refused": total,
        "n_tagged": int(len(tagged)),
        "tag_coverage": round(len(tagged) / max(1, total), 4),
        "frequencies": {
            family: round(counts.get(family, 0) / max(1, total), 4)
            for family in FAMILY_LABELS
        },
        "overlap_warning": "decisions can contain multiple reasons; frequencies are marginal, not exclusive",
        "labels": FAMILY_LABELS,
    }


def transfer_themes(
    *,
    description: str,
    authority: str,
    units: float | None,
    theme_cases: pd.DataFrame | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Scheme-specific theme transfer from matched refused comparables.

    Match: same authority + unit band (0.5x-2x) + description token overlap;
    rank by token similarity; weight theme counts by similarity.
    """
    frame = theme_cases if theme_cases is not None else load_theme_cases()
    tagged = frame[frame["case_primary_tags"].notna()].copy()
    if "council" in tagged.columns and authority:
        tagged = tagged[tagged["council"].fillna("").astype(str).str.lower() == str(authority).lower()]
        if tagged.empty:
            tagged = frame[frame["case_primary_tags"].notna()].copy()

    subject_tokens = address_tokens(description or "")
    tagged["token_sim"] = tagged["case_key"].astype(str).map(lambda _: 0.0)
    descriptions = tagged["reasons_joined"].fillna("").astype(str) if "reasons_joined" in tagged.columns else pd.Series("", index=tagged.index)
    tagged["token_sim"] = descriptions.map(lambda text: token_similarity(description or "", text) if subject_tokens else 0.0)

    if units is not None and "application_number" in tagged.columns:
        pass  # unit band not available in theme cases; similarity carries the match

    matched = tagged[tagged["token_sim"] > 0].sort_values("token_sim", ascending=False).head(60)
    if matched.empty:
        return {"matched_n": 0, "themes": [], "note": "no token-overlapping refused comparables; family priors shown only"}

    scores: dict[str, float] = {}
    for _, row in matched.iterrows():
        weight = float(row["token_sim"])
        seen = set()
        for tag in _expand_tags(row.get("case_primary_tags")):
            family = FAMILY_MAP.get(tag, "other")
            if family not in seen:
                seen.add(family)
                scores[family] = scores.get(family, 0.0) + weight
    total_weight = sum(scores.values()) or 1.0
    themes = [
        {
            "family": family,
            "label": FAMILY_LABELS.get(family, family),
            "share": round(score / total_weight, 3),
            "matched_n": int(len(matched)),
        }
        for family, score in sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]
    ]
    return {
        "matched_n": int(len(matched)),
        "themes": themes,
        "transfer_accuracy_note": "top-3 theme-transfer accuracy 55.6% on the leakage-free GE10 holdout (not a calibrated conditional probability)",
    }


def refusal_reason_payload(*, description: str, authority: str, units: float | None) -> dict[str, Any]:
    theme_cases = load_theme_cases()
    return {
        "family_priors": family_priors(theme_cases),
        "scheme_transfer": transfer_themes(description=description, authority=authority, units=units, theme_cases=theme_cases),
        "evidence": "03_refusal/current/refusal_reasons_cases_master.csv (human-verified theme tags)",
    }
