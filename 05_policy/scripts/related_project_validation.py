"""Conservative related-project grouping for leakage and robustness diagnostics."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold


def _key(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def build_related_project_group(
    frame: pd.DataFrame,
    explicit_group_by_case: dict[str, str] | None = None,
) -> pd.Series:
    """Scope SiteId by authority; missing IDs deliberately become singleton case groups."""
    groups: list[str] = []
    explicit_group_by_case = explicit_group_by_case or {}
    for row_number, (_, row) in enumerate(frame.iterrows()):
        authority = _key(row.get("PlanningAuthority"))
        site_id = _key(row.get("SiteId"))
        case_key = _key(row.get("case_key"))
        if case_key in explicit_group_by_case:
            groups.append(explicit_group_by_case[case_key])
        elif site_id:
            groups.append(f"site:{authority}::{site_id}")
        else:
            groups.append(f"case:{case_key or row_number}")
    return pd.Series(groups, index=frame.index, name="related_project_group")


def split_temporal_related_project_scores(
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    explicit_group_by_case: dict[str, str] | None = None,
) -> dict[str, object]:
    """Label a temporal holdout by whether its authority-scoped site group was seen earlier."""
    train_groups = set(build_related_project_group(train, explicit_group_by_case).tolist())
    scored = holdout.copy()
    scored["related_project_group"] = build_related_project_group(scored, explicit_group_by_case)
    scored["seen_before"] = scored["related_project_group"].isin(train_groups)
    counts = scored["seen_before"].map({True: "seen_before", False: "unseen"}).value_counts()
    return {
        "scored": scored,
        "seen_before": scored["seen_before"],
        "group_status_counts": {
            "seen_before": int(counts.get("seen_before", 0)),
            "unseen": int(counts.get("unseen", 0)),
        },
    }


def binary_score_metrics(target: pd.Series, score: pd.Series) -> dict[str, float | int | str]:
    y = pd.to_numeric(target, errors="coerce")
    p = pd.to_numeric(score, errors="coerce")
    valid = y.notna() & p.notna()
    y = y[valid].astype(int)
    p = p[valid].clip(1e-6, 1 - 1e-6)
    result: dict[str, float | int | str | None] = {"n": int(len(y)), "refusal_rate": float(y.mean()) if len(y) else None}
    if len(y) == 0:
        return {**result, "status": "no_scored_rows"}
    result.update({"brier": float(brier_score_loss(y, p)), "log_loss": float(log_loss(y, p, labels=[0, 1]))})
    if y.nunique() != 2:
        return {**result, "status": "only_one_class"}
    return {
        **result,
        "status": "ok",
        "roc_auc": float(roc_auc_score(y, p)),
        "average_precision": float(average_precision_score(y, p)),
    }


def group_kfold_summary(
    frame: pd.DataFrame,
    n_splits: int = 5,
    explicit_group_by_case: dict[str, str] | None = None,
) -> list[dict[str, int]]:
    """Describe reproducible, non-overlapping related-project folds for future candidates.

    scikit-learn 1.6 GroupKFold guarantees each group appears in one test fold:
    https://scikit-learn.org/1.6/modules/generated/sklearn.model_selection.GroupKFold.html
    """
    groups = build_related_project_group(frame, explicit_group_by_case)
    distinct_groups = int(groups.nunique())
    if distinct_groups < 2:
        return []
    splitter = GroupKFold(n_splits=min(n_splits, distinct_groups), shuffle=True, random_state=42)
    rows: list[dict[str, int]] = []
    values = np.zeros(len(frame))
    for fold, (train_index, test_index) in enumerate(splitter.split(values, groups=groups)):
        train_groups = set(groups.iloc[train_index])
        test_groups = set(groups.iloc[test_index])
        if train_groups & test_groups:
            raise AssertionError("related-project group leaked across GroupKFold split")
        rows.append({"fold": fold, "train_rows": int(len(train_index)), "test_rows": int(len(test_index)), "test_groups": int(len(test_groups))})
    return rows
