#!/usr/bin/env python3
"""Theme-matched alteration effects: does changing the lever the refusal
ACTUALLY CITED precede grants more often than refusals?

Contrasts, per lever + direction:
- on-diagnosis: pairs whose original refusal cited a theme mapped to that lever
- off-diagnosis: pairs whose original refusal cited no such theme

If addressing the cited problem helps, on-diagnosis grant shares should exceed
off-diagnosis shares. This is the confounder-aware version of the alteration
table (a pair cutting parking because policy demanded it, while refused for
design, is off-diagnosis for parking and no longer pollutes the parking row).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"

sys.path.insert(0, str(ROOT / "06_copilot" / "scripts"))
from theme_lever_bridge import THEME_TO_FIELD  # noqa: E402
from recommendation_grader import MATERIAL_MAGNITUDE, STRUCTURED_TO_SCHEME_FIELD  # noqa: E402

LEVER_TO_THEMES: dict[str, set[str]] = {}
for theme, fields in THEME_TO_FIELD.items():
    for field in fields:
        LEVER_TO_THEMES.setdefault(field, set()).add(theme)


def wilson(n: int, k: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (centre - margin) / denom, (centre + margin) / denom


def granted_pairs_with_deltas(canonical: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in canonical.iterrows():
        try:
            deltas = json.loads(str(row.get("feature_delta_json") or "{}"))
        except (TypeError, ValueError):
            continue
        for column, delta in deltas.items():
            if not isinstance(delta, dict):
                continue
            value = float(delta.get("delta", 0.0) or 0.0)
            if abs(value) < MATERIAL_MAGNITUDE.get(column, 0.0):
                continue
            rows.append({
                "original_case_key": str(row.get("original_case_key")),
                "themes": [t.strip() for t in str(row.get("refusal_themes_original") or "").split(";") if t.strip()],
                "lever": STRUCTURED_TO_SCHEME_FIELD.get(column, column),
                "direction": "up" if value > 0 else "down",
                "outcome": "granted",
            })
    return pd.DataFrame(rows)


def refused_pairs_with_deltas(refused_fixed: pd.DataFrame, refused_reports: pd.DataFrame | None, themes_csv: pd.DataFrame | None) -> pd.DataFrame:
    rows = []
    theme_lookup = {}
    if themes_csv is not None and not themes_csv.empty:
        theme_lookup = dict(zip(
            themes_csv["original_case_key"].astype(str),
            themes_csv["case_primary_tags"].fillna("").astype(str),
        ))
    report_lookup: dict[tuple[str, str], pd.Series] = {}
    if refused_reports is not None and not refused_reports.empty:
        report_lookup = {
            (str(row["original_case_key"]), str(row["revised_case_key"])): row
            for _, row in refused_reports.iterrows()
        }
    report_field_to_lever = {
        "max_storeys": "max_storeys", "parking_spaces": "parking_spaces",
        "max_height_m": "max_height_m", "vehicular_access_points": "vehicular_access_points",
        "nearest_dwelling_separation_m": "nearest_dwelling_separation_m",
        "communal_open_space_sqm": "communal_open_space_sqm",
    }
    for _, row in refused_fixed.iterrows():
        key = (str(row.get("original_case_key")), str(row.get("revised_case_key")))
        themes = [t.strip() for t in theme_lookup.get(str(row.get("original_case_key")), "").split(";") if t.strip()]
        units_delta = pd.to_numeric(row.get("units_delta"), errors="coerce")
        if pd.notna(units_delta) and abs(float(units_delta)) >= MATERIAL_MAGNITUDE["units_total_best"]:
            rows.append({
                "original_case_key": str(row.get("original_case_key")),
                "themes": themes,
                "lever": "units",
                "direction": "up" if float(units_delta) > 0 else "down",
                "outcome": "refused",
            })
        report_row = report_lookup.get(key)
        if report_row is not None:
            for field, lever in report_field_to_lever.items():
                delta = pd.to_numeric(report_row.get(f"{field}_delta"), errors="coerce")
                column = {v: k for k, v in STRUCTURED_TO_SCHEME_FIELD.items()}.get(lever, lever)
                if pd.notna(delta) and abs(float(delta)) >= MATERIAL_MAGNITUDE.get(column, 0.0):
                    rows.append({
                        "original_case_key": str(row.get("original_case_key")),
                        "themes": themes,
                        "lever": lever,
                        "direction": "up" if float(delta) > 0 else "down",
                        "outcome": "refused",
                    })
    return pd.DataFrame(rows)


def build_theme_matched_effects(
    granted: pd.DataFrame,
    refused: pd.DataFrame,
) -> dict:
    levers = sorted(set(granted["lever"]) | set(refused["lever"]))
    rows = []
    for lever in levers:
        themes = LEVER_TO_THEMES.get(lever, set())
        granted_lev = granted[granted["lever"] == lever]
        refused_lev = refused[refused["lever"] == lever]
        for direction in ["down", "up"]:
            granted_dir = granted_lev[granted_lev["direction"] == direction]
            refused_dir = refused_lev[refused_lev["direction"] == direction]
            for label, sub_granted, sub_refused in [
                ("on_diagnosis",
                 granted_dir[granted_dir["themes"].apply(lambda t: bool(set(t) & themes))],
                 refused_dir[refused_dir["themes"].apply(lambda t: bool(set(t) & themes))]),
                ("off_diagnosis",
                 granted_dir[granted_dir["themes"].apply(lambda t: not bool(set(t) & themes))],
                 refused_dir[refused_dir["themes"].apply(lambda t: not bool(set(t) & themes))]),
            ]:
                g = int(len(sub_granted))
                r = int(len(sub_refused))
                total = g + r
                low, high = wilson(total, g)
                rows.append({
                    "lever": lever,
                    "direction": direction,
                    "diagnosis": label,
                    "granted": g,
                    "refused": r,
                    "total": total,
                    "grant_share": round(g / total, 4) if total else None,
                    "wilson_95_low": round(low, 4) if low is not None else None,
                    "wilson_95_high": round(high, 4) if high is not None else None,
                })
    return {
        "generated": date.today().isoformat(),
        "granted_pairs": int(len(granted)),
        "refused_pairs": int(len(refused)),
        "granted_pairs_with_themes": int(granted["themes"].astype(bool).sum()),
        "refused_pairs_with_themes": int(refused["themes"].astype(bool).sum()),
        "rows": rows,
        "caveat": (
            "On-diagnosis = the original refusal cited a theme mapped to the lever. "
            "Off-diagnosis pairs changed the lever for other reasons (e.g. policy). "
            "Observational association between audited pairs; small cells carry wide intervals."
        ),
    }


def main() -> None:
    canonical = pd.read_csv(CURRENT / "canonical_revision_scheme_records.csv", low_memory=False)
    refused_fixed = pd.read_csv(CURRENT / "refused_refused_audit_merged.csv", low_memory=False)
    refused_fixed = refused_fixed[refused_fixed["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")]
    refused_reports = pd.read_csv(
        CURRENT / "revision_pair_report_extraction_2026-09-13" / "revision_pair_report_extractions_refused_arm.csv",
        low_memory=False,
    ) if (CURRENT / "revision_pair_report_extraction_2026-09-13" / "revision_pair_report_extractions_refused_arm.csv").exists() else None
    themes_csv = pd.read_csv(CURRENT / "refused_arm_themes.csv", low_memory=False) if (CURRENT / "refused_arm_themes.csv").exists() else None

    granted = granted_pairs_with_deltas(canonical)
    refused = refused_pairs_with_deltas(refused_fixed, refused_reports, themes_csv)
    effects = build_theme_matched_effects(granted, refused)
    (CURRENT / f"theme_matched_effects_{date.today().isoformat()}.json").write_text(
        json.dumps(effects, indent=2), encoding="utf-8"
    )
    print(json.dumps(effects, indent=2))


if __name__ == "__main__":
    main()
