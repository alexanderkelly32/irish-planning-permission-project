"""Conservative labelled candidate-ranking evaluation for revision linkage.

Ground truth is the manually labelled subset of the candidate queue (pilot review
plus the earlier audit). The labels are an audit convenience, not a random sample:
the pilot was tier-stratified and the audit came from the earlier narrow queue.
All metrics below are therefore reported for the labelled subset only, and no
threshold auto-accepts candidates.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import StratifiedKFold

LABEL_COLUMN = "manual_review_status"
RESOLVED_STATUSES = {"accepted", "rejected"}
TIERS = ("high", "medium", "low")

FEATURE_SPEC = {
    "linkage_score": "numeric",
    "coordinate_distance_m": "numeric",
    "description_similarity": "numeric",
    "gap_days": "numeric",
    "applicant_match": "boolean",
    "postcode_match": "boolean",
    "has_units_delta": "derived",
    "abs_units_delta": "derived",
    "blocking_exact_address": "derived",
    "blocking_spatial_50m": "derived",
    "tier_ordinal": "derived",
}


def build_labelled_frame(queue: pd.DataFrame) -> pd.DataFrame:
    """Extract the manually resolved rows with model-ready features."""
    required = {
        "original_case_key", "revised_case_key", "linkage_tier", "linkage_score",
        "manual_review_status", "coordinate_distance_m", "description_similarity",
        "gap_days", "applicant_match", "postcode_match", "units_delta",
        "blocking_methods",
    }
    missing = required.difference(queue.columns)
    if missing:
        raise ValueError(f"queue is missing columns: {', '.join(sorted(missing))}")
    frame = queue[queue[LABEL_COLUMN].fillna("pending").astype(str).str.strip().str.lower().isin(RESOLVED_STATUSES)].copy()
    if frame.empty:
        raise ValueError("no resolved manual-review labels in the queue")
    frame["target"] = frame[LABEL_COLUMN].astype(str).str.strip().str.lower().eq("accepted").astype(int)
    frame["has_units_delta"] = pd.to_numeric(frame["units_delta"], errors="coerce").notna().astype(int)
    frame["abs_units_delta"] = pd.to_numeric(frame["units_delta"], errors="coerce").abs().fillna(0.0)
    block = frame["blocking_methods"].fillna("").astype(str)
    frame["blocking_exact_address"] = block.str.contains("exact_address", na=False).astype(int)
    frame["blocking_spatial_50m"] = block.str.contains("spatial", na=False).astype(int)
    frame["tier_ordinal"] = frame["linkage_tier"].astype(str).str.lower().map({"high": 3, "medium": 2, "low": 1}).fillna(1).astype(int)
    return frame.reset_index(drop=True)


MODEL_COLUMNS = [
    "linkage_score", "coordinate_distance_m", "description_similarity", "gap_days",
    "applicant_match", "postcode_match", "has_units_delta", "abs_units_delta",
    "blocking_exact_address", "blocking_spatial_50m", "tier_ordinal",
]
HEURISTIC_COLUMNS = [column for column in MODEL_COLUMNS if column not in {"linkage_score", "tier_ordinal"}]


def _feature_matrix(frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    values = frame[columns].copy()
    for column in ("coordinate_distance_m", "gap_days", "abs_units_delta"):
        values[column] = np.log1p(pd.to_numeric(values[column], errors="coerce").fillna(0.0))
    for column in columns:
        values[column] = pd.to_numeric(values[column], errors="coerce").fillna(0.0)
    return values.to_numpy(dtype=float)


def _tier_metrics(preds: np.ndarray, labels: np.ndarray, tiers: np.ndarray, threshold: float) -> dict[str, dict[str, Any]]:
    by_tier: dict[str, dict[str, Any]] = {}
    for tier in TIERS:
        mask = tiers == tier
        if not mask.any():
            continue
        y, p = labels[mask], preds[mask]
        precision, recall, _, _ = precision_recall_fscore_support(y, (p >= threshold).astype(int), labels=[0, 1], zero_division=0)
        by_tier[tier] = {
            "rows": int(mask.sum()),
            "accepted": int(y.sum()),
            "precision": round(float(precision[1]), 4),
            "recall": round(float(recall[1]), 4),
        }
    return by_tier


def evaluate_labelled_ranking(
    frame: pd.DataFrame,
    n_splits: int = 5,
    seed: int = 20260902,
) -> dict[str, Any]:
    """Repeated stratified holdout evaluation over the labelled rows only."""
    if frame.empty or frame["target"].nunique() < 2:
        return {"status": "insufficient_labels", "labelled_row_count": int(len(frame))}
    x_all = _feature_matrix(frame, MODEL_COLUMNS)
    x_heur = _feature_matrix(frame, HEURISTIC_COLUMNS)
    y_all = frame["target"].to_numpy(dtype=int)
    tiers = frame["linkage_tier"].astype(str).str.lower().to_numpy()
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    fold_results: list[dict[str, Any]] = []
    for fold, (train_idx, test_idx) in enumerate(skf.split(x_all, y_all)):
        model = LogisticRegression(max_iter=2000, class_weight="balanced")
        model.fit(x_all[train_idx], y_all[train_idx])
        probs = model.predict_proba(x_all[test_idx])[:, 1]
        threshold = _train_f1_threshold(model.predict_proba(x_all[train_idx])[:, 1], y_all[train_idx])
        preds = (probs >= threshold).astype(int)
        precision, recall, _, _ = precision_recall_fscore_support(y_all[test_idx], preds, labels=[0, 1], zero_division=0)
        heuristic = LogisticRegression(max_iter=2000, class_weight="balanced")
        heuristic.fit(x_heur[train_idx], y_all[train_idx])
        heuristic_probs = heuristic.predict_proba(x_heur[test_idx])[:, 1]
        fold_results.append({
            "fold": int(fold),
            "test_rows": int(len(test_idx)),
            "test_accepted": int(y_all[test_idx].sum()),
            "roc_auc": round(roc_auc_score(y_all[test_idx], probs), 4),
            "average_precision": round(average_precision_score(y_all[test_idx], probs), 4),
            "precision": round(float(precision[1]), 4),
            "recall": round(float(recall[1]), 4),
            "threshold": round(float(threshold), 4),
            "roc_auc_without_score_or_tier": round(roc_auc_score(y_all[test_idx], heuristic_probs), 4),
            "tier_metrics": _tier_metrics(probs, y_all[test_idx], tiers[test_idx], threshold),
        })
    return {
        "status": "evaluated",
        "labelled_row_count": int(len(frame)),
        "accepted_row_count": int(y_all.sum()),
        "rejected_row_count": int(len(frame) - int(y_all.sum())),
        "n_splits": n_splits,
        "seed": seed,
        "fold_results": fold_results,
        "fold_aggregates": _fold_aggregates(fold_results),
        "tier_aggregates": _tier_aggregates(fold_results),
        "caveats": [
            "Labels come from the tier-stratified pilot and the earlier narrow-queue audit; they are not a random sample of the queue.",
            "Metrics describe the labelled subset only and are not national recall/precision estimates.",
            "No threshold auto-accepts candidates; ranking diagnostics inform review prioritisation only.",
        ],
    }


def _fold_aggregates(fold_results: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ["roc_auc", "average_precision", "precision", "recall", "roc_auc_without_score_or_tier"]
    values: dict[str, list[float]] = {key: [float(fold[key]) for fold in fold_results if fold.get(key) is not None] for key in keys}

    def stats(series: list[float]) -> dict[str, float | None]:
        if not series:
            return {"mean": None, "min": None, "max": None}
        return {
            "mean": round(float(np.mean(series)), 4),
            "min": round(float(min(series)), 4),
            "max": round(float(max(series)), 4),
        }

    return {key: stats(series) for key, series in values.items()}


def _tier_aggregates(fold_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = {}
    for tier in TIERS:
        rows: list[int] = []
        accepted: list[int] = []
        precision: list[float] = []
        recall: list[float] = []
        for fold in fold_results:
            metrics = fold.get("tier_metrics", {}).get(tier)
            if metrics is None:
                continue
            rows.append(int(metrics["rows"]))
            accepted.append(int(metrics["accepted"]))
            precision.append(float(metrics["precision"]))
            recall.append(float(metrics["recall"]))
        total_rows = sum(rows)
        total_accepted = sum(accepted)
        aggregates[tier] = {
            "fold_rows_total": total_rows,
            "fold_accepted_total": total_accepted,
            "mean_precision": round(float(np.mean(precision)), 4) if precision else None,
            "mean_recall": round(float(np.mean(recall)), 4) if recall else None,
        }
    return aggregates


def _train_f1_threshold(probs: np.ndarray, labels: np.ndarray) -> float:
    best, best_score = 0.5, -1.0
    for threshold in np.linspace(0.05, 0.95, 19):
        preds = (probs >= threshold).astype(int)
        _, _, f1, _ = precision_recall_fscore_support(labels, preds, zero_division=0)
        if f1[1] > best_score:
            best, best_score = threshold, float(f1[1])
    return best


def review_order_analysis(queue: pd.DataFrame) -> dict[str, Any]:
    """Where accepted manual labels surface in the tier-then-score review order."""
    ordered = queue.copy()
    tier_order = {"high": 0, "medium": 1, "low": 2}
    ordered["_tier_order"] = ordered["linkage_tier"].astype(str).str.lower().map(tier_order).fillna(3)
    ordered = ordered.sort_values(["_tier_order", "linkage_score"], ascending=[True, False]).reset_index(drop=True)
    labelled = ordered[ordered[LABEL_COLUMN].fillna("pending").astype(str).str.strip().str.lower().isin(RESOLVED_STATUSES)].copy()
    labelled["accepted"] = labelled[LABEL_COLUMN].astype(str).str.strip().str.lower().eq("accepted")
    accepted_positions = labelled.index[labelled["accepted"]].to_numpy()
    rejected_positions = labelled.index[~labelled["accepted"]].to_numpy()
    total = max(len(ordered), 1)

    def share_at(percentile: float) -> float:
        cutoff = max(int(total * percentile) - 1, 0)
        found = float((accepted_positions <= cutoff).sum())
        return round(found / len(accepted_positions), 4) if len(accepted_positions) else 0.0

    by_tier: dict[str, dict[str, Any]] = {}
    for tier in TIERS:
        subset = labelled[labelled["linkage_tier"].astype(str).str.lower() == tier]
        accepted = subset[subset["accepted"]]
        positions = accepted.index.to_numpy()
        tier_total = int((ordered["linkage_tier"].astype(str).str.lower() == tier).sum()) or 1
        median_rank = float(np.median(positions) + 1) if len(positions) else None
        by_tier[tier] = {
            "labelled_rows": int(len(subset)),
            "accepted_rows": int(len(accepted)),
            "median_rank_in_queue": int(median_rank) if median_rank is not None else None,
            "median_share_rank": round(median_rank / tier_total, 4) if median_rank is not None else None,
        }
    return {
        "queue_row_count": int(len(ordered)),
        "labelled_row_count": int(len(labelled)),
        "accepted_label_count": int(labelled["accepted"].sum()),
        "rejected_label_count": int(len(labelled) - int(labelled["accepted"].sum())),
        "accepted_labels_found_in_top_1pct": share_at(0.01),
        "accepted_labels_found_in_top_5pct": share_at(0.05),
        "accepted_labels_found_in_top_10pct": share_at(0.10),
        "accepted_labels_found_in_top_20pct": share_at(0.20),
        "rejected_labels_median_rank": int(np.median(rejected_positions) + 1) if len(rejected_positions) else None,
        "by_tier": by_tier,
        "caveat": "Ranks are positions in the full queue ordered high-to-low tier then score; labelled rows are not a random sample.",
    }
