"""Pain-to-develop label builder (Amendment A).

Builds the provisional `pain_v1` composite from structured data:
  - register: FI dates, appeal dates, received/decision dates;
  - BCMS silver: confirmed-link commencement dates, completion records.

Only confirmed BCMS links contribute timing components; unlinked events are
unknown. The composite rule lives in configs/rules/pain_v1.yaml and is
versioned; raw components are always retained.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from .activation import _parse_date, days_between

HIGH_COMPONENTS = ("appeal_submitted", "slow_planning_24m", "slow_activation_24m", "slow_completion_36m")
MODERATE_COMPONENTS = ("fi_requested", "slow_planning_12m", "no_completion_matured")
HIGH_COMPONENTS_V2 = HIGH_COMPONENTS + ("slow_exit_24m",)
MODERATE_COMPONENTS_V2 = MODERATE_COMPONENTS + ("below_market_25pct",)

COMPONENT_COLUMNS = [
    "appeal_submitted",
    "fi_requested",
    "planning_duration_days",
    "slow_planning_12m",
    "slow_planning_24m",
    "activation_days",
    "slow_activation_24m",
    "completion_days",
    "slow_completion_36m",
    "no_completion_matured",
]


def build_components(
    register: pd.DataFrame,
    bcms_events: pd.DataFrame,
    links: pd.DataFrame,
    *,
    censor_date: str,
    exit_labels: pd.DataFrame | None = None,
    rule_version: str = "pain_v1",
) -> pd.DataFrame:
    """One component row per register row (scheme/application).

    register: bronze register rows for the cohort (one row per application).
    bcms_events: silver bcms_events (commencement_date_dt, completion_*).
    links: adjudicated scheme->bcms links (confidence_band == confirmed used).
    exit_labels: optional economics output (slow_exit_24m, below_market_25pct)
      merged for pain_v2.
    censor_date: last observation date.
    """
    censor = pd.to_datetime(censor_date, utc=True).date()
    confirmed = links[links["confidence_band"] == "confirmed"] if links is not None and len(links) else pd.DataFrame()

    commencement_by_scheme: dict[str, dt.date] = {}
    completion_by_scheme: dict[str, dt.date] = {}
    if not confirmed.empty and not bcms_events.empty:
        events = bcms_events.merge(
            confirmed[["scheme_id", "bcms_event_id"]].drop_duplicates(),
            left_on="bcms_event_id",
            right_on="bcms_event_id",
            how="inner",
        )
        if not events.empty:
            comm = events[events["commencement_date_dt"].notna()].copy()
            comm["comm_date"] = comm["commencement_date_dt"].map(_parse_date)
            first_comm = comm.dropna(subset=["comm_date"]).groupby("scheme_id")["comm_date"].min()
            commencement_by_scheme = first_comm.to_dict()

            done = events[events["completion_certificate_date_dt"].notna()].copy()
            done["done_date"] = done["completion_certificate_date_dt"].map(_parse_date)
            first_done = done.dropna(subset=["done_date"]).groupby("scheme_id")["done_date"].min()
            completion_by_scheme = first_done.to_dict()

    rows = []
    for _, application in register.iterrows():
        scheme_id = str(application["case_key"])
        received = _parse_date(application.get("ReceivedDate"))
        decision = _parse_date(application.get("DecisionDate"))
        grant = _parse_date(application.get("GrantDate")) or decision

        fi_requested = bool(
            _parse_date(application.get("FIRequestDate")) or _parse_date(application.get("FIRecDate"))
        )
        appeal_submitted = bool(
            _parse_date(application.get("AppealSubmittedDate"))
            or (application.get("AppealRefNumber") and str(application["AppealRefNumber"]).strip())
        )

        planning_duration_days = days_between(received, decision)
        slow_planning_12m = planning_duration_days is not None and planning_duration_days >= 365
        slow_planning_24m = planning_duration_days is not None and planning_duration_days >= 730

        activation_days = days_between(grant, commencement_by_scheme.get(scheme_id))
        # Hygiene: commencement more than 180 days before grant is a link
        # error (commencement of a different scheme), not activation.
        if activation_days is not None and activation_days < -180:
            activation_days = None
        slow_activation_24m = activation_days is not None and activation_days >= 730

        commencement_date = commencement_by_scheme.get(scheme_id)
        completion_days = days_between(commencement_date, completion_by_scheme.get(scheme_id))
        slow_completion_36m = completion_days is not None and completion_days >= 1095
        no_completion_matured = bool(
            commencement_date is not None
            and completion_by_scheme.get(scheme_id) is None
            and days_between(commencement_date, censor) is not None
            and days_between(commencement_date, censor) >= 1095
        )

        components = {
            "scheme_id": scheme_id,
            "appeal_submitted": appeal_submitted,
            "fi_requested": fi_requested,
            "planning_duration_days": planning_duration_days,
            "slow_planning_12m": slow_planning_12m,
            "slow_planning_24m": slow_planning_24m,
            "activation_days": activation_days,
            "slow_activation_24m": slow_activation_24m,
            "completion_days": completion_days,
            "slow_completion_36m": slow_completion_36m,
            "no_completion_matured": no_completion_matured,
            "activation_linked": commencement_date is not None,
            "completion_linked": completion_by_scheme.get(scheme_id) is not None,
        }
        if exit_labels is not None and not exit_labels.empty:
            matched = exit_labels[exit_labels["scheme_id"] == scheme_id]
            if not matched.empty:
                row_exit = matched.iloc[0]
                components["slow_exit_24m"] = None if pd.isna(row_exit.get("slow_exit_24m")) else int(row_exit["slow_exit_24m"])
                components["below_market_25pct"] = None if pd.isna(row_exit.get("below_market_25pct")) else int(row_exit["below_market_25pct"])
                components["sales_linked"] = int(row_exit.get("sales_linked", 0))
        components["level"] = assign_level(components, rule_version=rule_version)
        components["pain_high_binary"] = int(components["level"] == "high")
        rows.append(components)

    frame = pd.DataFrame(rows)
    frame["label_rule_version"] = rule_version
    return frame


def assign_level(components: dict[str, Any], rule_version: str = "pain_v1") -> str:
    high_names = HIGH_COMPONENTS_V2 if rule_version == "pain_v2" else HIGH_COMPONENTS
    moderate_names = MODERATE_COMPONENTS_V2 if rule_version == "pain_v2" else MODERATE_COMPONENTS
    high = [name for name in high_names if _truthy_component(components.get(name))]
    if high:
        return "high"
    moderate = [name for name in moderate_names if _truthy_component(components.get(name))]
    if moderate:
        return "moderate"
    observed = {name for name in high_names + moderate_names if name in components}
    if observed and not any(_truthy_component(components.get(name)) for name in observed):
        return "low"
    return "low"  # unknown components are treated as absent; coverage reported separately


def _truthy_component(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    return str(value).strip().lower() in {"true", "yes", "y", "1", "present"}


def component_prevalence(labels: pd.DataFrame) -> dict[str, Any]:
    summary: dict[str, Any] = {"rows": int(len(labels))}
    for column in [*COMPONENT_COLUMNS, "activation_linked", "completion_linked"]:
        if column not in labels.columns:
            continue
        series = labels[column]
        if series.dtype == bool or series.dtype == object and set(series.dropna().unique()) <= {True, False}:
            summary[column] = int(series.sum())
        else:
            summary[column] = int(series.notna().sum())
    summary["level_counts"] = labels["level"].value_counts().to_dict()
    summary["pain_high_prevalence"] = round(float(labels["pain_high_binary"].mean()), 4) if len(labels) else None
    return summary
