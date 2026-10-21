"""Append-only prospective shadow ledger for frozen-model predictions."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd

LEDGER_COLUMNS = [
    "case_key",
    "PlanningAuthority",
    "ApplicationNumber",
    "received_date",
    "registered_at",
    "model_version",
    "predicted_refusal_risk",
    "predicted_risk_band",
    "ranking_score",
    "input_snapshot",
    "outcome_decision",
    "outcome_refused",
    "outcome_date",
    "outcome_source_note",
]


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def build_case_key(authority: object, number: object) -> str:
    return f"{_slug(authority)}__{_slug(number)}"


def _sanitize(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    return value


def snapshot_json(query: dict[str, Any]) -> str:
    return json.dumps(
        {key: _sanitize(value) for key, value in query.items()},
        sort_keys=True,
    )


def build_ledger_rows(
    cases: pd.DataFrame,
    scorer: Callable[[dict[str, Any]], dict[str, Any]],
    registered_at: datetime | None = None,
) -> pd.DataFrame:
    """Score submission-time inputs for each case and produce append-only ledger rows."""
    registered_at = registered_at or datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for _, case in cases.iterrows():
        authority = str(case.get("PlanningAuthority") or "").strip()
        received = pd.to_datetime(case.get("ReceivedDate"), utc=True, errors="coerce")
        if not authority or pd.isna(received):
            continue
        units = case.get("NumResidentialUnits")
        query = {
            "PlanningAuthority": authority,
            "ApplicationType": case.get("ApplicationType"),
            "DevelopmentDescription": str(case.get("DevelopmentDescription") or ""),
            "units_total_best": None if pd.isna(units) else float(units),
            "ITMEasting": None if pd.isna(case.get("ITMEasting")) else float(case.get("ITMEasting")),
            "ITMNorthing": None if pd.isna(case.get("ITMNorthing")) else float(case.get("ITMNorthing")),
            "received_year": float(received.year),
        }
        score = scorer(query)
        if score.get("status") != "scored":
            continue
        rows.append({
            "case_key": build_case_key(authority, case.get("ApplicationNumber")),
            "PlanningAuthority": authority,
            "ApplicationNumber": str(case.get("ApplicationNumber") or ""),
            "received_date": str(received.date()),
            "registered_at": registered_at.isoformat(),
            "model_version": str(score.get("model_version", "unknown")),
            "predicted_refusal_risk": round(float(score.get("refusal_score", 0.0)), 6),
            "predicted_risk_band": str(score.get("risk_band", "")),
            "ranking_score": round(float(score.get("ranking_score", 0.0)), 6),
            "input_snapshot": snapshot_json(query),
            "outcome_decision": "",
            "outcome_refused": "",
            "outcome_date": "",
            "outcome_source_note": "",
        })
    return pd.DataFrame(rows, columns=LEDGER_COLUMNS)


def append_ledger(existing: pd.DataFrame | None, new_rows: pd.DataFrame) -> pd.DataFrame:
    """Append new rows only; existing registrations are never modified."""
    if existing is None or existing.empty:
        return new_rows.reset_index(drop=True)
    for column in LEDGER_COLUMNS:
        if column not in existing.columns:
            existing[column] = ""
    existing = existing[LEDGER_COLUMNS].copy()
    known = set(existing["case_key"].astype(str))
    additions = new_rows[~new_rows["case_key"].astype(str).isin(known)]
    if additions.empty:
        return existing.reset_index(drop=True)
    return pd.concat([existing, additions], ignore_index=True)


def ledger_summary(ledger: pd.DataFrame, model_sha256: str | None = None) -> dict[str, Any]:
    """Counts and conservative notes; outcomes are separate and never used for tuning."""
    frame = ledger if ledger is not None else pd.DataFrame(columns=LEDGER_COLUMNS)
    outcome_known = frame.get("outcome_refused", pd.Series(dtype=str)).fillna("").astype(str).ne("")
    summary = {
        "ledger_row_count": int(len(frame)),
        "registered_case_count": int(frame["case_key"].nunique()) if not frame.empty else 0,
        "authority_counts": frame["PlanningAuthority"].value_counts().to_dict() if not frame.empty else {},
        "risk_band_counts": (
            frame.get("predicted_risk_band", pd.Series(dtype=str)).value_counts().to_dict()
            if not frame.empty else {}
        ),
        "outcome_known_count": int(outcome_known.sum()),
        "model_sha256": model_sha256,
        "caveat": (
            "The shadow ledger is a prospective monitor only. Registered predictions must "
            "not be used to tune or promote any model until outcomes arrive and are read "
            "out separately."
        ),
    }
    return summary


def outcome_readout(ledger: pd.DataFrame) -> dict[str, Any]:
    """Early readout once outcomes exist; conservative and explicitly non-promotional."""
    frame = ledger[ledger.get("outcome_refused", pd.Series(dtype=str)).fillna("").astype(str).isin({"0", "1"})].copy()
    if frame.empty:
        return {"status": "no_outcomes_yet", "outcome_row_count": 0}
    y = frame["outcome_refused"].astype(int)
    p = pd.to_numeric(frame["predicted_refusal_risk"], errors="coerce")
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    readout = {
        "status": "readout",
        "outcome_row_count": int(len(frame)),
        "observed_refusal_rate": float(y.mean()),
        "mean_predicted_risk": float(p.mean()),
    }
    if y.nunique() >= 2:
        clipped = np.clip(p.to_numpy(dtype=float), 1e-6, 1 - 1e-6)
        readout["roc_auc"] = round(float(roc_auc_score(y, clipped)), 4)
        readout["average_precision"] = round(float(average_precision_score(y, clipped)), 4)
        readout["brier"] = round(float(brier_score_loss(y, clipped)), 4)
    readout["caveat"] = (
        "Readouts are monitoring diagnostics only; do not use them to promote or retune a model."
    )
    return readout
