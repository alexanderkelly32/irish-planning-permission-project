"""Discrete-time hazard machinery for activation/completion survival models.

Person-period expansion with time-varying regime covariates (COVID
construction restrictions), piecewise baseline via interval index, regularised
logistic hazard, horizon survival probabilities, and proper scoring tools:
concordance index, IPCW-adjusted Brier at horizons, time-dependent AUC at a
horizon. Cohort = final-grant snapshot (brief section 6).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from ..labels.activation import HORIZONS_DAYS, days_between
from .survival import kaplan_meier

INTERVAL_DAYS = 30
MAX_DAYS = 3650  # 10-year cap for person-period expansion

REGIME_INTERVALS = [
    ("broad_closure", dt.date(2021, 1, 8), dt.date(2021, 4, 11)),
    ("phased_reopening", dt.date(2021, 4, 12), dt.date(2021, 5, 3)),
]


def regime_exposure(interval_start: dt.date, interval_end: dt.date) -> dict[str, int]:
    exposure = {}
    for name, start, end in REGIME_INTERVALS:
        window_start = max(interval_start, start)
        window_end = min(interval_end, end)
        days = (window_end - window_start).days
        exposure[name] = 1 if days > 0 else 0
    return exposure


def build_person_periods(
    durations: np.ndarray,
    events: np.ndarray,
    *,
    start_dates: np.ndarray,
    features: pd.DataFrame,
    max_days: int = MAX_DAYS,
) -> pd.DataFrame:
    """Expand right-censored durations into person-period rows with regime flags.

    durations: days from origin to event or censor. events: 1/0. start_dates:
    origin dates (datetime64 or python dates) per subject. features: per-subject
    baseline features (DataFrame, same order).
    """
    rows: list[dict[str, Any]] = []
    for i, (duration, event, start_date) in enumerate(zip(durations, events, start_dates, strict=False)):
        duration = min(float(duration), float(max_days)) if pd.notna(duration) else float(max_days)
        start = pd.Timestamp(start_date).date() if pd.notna(start_date) else dt.date(2019, 1, 1)
        t = 0.0
        interval_index = 0
        while t < duration:
            end = min(t + INTERVAL_DAYS, duration)
            interval_start = start + dt.timedelta(days=int(t))
            interval_end = start + dt.timedelta(days=int(end))
            y = int(event and end >= duration)
            row = {"unit": i, "interval_index": interval_index, "t_start": t, "y": y}
            row.update(regime_exposure(interval_start, interval_end))
            rows.append(row)
            t = end
            interval_index += 1
    person_periods = pd.DataFrame(rows)
    if not person_periods.empty:
        baseline = features.iloc[person_periods["unit"]].reset_index(drop=True)
        person_periods = pd.concat([person_periods.reset_index(drop=True), baseline], axis=1)
    return person_periods


def fit_hazard(
    person_periods: pd.DataFrame,
    feature_columns: list[str],
    *,
    C: float = 0.5,
    max_iter: int = 3000,
) -> LogisticRegression:
    model = LogisticRegression(C=C, max_iter=max_iter, solver="liblinear")
    model.fit(person_periods[feature_columns], person_periods["y"])
    return model


def predict_horizon_probabilities(
    model: LogisticRegression,
    baseline_features: pd.DataFrame,
    *,
    feature_columns: list[str],
    origins: np.ndarray,
    horizons: tuple[int, ...] = (365, 730, 1096),
) -> np.ndarray:
    """P(event by each horizon) per subject; rows built in feature_columns order."""
    out = np.zeros((len(baseline_features), len(horizons)))
    for subject_idx in range(len(baseline_features)):
        origin = pd.Timestamp(origins[subject_idx]).date() if pd.notna(origins[subject_idx]) else dt.date(2019, 1, 1)
        for horizon_idx, horizon in enumerate(horizons):
            survival = 1.0
            t = 0.0
            interval_index = 0
            while t < horizon:
                end = min(t + INTERVAL_DAYS, float(horizon))
                interval_start = origin + dt.timedelta(days=int(t))
                interval_end = origin + dt.timedelta(days=int(end))
                values: dict[str, Any] = {"interval_index": interval_index, "t_start": t}
                values.update(regime_exposure(interval_start, interval_end))
                for column in baseline_features.columns:
                    if column not in values:
                        values[column] = baseline_features.iloc[subject_idx][column]
                row = pd.DataFrame([{column: values[column] for column in feature_columns}])
                hazard = model.predict_proba(row)[0, 1]
                survival *= 1.0 - hazard
                t = end
                interval_index += 1
            out[subject_idx, horizon_idx] = 1.0 - survival
    return np.clip(out, 0.0, 1.0)


def concordance_index(times: np.ndarray, events: np.ndarray, risk_scores: np.ndarray) -> float:
    """Harrell's c-index (risk_scores higher = earlier event)."""
    order = np.argsort(times, kind="stable")
    times = np.asarray(times, dtype=float)[order]
    events = np.asarray(events, dtype=int)[order]
    risk = np.asarray(risk_scores, dtype=float)[order]
    comparable = 0
    concordant = 0
    for i in range(len(times)):
        if events[i] != 1:
            continue
        ti = times[i]
        ri = risk[i]
        for j in range(len(times)):
            if times[j] <= ti:
                continue
            comparable += 1
            if ri > risk[j]:
                concordant += 1
            elif ri == risk[j]:
                concordant += 0.5
    return float(concordant / comparable) if comparable else float("nan")


