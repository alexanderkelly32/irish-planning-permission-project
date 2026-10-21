"""Independent double-review slice and adjudication for revision-linkage labels."""
from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

REQUIRED_PILOT_COLUMNS = {
    "original_case_key",
    "revised_case_key",
    "linkage_tier",
    "manual_review_status",
}
RESOLVED_STATUSES = {"accepted", "rejected"}
TIERS = ("high", "medium", "low")
REVIEWER_B_COLUMNS = [
    "double_review_status",
    "double_review_notes",
    "reviewer_b",
    "reviewed_at_b",
]
MASKED_COLUMNS = {
    "manual_review_status",
    "manual_review_notes",
    "reviewer",
    "reviewed_at",
}


def _pair_hash(original: object, revised: object, tier: object, seed: int) -> str:
    payload = f"{seed}|{tier}|{original}|{revised}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_double_review_slice(
    pilot: pd.DataFrame,
    per_tier: int = 8,
    seed: int = 20260902,
) -> pd.DataFrame:
    """Select a deterministic stratified subset of resolved pilot rows for a second reviewer.

    Reviewer-A labels are masked so the second review stays independent.
    """
    missing = REQUIRED_PILOT_COLUMNS.difference(pilot.columns)
    if missing:
        raise ValueError(f"pilot sheet is missing columns: {', '.join(sorted(missing))}")
    frame = pilot.copy()
    frame["manual_review_status"] = (
        frame["manual_review_status"].fillna("pending").astype(str).str.strip().str.lower()
    )
    resolved = frame[frame["manual_review_status"].isin(RESOLVED_STATUSES)].copy()
    selected: list[pd.DataFrame] = []
    for tier in TIERS:
        group = resolved[resolved["linkage_tier"].astype(str).str.lower() == tier].copy()
        if group.empty:
            continue
        group["_review_order"] = [
            _pair_hash(original, revised, tier, seed)
            for original, revised in zip(
                group["original_case_key"].tolist(),
                group["revised_case_key"].tolist(),
                strict=False,
            )
        ]
        selected.append(
            group.sort_values("_review_order", kind="mergesort")
            .head(min(per_tier, len(group)))
            .drop(columns="_review_order")
        )
    if not selected:
        return resolved.iloc[0:0].drop(columns=[c for c in MASKED_COLUMNS if c in resolved.columns]).copy()
    slice_df = pd.concat(selected, ignore_index=True)
    for column in REVIEWER_B_COLUMNS:
        slice_df[column] = ""
    return slice_df.drop(columns=[column for column in MASKED_COLUMNS if column in slice_df.columns])


def merge_double_review(
    pilot: pd.DataFrame,
    reviewer_b: pd.DataFrame,
) -> pd.DataFrame:
    """Join the second reviewer's labels with the original ones and flag disagreements.

    Disagreements and unresolved second-review rows are never auto-resolved: they are
    flagged for manual adjudication.
    """
    missing = REQUIRED_PILOT_COLUMNS.difference(pilot.columns)
    if missing:
        raise ValueError(f"pilot sheet is missing columns: {', '.join(sorted(missing))}")
    required_b = {"original_case_key", "revised_case_key", "double_review_status"}.difference(reviewer_b.columns)
    if required_b:
        raise ValueError(f"reviewer B sheet is missing columns: {', '.join(sorted(required_b))}")
    a = pilot.copy()
    a["manual_review_status"] = a["manual_review_status"].fillna("pending").astype(str).str.strip().str.lower()
    a = a[a["manual_review_status"].isin(RESOLVED_STATUSES)]
    b = reviewer_b.copy()
    b["double_review_status"] = b["double_review_status"].fillna("pending").astype(str).str.strip().str.lower()
    merged = a.merge(
        b[["original_case_key", "revised_case_key", "double_review_status", "double_review_notes"]],
        on=["original_case_key", "revised_case_key"],
        how="left",
        suffixes=("", "_b"),
    )
    merged["in_slice"] = merged["double_review_status"].notna()
    merged["reviewer_b_resolved"] = merged["double_review_status"].isin(RESOLVED_STATUSES)
    merged["agreement"] = (
        merged["reviewer_b_resolved"]
        & (merged["manual_review_status"] == merged["double_review_status"])
    )
    merged["adjudication_required"] = merged["in_slice"] & ~merged["agreement"]
    merged["adjudicated_status"] = ""
    merged["adjudication_notes"] = ""
    merged["adjudicator"] = ""
    merged["adjudicated_at"] = ""
    columns = [
        "original_case_key",
        "revised_case_key",
        "planning_authority",
        "original_application_number",
        "revised_application_number",
        "linkage_tier",
        "linkage_score",
        "manual_review_status",
        "manual_review_notes",
        "double_review_status",
        "double_review_notes",
        "in_slice",
        "reviewer_b_resolved",
        "agreement",
        "adjudication_required",
        "adjudicated_status",
        "adjudication_notes",
        "adjudicator",
        "adjudicated_at",
    ]
    return merged[[column for column in columns if column in merged.columns]].reset_index(drop=True)


def summarize_double_review(adjudication: pd.DataFrame) -> dict[str, Any]:
    """Agreement summary by tier; disagreement rows remain open for adjudication."""
    if adjudication.empty:
        return {
            "row_count": 0,
            "double_reviewed_count": 0,
            "reviewer_b_resolved_count": 0,
            "agreement_count": 0,
            "disagreement_count": 0,
            "pending_by_b_count": 0,
            "agreement_rate": None,
            "by_tier": {},
        }
    resolved_b = int(adjudication["reviewer_b_resolved"].sum())
    agreements = int(adjudication["agreement"].sum())
    disagreements = int((adjudication["reviewer_b_resolved"] & ~adjudication["agreement"]).sum())
    pending_by_b = int((adjudication["in_slice"] & ~adjudication["reviewer_b_resolved"]).sum())
    by_tier: dict[str, dict[str, object]] = {}
    for tier, group in adjudication.groupby("linkage_tier"):
        resolved = int(group["reviewer_b_resolved"].sum())
        agreed = int(group["agreement"].sum())
        by_tier[str(tier)] = {
            "rows": int(len(group)),
            "double_reviewed": int(group["in_slice"].sum()),
            "reviewer_b_resolved": resolved,
            "agreements": agreed,
            "disagreements": int((group["reviewer_b_resolved"] & ~group["agreement"]).sum()),
            "pending_by_b": int((group["in_slice"] & ~group["reviewer_b_resolved"]).sum()),
            "agreement_rate": round(agreed / resolved, 4) if resolved else None,
        }
    return {
        "row_count": int(len(adjudication)),
        "double_reviewed_count": int(adjudication["in_slice"].sum()),
        "reviewer_b_resolved_count": resolved_b,
        "agreement_count": agreements,
        "disagreement_count": disagreements,
        "pending_by_b_count": pending_by_b,
        "adjudication_required_count": int(adjudication["adjudication_required"].sum()),
        "agreement_rate": round(agreements / resolved_b, 4) if resolved_b else None,
        "by_tier": by_tier,
        "note": (
            "Agreement is a reviewer-consistency check only. It does not validate any pair "
            "against source documents and is never used to auto-accept linkage candidates."
        ),
    }
