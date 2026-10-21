"""Council-aware probability calibration with minimum sample thresholds.

Evaluation protocol: fit calibrators on the first half of 2025 (prospective-style),
evaluate on the second half, and fall back to the national calibrator wherever a
council lacks the minimum sample size. This is a validation experiment only; the
frozen national model is never replaced by its outputs.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss


def _logits(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped)).reshape(-1, 1)


def _fit_platt(probabilities: np.ndarray, targets: np.ndarray) -> LogisticRegression | None:
    """Fit a Platt calibrator on logit inputs; None when both classes are absent."""
    labels = pd.Series(targets).dropna().astype(int)
    if labels.nunique() < 2:
        return None
    calibrator = LogisticRegression(C=1_000_000, solver="lbfgs", max_iter=1000)
    calibrator.fit(_logits(probabilities), labels.to_numpy())
    return calibrator


def _calibrate(probabilities: np.ndarray, calibrator: LogisticRegression | None) -> np.ndarray:
    if calibrator is None:
        return np.clip(probabilities, 1e-6, 1 - 1e-6)
    return calibrator.predict_proba(_logits(probabilities))[:, 1]


def fit_council_calibrators(
    frame: pd.DataFrame,
    authority_column: str = "PlanningAuthority",
    score_column: str = "v3_ranking_score",
    target_column: str = "target_refused",
    minimum_samples: int = 100,
) -> tuple[dict[str, LogisticRegression | None], LogisticRegression | None, dict[str, Any]]:
    """Fit national and per-council calibrators on the fitting window only."""
    probabilities = pd.to_numeric(frame[score_column], errors="coerce").to_numpy()
    targets = pd.to_numeric(frame[target_column], errors="coerce").to_numpy()
    national = _fit_platt(probabilities, targets)
    council_calibrators: dict[str, LogisticRegression | None] = {}
    diagnostics: dict[str, Any] = {"minimum_samples": minimum_samples, "councils_fitted": {}, "councils_fallback": []}
    for council, group in frame.groupby(authority_column):
        if len(group) < minimum_samples:
            diagnostics["councils_fallback"].append(str(council))
            continue
        calibrator = _fit_platt(
            pd.to_numeric(group[score_column], errors="coerce").to_numpy(),
            pd.to_numeric(group[target_column], errors="coerce").to_numpy(),
        )
        council_calibrators[str(council)] = calibrator
        diagnostics["councils_fitted"][str(council)] = {
            "rows": int(len(group)),
            "refusal_rate": float(pd.to_numeric(group[target_column], errors="coerce").mean()),
            "single_class_skipped": calibrator is None,
        }
    return council_calibrators, national, diagnostics


def evaluate_council_calibration(
    frame: pd.DataFrame,
    council_calibrators: dict[str, LogisticRegression | None],
    national: LogisticRegression | None,
    frozen_calibrated_column: str = "v3_platt_risk",
    authority_column: str = "PlanningAuthority",
    score_column: str = "v3_ranking_score",
    target_column: str = "target_refused",
) -> dict[str, Any]:
    """Compare council-aware calibration against national and frozen calibrations."""
    if frame.empty:
        return {
            "summary": {
                "eval_rows": 0,
                "eval_refusal_rate": None,
                "council_aware_brier": None,
                "national_fit_brier": None,
                "frozen_national_brier": None,
            },
            "by_council": {},
            "caveat": (
                "Calibrators are fitted on the first half of 2025 and evaluated on the second half "
                "(temporal holdout). This validates whether council-aware recalibration is worth "
                "maintaining; it does not replace the frozen national model."
            ),
        }
    targets = pd.to_numeric(frame[target_column], errors="coerce").to_numpy()
    probabilities = pd.to_numeric(frame[score_column], errors="coerce").to_numpy()
    council_risks = np.full(len(frame), np.nan)
    authorities = frame[authority_column].fillna("").astype(str).to_numpy()
    for index, authority in enumerate(authorities):
        calibrator = council_calibrators.get(authority, national)
        council_risks[index] = _calibrate(probabilities[index : index + 1], calibrator)[0]
    national_risks = _calibrate(probabilities, national)
    frozen_risks = np.clip(pd.to_numeric(frame[frozen_calibrated_column], errors="coerce").to_numpy(), 1e-6, 1 - 1e-6)
    mask = pd.notna(targets) & pd.notna(council_risks)
    summary = {
        "eval_rows": int(mask.sum()),
        "eval_refusal_rate": float(targets[mask].mean()) if mask.any() else None,
        "council_aware_brier": round(float(brier_score_loss(targets[mask], council_risks[mask])), 5) if mask.any() else None,
        "national_fit_brier": round(float(brier_score_loss(targets[mask], national_risks[mask])), 5) if mask.any() else None,
        "frozen_national_brier": round(float(brier_score_loss(targets[mask], frozen_risks[mask])), 5) if mask.any() else None,
    }
    by_council: dict[str, dict[str, Any]] = {}
    for council, group in frame.groupby(authority_column):
        indices = group.index.to_numpy()
        y = pd.to_numeric(group[target_column], errors="coerce").to_numpy()
        used_council = council_calibrators.get(str(council), national)
        if used_council is None:
            continue
        council_p = _calibrate(pd.to_numeric(group[score_column], errors="coerce").to_numpy(), used_council)
        national_p = _calibrate(pd.to_numeric(group[score_column], errors="coerce").to_numpy(), national)
        frozen_p = np.clip(pd.to_numeric(group[frozen_calibrated_column], errors="coerce").to_numpy(), 1e-6, 1 - 1e-6)
        valid = pd.notna(y)
        by_council[str(council)] = {
            "rows": int(len(group)),
            "used_council_calibrator": str(council) in council_calibrators,
            "council_brier": round(float(brier_score_loss(y[valid], council_p[valid])), 5) if valid.any() else None,
            "national_brier": round(float(brier_score_loss(y[valid], national_p[valid])), 5) if valid.any() else None,
            "frozen_brier": round(float(brier_score_loss(y[valid], frozen_p[valid])), 5) if valid.any() else None,
        }
    return {
        "summary": summary,
        "by_council": by_council,
        "caveat": (
            "Calibrators are fitted on the first half of 2025 and evaluated on the second half "
            "(temporal holdout). This validates whether council-aware recalibration is worth "
            "maintaining; it does not replace the frozen national model."
        ),
    }