def brier_ipcw(
    times: np.ndarray,
    events: np.ndarray,
    survival_at_horizon: np.ndarray,
    horizon: float,
    censoring_table: pd.DataFrame | None = None,
) -> float:
    """IPCW Brier score for the event-by-horizon prediction (1 - survival).

    survival_at_horizon: P(T > horizon) per subject. Inverse-probability-of-
    censoring weights from the KM censoring model (treating events as censored).
    """
    y = np.asarray(events, dtype=int)
    times = np.asarray(times, dtype=float)
    cens_event = 1 - y
    cens_table = kaplan_meier(times, cens_event) if censoring_table is None else censoring_table
    weights = np.ones(len(times))
    for i, time in enumerate(times):
        if time <= horizon:
            if y[i]:
                weights[i] = 1.0 / max(_km_survival_at(cens_table, time - 1e-6), 1e-6)
            else:
                weights[i] = 1.0 / max(_km_survival_at(cens_table, horizon), 1e-6)
        else:
            weights[i] = 1.0 / max(_km_survival_at(cens_table, horizon), 1e-6)
    observed = (times <= horizon).astype(int)
    pred_event = 1.0 - np.clip(survival_at_horizon, 0.0, 1.0)
    return float(np.mean(weights * (observed - pred_event) ** 2))


def _km_survival_at(table: pd.DataFrame, horizon: float) -> float:
    if table.empty:
        return 1.0
    earlier = table[table["t"] <= horizon]
    return float(earlier["survival"].iloc[-1]) if not earlier.empty else 1.0


def time_dependent_auc(times: np.ndarray, events: np.ndarray, risk_scores: np.ndarray, horizon: float) -> float:
    """AUC for event-by-horizon using subjects with observed or censored-after status."""
    from sklearn.metrics import roc_auc_score

    y = ((times <= horizon) & (events == 1)).astype(int)
    risk = -risk_scores  # higher risk -> higher probability of event
    include = (events == 1) | (times > horizon)
    if np.unique(y[include]).size < 2:
        return float("nan")
    return float(roc_auc_score(y[include], risk[include]))


def median_time_from_curve(horizons: tuple[int, ...], probs: np.ndarray, cap_days: float = 3650.0) -> float | None:
    """Interpolate median from horizon event-probabilities."""
    for horizon, prob in zip(horizons, probs, strict=False):
        if prob >= 0.5:
            return float(horizon)
    return None
