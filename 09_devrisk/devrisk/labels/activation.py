"""Activation labels: censored time-to-commencement (brief sections 5.3, 13.1-13.2).

Primary duration: days from final effective grant to first valid commencement
notice. Binary horizons: 12/18/24/36 months. Right-censoring is explicit: a
2025 grant can never be labelled "did not commence within 36 months" in 2026.

Evidence tiers (version one):
  A - administrative only (commencement notice linked, no corroboration yet)
  B - corroborated progress (later phase notice / completion event / sales)
  C - completion evidence
  Unresolved - identity or follow-up inadequate
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

HORIZONS_DAYS = {"commence_12m": 365, "commence_18m": 548, "commence_24m": 730, "commence_36m": 1096}

COMPETING_EVENTS = {
    "lapse_or_expiry",
    "replacement_permission",
    "judicial_quashing",
    "withdrawal",
    "sale_or_change_of_control",
    "phase_restructuring",
}


def _parse_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, dt.datetime):
        result = value.date()
        return None if pd.isna(result) else result
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nat", "none", ""}:
        return None
    parsed = pd.to_datetime(text, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def days_between(start: dt.date | None, end: dt.date | None) -> int | None:
    if start is None or end is None:
        return None
    return (end - start).days


def build_activation_labels(
    schemes: pd.DataFrame,
    commencements: pd.DataFrame,
    *,
    censor_date: str,
    links: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build censored activation labels for schemes.

    schemes: one row per scheme, columns scheme_id, final_grant_date,
             expected_units, eligibility flags optional.
    commencements: linked commencement events, columns scheme_id,
             commencement_date_dt, corroboration_tier, competing_event,
             censor_reason optional.
    links: optional link confidence per (scheme_id, bcms_event_id); only
             confirmed links count as events unless explicitly allowed.
    censor_date: last observation date (inclusive).
    """
    labels = []
    censor = pd.to_datetime(censor_date, utc=True).date()

    for _, scheme in schemes.iterrows():
        grant = _parse_date(scheme.get("final_grant_date"))
        scheme_id = str(scheme["scheme_id"])
        events = commencements[commencements["scheme_id"] == scheme_id].copy() if not commencements.empty else pd.DataFrame()

        if not events.empty and links is not None and not links.empty:
            link_rows = links[links["scheme_id"] == scheme_id]
            confirmed_events = set(
                link_rows[link_rows["confidence_band"] == "confirmed"]["bcms_event_id"]
            )
            if "bcms_event_id" in events.columns:
                events = events[events["bcms_event_id"].isin(confirmed_events)]

        event_date: dt.date | None = None
        corroboration_tier = "unresolved"
        competing = None
        if not events.empty:
            if "commencement_date_dt" in events.columns:
                parsed = events["commencement_date_dt"].map(_parse_date).dropna()
                if not parsed.empty:
                    event_date = min(parsed)
            tiers = events["corroboration_tier"].dropna().astype(str) if "corroboration_tier" in events.columns else pd.Series(dtype=str)
            corroboration_tier = "C" if "C" in set(tiers) else ("B" if "B" in set(tiers) else ("A" if "A" in set(tiers) else "unresolved"))
            if "competing_event" in events.columns:
                observed = [str(value) for value in events["competing_event"].dropna().astype(str) if str(value).strip()]
                competing = observed[0] if observed else None

        eligible = grant is not None
        observed = event_date is not None and grant is not None and event_date <= censor
        duration_days = days_between(grant, event_date) if observed else None

        if competing:
            censored = False
            censor_reason = ""
            event_flag = 0
            horizon_flags = {}
            if observed:
                horizon_flags = {key: int(duration_days <= limit) for key, limit in HORIZONS_DAYS.items()}
            else:
                horizon_flags = {key: None for key in HORIZONS_DAYS}
        elif grant is None:
            censored = True
            censor_reason = "missing_final_grant_date"
            event_flag = None
            horizon_flags = {key: None for key in HORIZONS_DAYS}
        elif not observed:
            censored = True
            censor_reason = "right_censored_no_event_by_censor_date"
            event_flag = 0
            horizon_flags = {
                key: None if days_between(grant, censor) < limit else 0
                for key, limit in HORIZONS_DAYS.items()
            }
        else:
            censored = False
            censor_reason = ""
            event_flag = 1
            horizon_flags = {key: int(duration_days <= limit) for key, limit in HORIZONS_DAYS.items()}

        row = {
            "scheme_id": scheme_id,
            "start_milestone": "final_grant",
            "start_date": grant.isoformat() if grant else None,
            "event_milestone": "first_valid_commencement_notice",
            "event_date": event_date.isoformat() if event_date else None,
            "duration_days": duration_days,
            "event_observed": event_flag,
            "censored": censored,
            "censor_reason": censor_reason,
            "last_observation_date": censor.isoformat(),
            "competing_event": competing,
            "corroboration_tier": corroboration_tier,
            "eligible": bool(eligible),
            "label_rule_version": "activation_v1",
        }
        row.update(horizon_flags)
        labels.append(row)

    return pd.DataFrame(labels)


def months_to_days(months: int) -> int:
    return months * 365 // 12
