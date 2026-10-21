"""Monthly, quarterly and cumulative temporal robustness for the frozen v3 model."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

SCORE_COLUMNS = {
    "ranking": "v3_ranking_score",
    "calibrated": "v3_platt_risk",
}


def metric_block(y: pd.Series, p: pd.Series) -> dict[str, float | None]:
    """Discrimination/calibration metrics; None when the block is single-class."""
    values = pd.to_numeric(p, errors="coerce")
    labels = pd.to_numeric(y, errors="coerce")
    mask = values.notna() & labels.notna()
    values, labels = values[mask].astype(float), labels[mask].astype(int)
    if len(labels) == 0 or labels.nunique() < 2:
        return {"roc_auc": None, "average_precision": None, "brier": None}
    clipped = np.clip(values.to_numpy(), 1e-6, 1 - 1e-6)
    return {
        "roc_auc": float(roc_auc_score(labels, clipped)),
        "average_precision": float(average_precision_score(labels, clipped)),
        "brier": float(brier_score_loss(labels, clipped)),
    }


def block_summary(frame: pd.DataFrame, block_label: str) -> dict[str, Any]:
    """Summarise one temporal block for both score tracks."""
    row: dict[str, Any] = {
        "window": block_label,
        "rows": int(len(frame)),
        "refusal_rate": None if frame.empty else float(pd.to_numeric(frame["target_refused"], errors="coerce").mean()),
    }
    if frame.empty:
        return row
    for track, column in SCORE_COLUMNS.items():
        metrics = metric_block(frame["target_refused"], frame[column])
        row[f"{track}_roc_auc"] = metrics["roc_auc"]
        row[f"{track}_average_precision"] = metrics["average_precision"]
        row[f"{track}_brier"] = metrics["brier"]
    return row


def window_summaries(predictions: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Monthly, quarterly and cumulative windows over the 2025 prospective year."""
    frame = predictions.copy()
    frame["received_date_dt"] = pd.to_datetime(frame["received_date_dt"], utc=True, errors="coerce")
    frame = frame[frame["received_date_dt"].notna()].copy()
    rows: list[dict[str, Any]] = []
    periods = pd.unique(frame["received_date_dt"].dt.to_period("M").dropna())
    for period in sorted(periods):
        block = frame[frame["received_date_dt"].dt.to_period("M") == period]
        rows.append(block_summary(block, str(period)))
    for start_month in (1, 4, 7, 10):
        start = pd.Timestamp(year=2025, month=start_month, day=1, tz="UTC")
        end = start + pd.DateOffset(months=3)
        block = frame[(frame["received_date_dt"] >= start) & (frame["received_date_dt"] < end)]
        rows.append(block_summary(block, f"Q{start.month // 3 + 1}_2025"))
    ordered = frame.sort_values("received_date_dt")
    for cutoff_month in (3, 6, 9, 12):
        cutoff = pd.Timestamp(year=2025, month=cutoff_month, day=1, tz="UTC") + pd.offsets.MonthEnd(0)
        block = ordered[ordered["received_date_dt"] <= cutoff]
        rows.append(block_summary(block, f"cumulative_to_{cutoff_month:02d}"))
    summary = pd.DataFrame(rows)
    skipped = {
        "single_class_blocks": [
            row["window"] for row in rows if row.get("ranking_roc_auc") is None and row["rows"] > 0
        ],
        "small_blocks_under_100_rows": [
            row["window"] for row in rows if 0 < row["rows"] < 100
        ],
        "caveat": "Blocks are frozen-model scores on time-safe features; a block is not a retrained rolling model.",
    }
    return summary, [{"window_summary": rows, **skipped}]
