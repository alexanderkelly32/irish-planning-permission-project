#!/usr/bin/env python3
"""Build the lever-contrast table: audited refused->revised->granted pairs vs
audited refused->revised->refused pairs, by lever change.

For each lever (field + direction) the table reports how many audited
resubmissions that made that change ended granted vs refused. This is the first
observational contrast form of "this change preceded grants X vs Y times".
It is association evidence, NOT a causal guarantee.

The refused arm requires the returned refused->refused audit pack
(refused_refused_audit_2026-09-09/review_rows_fixed.csv); until then the table
reports the granted arm only with status "blocked_on_audit".
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
CANONICAL_RECORDS = CURRENT / "canonical_revision_scheme_records.csv"
REFUSED_AUDIT_DIR = CURRENT / "refused_refused_audit_2026-09-09"

MATERIAL = {
    "units_total_best": 3.0,
    "max_storeys_best": 1.0,
    "parking_spaces_best": 2.0,
    "cycle_parking_spaces_best": 2.0,
    "open_space_sqm_best": 10.0,
    "site_area_sqm_best": 10.0,
    "floor_area_sqm_best": 20.0,
}
FIELD_LABELS = {
    "units_total_best": "units",
    "max_storeys_best": "max storeys",
    "parking_spaces_best": "parking spaces",
    "cycle_parking_spaces_best": "cycle parking",
    "open_space_sqm_best": "open space (sqm)",
    "site_area_sqm_best": "site area (sqm)",
    "floor_area_sqm_best": "floor area (sqm)",
}


def wilson(n: int, k: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (centre - margin) / denom, (centre + margin) / denom


def granted_arm_levers(records: pd.DataFrame) -> dict[tuple[str, str], int]:
    """Count material lever changes among audited refused->granted pairs."""
    counts: dict[tuple[str, str], int] = {}
    for _, row in records.iterrows():
        try:
            deltas = json.loads(str(row.get("feature_delta_json") or "{}"))
        except (TypeError, ValueError):
            continue
        if not isinstance(deltas, dict):
            continue
        for column, delta in deltas.items():
            if not isinstance(delta, dict):
                continue
            magnitude = abs(float(delta.get("delta", 0.0) or 0.0))
            if magnitude < MATERIAL.get(column, 0.0):
                continue
            direction = "up" if float(delta.get("delta", 0.0) or 0.0) > 0 else "down"
            key = (column, direction)
            counts[key] = counts.get(key, 0) + 1
    return counts


def refused_arm_levers(audit: pd.DataFrame) -> dict[tuple[str, str], int]:
    """Count material units changes among accepted audited refused->refused pairs."""
    counts: dict[tuple[str, str], int] = {}
    accepted = audit[
        audit["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")
    ]
    for _, row in accepted.iterrows():
        delta = pd.to_numeric(row.get("units_delta"), errors="coerce")
        if pd.isna(delta) or abs(float(delta)) < MATERIAL["units_total_best"]:
            continue
        direction = "up" if float(delta) > 0 else "down"
        key = ("units_total_best", direction)
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_lever_contrast(
    records: pd.DataFrame,
    audit: pd.DataFrame | None,
) -> dict:
    granted = granted_arm_levers(records)
    refused = refused_arm_levers(audit) if audit is not None else {}
    keys = sorted(set(granted) | set(refused))
    rows = []
    for column, direction in keys:
        granted_n = granted.get((column, direction), 0)
        refused_n = refused.get((column, direction), 0)
        total = granted_n + refused_n
        low, high = wilson(total, granted_n)
        rows.append({
            "lever": FIELD_LABELS.get(column, column),
            "structured_column": column,
            "direction": direction,
            "audited_granted_pairs": granted_n,
            "audited_refused_pairs": refused_n,
            "audited_total": total,
            "grant_share": round(granted_n / total, 4) if total else None,
            "wilson_95_low": round(low, 4) if low is not None else None,
            "wilson_95_high": round(high, 4) if high is not None else None,
            "refused_arm_measured": refused_n > 0,
        })
    blocked = audit is None
    return {
        "generated": date.today().isoformat(),
        "status": "blocked_on_audit" if blocked else "complete",
        "granted_arm_pairs": int(len(records)),
        "refused_arm_audited_pairs": int(len(audit)) if audit is not None else 0,
        "refused_arm_accepted_pairs": (
            int(audit["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted").sum())
            if audit is not None else 0
        ),
        "rows": rows,
        "caveat": (
            "Observational contrast between audited resubmission arms. The granted arm "
            "carries extraction-verified structured deltas; the refused arm currently "
            "supports units only (register values). Association, not causation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audit",
        type=Path,
        default=None,
        help="completed refused->refused audit CSV (defaults to the expected fixed file if present)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    records = pd.read_csv(CANONICAL_RECORDS, low_memory=False)
    audit = None
    audit_path = args.audit
    if audit_path is None:
        fixed = REFUSED_AUDIT_DIR / "review_rows_fixed.csv"
        audit_path = fixed if fixed.exists() else None
    if audit_path is not None:
        audit = pd.read_csv(audit_path, low_memory=False)

    contrast = build_lever_contrast(records, audit)
    output = args.output or (CURRENT / f"lever_contrast_{date.today().isoformat()}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contrast, indent=2), encoding="utf-8")
    print(json.dumps(contrast, indent=2))


if __name__ == "__main__":
    main()
