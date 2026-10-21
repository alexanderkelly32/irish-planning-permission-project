"""Survival baselines: Kaplan-Meier and discrete-time logistic hazard.

Brief sections 15.3-15.4. Baselines first: overall KM curve, KM by cohort
strata, then a discrete-time logistic hazard model (explainable, horizon-
calibratable) built on the existing scikit-learn stack. No external survival
library dependency.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression


def kaplan_meier(durations: np.ndarray, events: np.ndarray) -> pd.DataFrame:
    """Kaplan-Meier estimate with Greenwood confidence intervals.

    durations: time to event or censoring (>= 0). events: 1 observed event,
    0 right-censored. Returns a survival table: t, n_at_risk, n_events,
    survival, se, ci_lower, ci_upper.
    """
    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=int)
    if len(durations) == 0:
        return pd.DataFrame(columns=["t", "n_at_risk", "n_events", "survival", "se", "ci_lower", "ci_upper"])
    if np.any(durations < 0):
        raise ValueError("durations must be >= 0")

    order = np.argsort(durations, kind="stable")
    durations = durations[order]
    events = events[order]
    n = len(durations)
    unique_times = np.unique(durations)

    rows = []
    survival = 1.0
    greenwood = 0.0
    idx = 0
    for t in unique_times:
        mask = durations == t
        d = int(events[mask].sum())
        at_risk = n - idx
        if d > 0 and at_risk > 0:
            survival *= (1.0 - d / at_risk)
            greenwood += d / (at_risk * (at_risk - d)) if at_risk > d else d / max(at_risk * (at_risk - d), 1)
        se = survival * np.sqrt(greenwood) if greenwood > 0 else 0.0
        z = 1.96
        log_term = np.log(max(survival, 1e-12))
        ci_lower = survival * np.exp(z * np.sqrt(greenwood)) if greenwood > 0 else survival
        ci_upper = survival * np.exp(-z * np.sqrt(greenwood)) if greenwood > 0 else survival
        rows.append({
            "t": float(t),
            "n_at_risk": int(at_risk),
            "n_events": int(d),
            "survival": float(survival),
            "se": float(se),
            "ci_lower": max(0.0, min(1.0, ci_lower)),
            "ci_upper": max(0.0, min(1.0, ci_upper)),
        })
        idx += int(mask.sum())
    return pd.DataFrame(rows)


def km_survival_at(table: pd.DataFrame, horizon: float) -> float:
    """Point estimate of survival at a horizon from a KM table."""
    if table.empty:
        return 1.0
    earlier = table[table["t"] <= horizon]
    if earlier.empty:
        return 1.0
    return float(earlier["survival"].iloc[-1])


def km_probability_by(table: pd.DataFrame, horizon: float) -> float:
    """P(event by horizon) from a KM table (1 - S(horizon))."""
    return 1.0 - km_survival_at(table, horizon)


def discrete_time_hazard_matrix(
    durations: np.ndarray,
    events: np.ndarray,
    max_time: float,
    interval_days: float = 30.0,
) -> pd.DataFrame:
    """Expand right-censored durations into person-period rows.

    Each row: unit i, interval [t_start, t_end), y (event in interval).
    """
    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=int)
    edges = np.arange(0.0, max_time + interval_days, interval_days)
    edges = np.append(edges, np.inf)
    rows = []
    for i, (duration, event) in enumerate(zip(durations, events, strict=False)):
        for start in edges[:-1]:
            end = min(start + interval_days, duration)
            if end <= start:
                break
            y = int(event and end >= duration and duration <= start + interval_days)
            rows.append({"unit": i, "t_start": start, "t_end": min(start + interval_days, edges[-2]), "y": y})
            if y or end >= duration:
                break
    return pd.DataFrame(rows)


def fit_discrete_time_hazard(
    person_periods: pd.DataFrame,
    feature_columns: list[str],
    *,
    C: float = 0.5,
    max_iter: int = 1000,
) -> LogisticRegression:
    """Regularised discrete-time logistic hazard on person-period rows."""
    model = LogisticRegression(C=C, max_iter=max_iter, solver="liblinear", class_weight="balanced")
    model.fit(person_periods[feature_columns], person_periods["y"])
    return model


def predict_horizon_probabilities(
    model: LogisticRegression,
    row_features: dict[str, float],
    horizons_days: list[int],
    interval_days: float = 30.0,
) -> dict[int, float]:
    """Horizon-specific P(commence by h) from a discrete-time hazard model."""
    frame = pd.DataFrame([row_features])
    probs = {}
    for horizon in horizons_days:
        intervals = int(np.ceil(horizon / interval_days))
        hazard = model.predict_proba(frame)[:, 1][0]
        survival = (1.0 - hazard) ** intervals
        probs[horizon] = float(np.clip(1.0 - survival, 0.0, 1.0))
    return probs


def median_survival_time(table: pd.DataFrame) -> float | None:
    """First time survival drops to <= 0.5, else None."""
    crossed = table[table["survival"] <= 0.5]
    if crossed.empty:
        return None
    return float(crossed["t"].iloc[0])


def predict_cumulative_incidence(
    hazard: np.ndarray,
    interval_days: float = 30.0,
    horizon_days: float = 365.0,
) -> float:
    """P(T <= horizon) = 1 - prod(1 - hazard_j) over a FIXED interval grid.

    hazard: per-interval hazards for ONE scheme over [0, horizon). The grid
    length must not depend on the scheme's observed duration (the earlier
    evaluation bug did exactly that and inverted the ranking).
    """
    intervals = max(1, int(np.ceil(horizon_days / interval_days)))
    hazard = np.asarray(hazard, dtype=float)[:intervals]
    if len(hazard) < intervals:
        hazard = np.pad(hazard, (0, intervals - len(hazard)), mode="edge")
    survival = float(np.prod(1.0 - np.clip(hazard, 0.0, 1.0)))
    return float(np.clip(1.0 - survival, 0.0, 1.0))


def km_ipcw_weights(y_obs: np.ndarray, censored: np.ndarray, horizon: float) -> np.ndarray:
    """Inverse-probability-of-censoring weights (KM on the censoring
    distribution). Rows censored before the horizon are not evaluable."""
    weights = np.ones(len(y_obs))
    censor_times = y_obs[censored]
    if len(censor_times):
        km = kaplan_meier(censor_times, np.ones(len(censor_times), dtype=int))
        surv = km[km["t"] <= horizon]["survival"]
        g = float(surv.iloc[-1]) if len(surv) else 1.0
        weights[censored & (y_obs < horizon)] = 0.0
        weights[(y_obs <= horizon) & (~censored)] = 1.0 / max(g, 1e-9)
    return weights


def dynamic_auc(y_obs: np.ndarray, censored: np.ndarray, score: np.ndarray, horizon: float) -> float:
    """Incident/dynamic AUC at a horizon, IPCW-weighted.

    score: predicted cumulative incidence P(T <= horizon), higher = higher
    event risk. Rows censored before the horizon are excluded.
    """
    weights = km_ipcw_weights(np.asarray(y_obs, dtype=float), np.asarray(censored, dtype=bool), horizon)
    evaluable = weights > 0
    if evaluable.sum() < 10:
        return np.nan
    y_h = np.where(censored, 0, np.asarray(y_obs) <= horizon).astype(float)[evaluable]
    weights_e = weights[evaluable]
    score_e = np.asarray(score)[evaluable]
    if y_h.min() == y_h.max():
        return np.nan
    order = np.argsort(score_e)
    y_sorted = y_h[order]
    w_sorted = weights_e[order]
    total_pos = w_sorted[y_sorted == 1].sum()
    total_neg = w_sorted[y_sorted == 0].sum()
    if total_pos == 0 or total_neg == 0:
        return np.nan
    cum_neg = np.cumsum(w_sorted * (y_sorted == 0))
    return float((w_sorted * (y_sorted == 1) * cum_neg).sum() / (total_pos * total_neg))


def integrated_brier(y_obs: np.ndarray, censored: np.ndarray, scores: dict[float, np.ndarray]) -> float:
    """IPCW Brier score integrated over the horizons in scores (mean)."""
    values = []
    for horizon, score in scores.items():
        weights = km_ipcw_weights(np.asarray(y_obs, dtype=float), np.asarray(censored, dtype=bool), horizon)
        evaluable = weights > 0
        y_h = np.where(censored, 0, np.asarray(y_obs) <= horizon).astype(float)[evaluable]
        values.append(float(np.mean(weights[evaluable] * (y_h - np.asarray(score)[evaluable]) ** 2)))
    return float(np.mean(values))
