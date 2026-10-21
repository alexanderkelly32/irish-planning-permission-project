"""Unified event ledger (brief: every development is an event chain).

One row per observed event: development_id, phase_id, event_type, event
dates, source, source_reference, units_affected, status, confidence,
observed_or_inferred. Populated from the register (planning/FI/appeal), BCMS
(commencement/declared-end/CCC per phase), PPR (first/last sale), JR evidence.
Precision-first: only confirmed links produce events; absence is never an
event.
"""
from __future__ import annotations

import pandas as pd

LEDGER_COLUMNS = [
    "development_id",
    "phase_id",
    "event_type",
    "event_date_start",
    "event_date_end",
    "source",
    "source_reference",
    "units_affected",
    "event_status",
    "confidence",
    "observed_or_inferred",
]

EVENT_TYPES = (
    "planning_received", "planning_granted", "fi_requested", "appeal_submitted",
    "judicial_review", "bcms_commencement", "bcms_declared_end",
    "completion_certificate", "first_sale", "last_sale",
)


def event_row(
    development_id: str,
    event_type: str,
    date_start,
    date_end=None,
    phase_id: str | None = None,
    source: str = "",
    source_reference: str = "",
    units_affected=None,
    event_status: str = "",
    confidence: str = "high",
) -> dict:
    return {
        "development_id": str(development_id),
        "phase_id": str(phase_id) if phase_id is not None else "",
        "event_type": event_type,
        "event_date_start": pd.Timestamp(date_start).date().isoformat() if pd.notna(pd.Timestamp(date_start)) else None,
        "event_date_end": pd.Timestamp(date_end).date().isoformat() if date_end is not None and pd.notna(pd.Timestamp(date_end)) else None,
        "source": source,
        "source_reference": str(source_reference),
        "units_affected": units_affected,
        "event_status": event_status,
        "confidence": confidence,
        "observed_or_inferred": "observed",
    }


def build_ledger(
    register: pd.DataFrame,
    bcms_events: pd.DataFrame,
    bcms_links: pd.DataFrame,
    exit_labels: pd.DataFrame,
    jr_events: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: list[dict] = []

    for _, scheme in register.iterrows():
        development_id = str(scheme["case_key"])
        received = pd.Timestamp(scheme.get("ReceivedDate"))
        if pd.notna(received):
            rows.append(event_row(development_id, "planning_received", received,
                                  source="npad_register", source_reference=scheme.get("ApplicationNumber") or ""))
        grant = pd.Timestamp(scheme.get("GrantDate"))
        if pd.isna(grant):
            grant = pd.Timestamp(scheme.get("DecisionDate"))
        if pd.notna(grant):
            rows.append(event_row(development_id, "planning_granted", grant,
                                  source="npad_register", source_reference=scheme.get("ApplicationNumber") or ""))
        fi = pd.Timestamp(scheme.get("FIRequestDate"))
        if pd.isna(fi):
            fi = pd.Timestamp(scheme.get("FIRecDate"))
        if pd.notna(fi):
            rows.append(event_row(development_id, "fi_requested", fi, source="npad_register"))
        appeal = pd.Timestamp(scheme.get("AppealSubmittedDate"))
        if pd.notna(appeal):
            rows.append(event_row(development_id, "appeal_submitted", appeal, source="npad_register",
                                  source_reference=str(scheme.get("AppealRefNumber") or "")))

    confirmed = bcms_links[bcms_links["confidence_band"] == "confirmed"]
    events = confirmed.merge(bcms_events, on="bcms_event_id", how="inner") if len(confirmed) else pd.DataFrame()
    if not events.empty:
        for _, notice in events.iterrows():
            development_id = str(notice["scheme_id"])
            phase_id = str(int(notice["phase_number"])) if pd.notna(notice.get("phase_number")) else None
            ref = str(notice.get("planning_reference") or "")
            if pd.notna(notice.get("commencement_date_dt")):
                rows.append(event_row(development_id, "bcms_commencement", notice["commencement_date_dt"],
                                      phase_id=phase_id, source="bcms", source_reference=ref,
                                      units_affected=notice.get("dwellings_phase"),
                                      event_status=str(notice.get("not_commenced") or ""),
                                      confidence="high"))
            if pd.notna(notice.get("proposed_end_date_dt")):
                rows.append(event_row(development_id, "bcms_declared_end", notice["proposed_end_date_dt"],
                                      phase_id=phase_id, source="bcms", source_reference=ref,
                                      confidence="high"))
            if pd.notna(notice.get("completion_certificate_date_dt")):
                rows.append(event_row(development_id, "completion_certificate", notice["completion_certificate_date_dt"],
                                      phase_id=phase_id, source="bcms", source_reference=ref,
                                      units_affected=notice.get("completion_units"),
                                      event_status=str(notice.get("ccc_type") or ""),
                                      confidence="high"))

    if exit_labels is not None and not exit_labels.empty:
        for _, scheme in exit_labels.iterrows():
            if not scheme.get("sales_linked"):
                continue
            development_id = str(scheme["scheme_id"])
            first = pd.Timestamp(scheme.get("first_sale_date"))
            last = pd.Timestamp(scheme.get("last_sale_date"))
            if pd.notna(first):
                rows.append(event_row(development_id, "first_sale", first, source="ppr",
                                      units_affected=scheme.get("sales_linked")))
            if pd.notna(last) and last != first:
                rows.append(event_row(development_id, "last_sale", last, source="ppr",
                                      units_affected=scheme.get("sales_linked")))

    if jr_events is not None and not jr_events.empty:
        for _, jr in jr_events.iterrows():
            rows.append(event_row(str(jr["case_key"]), "judicial_review",
                                  pd.Timestamp(jr.get("jr_conclusion_date")) if pd.notna(jr.get("jr_conclusion_date")) else pd.NaT,
                                  source="4dublin_pipeline", source_reference=str(jr.get("jr_reference") or ""),
                                  event_status=str(jr.get("jr_conclusion") or "pending"),
                                  confidence="medium"))

    ledger = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
    ledger = ledger.dropna(subset=["event_date_start"])
    ledger = ledger.sort_values(["development_id", "event_date_start", "event_type"]).drop_duplicates(
        subset=["development_id", "phase_id", "event_type", "event_date_start"], keep="first")
    return ledger.reset_index(drop=True)
