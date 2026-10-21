#!/usr/bin/env python3
"""Alteration-effect tables: per lever + direction, how many audited
resubmissions that made that change ended granted vs refused.

Granted arm = audited refused->granted pairs (canonical records carry the
deltas). Refused arm = audited refused->refused pairs (register units deltas
plus report-sourced deltas once the refused-arm campaign has run).

Every row carries Wilson 95% CIs; rows are ranked by evidence size then grant
share. These are the empirical "alter X -> gains/losses" numbers - model-free,
audited, observational (association, not causation).
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
CANONICAL = CURRENT / "canonical_revision_scheme_records.csv"
REFUSED_MERGED = CURRENT / "refused_refused_audit_merged.csv"
REFUSED_FIXED = REFUSED_MERGED if REFUSED_MERGED.exists() else (CURRENT / "refused_refused_review_rows_fixed.csv")
REFUSED_REPORTS = CURRENT / "revision_pair_report_extraction_2026-09-13" / "revision_pair_report_extractions_refused_arm.csv"
CONFIDENCE = CURRENT / "pair_delta_confidence.csv"

LEVERS = {
    "units_total_best": {"label": "units", "threshold": 3.0},
    "max_storeys_best": {"label": "storeys", "threshold": 1.0},
    "parking_spaces_best": {"label": "parking", "threshold": 2.0},
    "max_height_m": {"label": "height (m)", "threshold": 1.0},
    "vehicular_access_points": {"label": "access points", "threshold": 1.0},
    "nearest_dwelling_separation_m": {"label": "separation (m)", "threshold": 1.0},
    "communal_open_space_sqm": {"label": "open space (sqm)", "threshold": 10.0},
}
REPORT_FIELD_FOR_LEVER = {
    "max_storeys_best": "max_storeys",
    "parking_spaces_best": "parking_spaces",
    "max_height_m": "max_height_m",
    "vehicular_access_points": "vehicular_access_points",
    "nearest_dwelling_separation_m": "nearest_dwelling_separation_m",
    "communal_open_space_sqm": "communal_open_space_sqm",
}


def wilson(n: int, k: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (centre - margin) / denom, (centre + margin) / denom


def _low_confidence_keys() -> set[tuple[str, str, str]]:
    if not CONFIDENCE.exists():
        return set()
    frame = pd.read_csv(CONFIDENCE, low_memory=False)
    if frame.empty or "confidence" not in frame.columns:
        return set()
    low = frame[frame["confidence"].eq("low")]
    return {
        (str(row["original_case_key"]), str(row["revised_case_key"]), str(row["field"]))
        for _, row in low.iterrows()
    }


CONFIDENCE_FIELDS = {
    "max_storeys": "max_storeys_best",
    "parking_spaces": "parking_spaces_best",
    "max_height_m": "max_height_m",
    "vehicular_access_points": "vehicular_access_points",
    "nearest_dwelling_separation_m": "nearest_dwelling_separation_m",
    "communal_open_space_sqm": "communal_open_space_sqm",
}


def granted_arm_counts(canonical: pd.DataFrame) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    low_keys = _low_confidence_keys()
    excluded = 0
    for _, row in canonical.iterrows():
        try:
            deltas = json.loads(str(row.get("feature_delta_json") or "{}"))
        except (TypeError, ValueError):
            continue
        for column, delta in deltas.items():
            if column not in LEVERS or not isinstance(delta, dict):
                continue
            value = float(delta.get("delta", 0.0) or 0.0)
            if abs(value) < LEVERS[column]["threshold"]:
                continue
            key = (
                str(row.get("original_case_key")),
                str(row.get("revised_case_key")),
                {v: k for k, v in CONFIDENCE_FIELDS.items()}.get(column, column),
            )
            if key in low_keys:
                excluded += 1
                continue
            direction = "up" if value > 0 else "down"
            counts[(column, direction)] = counts.get((column, direction), 0) + 1
    return counts


def refused_arm_counts(refused_fixed: pd.DataFrame, refused_reports: pd.DataFrame | None) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for _, row in refused_fixed.iterrows():
        delta = pd.to_numeric(row.get("units_delta"), errors="coerce")
        if pd.notna(delta) and abs(float(delta)) >= LEVERS["units_total_best"]["threshold"]:
            direction = "up" if float(delta) > 0 else "down"
            counts[("units_total_best", direction)] = counts.get(("units_total_best", direction), 0) + 1
    if refused_reports is not None and not refused_reports.empty:
        for _, row in refused_reports.iterrows():
            for lever, field in REPORT_FIELD_FOR_LEVER.items():
                delta = pd.to_numeric(row.get(f"{field}_delta"), errors="coerce")
                if pd.notna(delta) and abs(float(delta)) >= LEVERS[lever]["threshold"]:
                    direction = "up" if float(delta) > 0 else "down"
                    counts[(lever, direction)] = counts.get((lever, direction), 0) + 1
    return counts


def build_alteration_effects(
    canonical: pd.DataFrame,
    refused_fixed: pd.DataFrame,
    refused_reports: pd.DataFrame | None = None,
) -> dict:
    granted = granted_arm_counts(canonical)
    refused = refused_arm_counts(refused_fixed, refused_reports)
    keys = sorted(set(granted) | set(refused))
    rows = []
    for column, direction in keys:
        granted_n = granted.get((column, direction), 0)
        refused_n = refused.get((column, direction), 0)
        total = granted_n + refused_n
        low, high = wilson(total, granted_n)
        rows.append({
            "lever": LEVERS[column]["label"],
            "column": column,
            "direction": direction,
            "audited_granted": granted_n,
            "audited_refused": refused_n,
            "audited_total": total,
            "grant_share": round(granted_n / total, 4) if total else None,
            "wilson_95_low": round(low, 4) if low is not None else None,
            "wilson_95_high": round(high, 4) if high is not None else None,
            "both_arms_measured": granted_n > 0 and refused_n > 0,
        })
    rows.sort(key=lambda row: (-(row["audited_total"] or 0), -(row["grant_share"] or 0)))
    return {
        "generated": date.today().isoformat(),
        "granted_arm_pairs": int(len(canonical)),
        "refused_arm_pairs": int(len(refused_fixed)),
        "rows": rows,
        "caveat": (
            "Empirical, model-free: how audited resubmissions that made each change ended. "
            "Observational association between audited pairs - never a causal guarantee. "
            "The refused arm is smaller and (until its report campaign) units-only, so "
            "non-units rows carry wide intervals."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    canonical = pd.read_csv(CANONICAL, low_memory=False)
    refused_fixed = pd.read_csv(REFUSED_FIXED, low_memory=False)
    refused_fixed = refused_fixed[
        refused_fixed["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")
    ]
    refused_reports = pd.read_csv(REFUSED_REPORTS, low_memory=False) if REFUSED_REPORTS.exists() else None

    effects = build_alteration_effects(canonical, refused_fixed, refused_reports)
    output = args.output or (CURRENT / f"alteration_effects_{date.today().isoformat()}.json")
    output.write_text(json.dumps(effects, indent=2), encoding="utf-8")
    print(json.dumps(effects, indent=2))


if __name__ == "__main__":
    main()
