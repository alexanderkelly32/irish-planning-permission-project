"""Pilot cohort construction (brief section 12).

Defines the mature granted residential 10+ unit candidate pool from the
bronze register, computes COVID-exposure strata and proposes the stratified
100-scheme pilot cohort. Output is reviewable (CSV audit workbook); human
adjudication happens outside code.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

# COVID-19 construction restriction regimes (brief section 12.1 + sources.yaml).
COVID_REGIMES = [
    ("broad_closure", dt.date(2021, 1, 8), dt.date(2021, 4, 11)),
    ("phased_residential_reopening", dt.date(2021, 4, 12), dt.date(2021, 5, 3)),
    ("fully_reopened", dt.date(2021, 5, 4), None),
]

GRANTED_LABELS = {"grant", "granted", "grant permission", "conditional", "conditional permission"}


def is_granted(decision: Any) -> bool:
    if decision is None or (isinstance(decision, float) and pd.isna(decision)):
        return False
    text = str(decision).strip().lower()
    return any(label in text for label in GRANTED_LABELS) and "refus" not in text


def build_candidate_pool(
    register: pd.DataFrame,
    *,
    min_units: int = 10,
    grant_start: str = "2016-01-01",
    grant_end: str = "2022-12-31",
    censor_date: str = "2026-09-27",
    min_followup_months: int = 36,
) -> pd.DataFrame:
    """Mature granted residential 10+ unit candidate schemes."""
    frame = register.copy()
    frame["grant_date_dt"] = pd.to_datetime(frame.get("GrantDate"), utc=True, errors="coerce")
    frame["received_date_dt"] = pd.to_datetime(frame.get("ReceivedDate"), utc=True, errors="coerce")
    if "DecisionDate" in frame.columns:
        frame["decision_date_dt"] = pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce")
    else:
        frame["decision_date_dt"] = pd.NaT

    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame = frame[units >= min_units]
    frame = frame[frame["grant_date_dt"].notna()]
    frame = frame[frame["grant_date_dt"].between(pd.Timestamp(grant_start, tz="UTC"), pd.Timestamp(grant_end, tz="UTC"))]
    frame = frame[frame["Decision"].map(is_granted)]

    censor = pd.Timestamp(censor_date, tz="UTC")
    followup = (censor - frame["grant_date_dt"]).dt.days / 30.44
    frame = frame[followup >= min_followup_months]
    frame["followup_months"] = followup

    return frame.reset_index(drop=True)


def covid_exposure(grant_date: pd.Timestamp) -> dict[str, Any]:
    """Exposure of the at-risk activation interval to defined regimes."""
    date = grant_date.date()
    start = date
    end = date + dt.timedelta(days=730)  # 24-month at-risk window
    exposed_days = {}
    for name, regime_start, regime_end in COVID_REGIMES:
        window_start = max(start, regime_start)
        window_end = end if regime_end is None else min(end, regime_end)
        days = (window_end - window_start).days
        exposed_days[name] = max(0, days) if window_end >= window_start else 0
    material = (exposed_days["broad_closure"] + exposed_days["phased_residential_reopening"]) >= 30
    return {"covid_exposure_days": exposed_days, "covid_materially_exposed": bool(material)}


def annotate_pool(pool: pd.DataFrame) -> pd.DataFrame:
    frame = pool.copy()
    if "grant_date_dt" not in frame.columns:
        frame["grant_date_dt"] = pd.to_datetime(frame.get("GrantDate"), utc=True, errors="coerce")
    exposure = frame["grant_date_dt"].map(covid_exposure)
    frame["covid_materially_exposed"] = [item["covid_materially_exposed"] for item in exposure]
    frame["covid_broad_closure_days"] = [item["covid_exposure_days"]["broad_closure"] for item in exposure]
    frame["covid_reopening_days"] = [item["covid_exposure_days"]["phased_residential_reopening"] for item in exposure]
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["size_band"] = pd.cut(
        units,
        bins=[-np.inf, 29, 99, 249, np.inf],
        labels=["10-29", "30-99", "100-249", "250+"],
    )
    frame["grant_year"] = frame["grant_date_dt"].dt.year
    return frame


def stratify_pilot(
    annotated: pd.DataFrame,
    *,
    target: int = 100,
    weights: dict[str, float] | None = None,
    seed: int = 7,
) -> pd.DataFrame:
    """Deterministic stratified sample of the candidate pool."""
    weights = weights or {"10-29": 0.25, "30-99": 0.25, "100-249": 0.25, "250+": 0.25}
    frame = annotated.copy()
    rng = np.random.default_rng(seed)
    picks = []
    per_band = {band: max(1, int(round(target * weight))) for band, weight in weights.items()}
    for band, count in per_band.items():
        band_pool = frame[frame["size_band"] == band]
        if band_pool.empty:
            continue
        sample_n = min(count, len(band_pool))
        picks.append(band_pool.sample(n=sample_n, random_state=int(rng.integers(0, 2**31))))
    if not picks:
        return pd.DataFrame()
    combined = pd.concat(picks, ignore_index=True)
    combined["pilot_rank"] = range(1, len(combined) + 1)
    return combined


def cohort_summary(annotated: pd.DataFrame) -> dict[str, Any]:
    units = pd.to_numeric(annotated["NumResidentialUnits"], errors="coerce")
    return {
        "candidate_schemes": int(len(annotated)),
        "authorities": int(annotated["PlanningAuthority"].nunique()),
        "grant_years": [int(year) for year in sorted(annotated["grant_year"].dropna().unique())],
        "size_band_counts": {str(band): int(count) for band, count in annotated["size_band"].value_counts().items()},
        "covid_materially_exposed": int(annotated["covid_materially_exposed"].sum()),
        "median_units": float(units.median()) if not units.empty else None,
    }


def export_audit_workbook(annotated: pd.DataFrame, out_path: Any) -> Path:
    from pathlib import Path

    out_path = Path(out_path)
    columns = [
        "pilot_rank", "case_key", "PlanningAuthority", "ApplicationNumber",
        "DevelopmentAddress", "NumResidentialUnits", "size_band", "grant_year",
        "ReceivedDate", "GrantDate", "covid_materially_exposed",
        "covid_broad_closure_days", "covid_reopening_days", "followup_months",
        "ITMEasting", "ITMNorthing", "SiteId",
    ]
    keep = [column for column in columns if column in annotated.columns]
    annotated[keep].to_csv(out_path, index=False)
    return out_path
