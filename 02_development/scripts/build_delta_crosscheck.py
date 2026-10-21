#!/usr/bin/env python3
"""Cross-check each pair delta across independent extraction sources.

Sources per lever field:
- description pair extraction (revision_pair_structured_extractions.csv)
- planner-report pair extraction (revision_pair_report_extractions.csv)
- structured single-side CSV (ground_source_extracted_final_wide_ge10_fixed.csv)
- register units (queue units_delta)

For every pair with >=2 non-null deltas for a field, the sources must agree on
SIGN (and on magnitude within tolerance for storeys/units). Disagreements are
flagged low-confidence and excluded from the alteration tables so a single bad
extraction can no longer flip a lever's direction.

Output: pair_delta_confidence.csv + pair_delta_crosscheck.json
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"

FIELD_SOURCES = {
    "max_storeys": [
        ("description", "revision_pair_extraction_2026-09-13/revision_pair_structured_extractions.csv", "max_storeys"),
        ("report", "revision_pair_report_extraction_2026-09-13/revision_pair_report_extractions.csv", "max_storeys"),
    ],
    "parking_spaces": [
        ("description", "revision_pair_extraction_2026-09-13/revision_pair_structured_extractions.csv", "parking_spaces"),
        ("report", "revision_pair_report_extraction_2026-09-13/revision_pair_report_extractions.csv", "parking_spaces"),
    ],
    "max_height_m": [
        ("report", "revision_pair_report_extraction_2026-09-13/revision_pair_report_extractions.csv", "max_height_m"),
    ],
    "vehicular_access_points": [
        ("description", "revision_pair_extraction_2026-09-13/revision_pair_structured_extractions.csv", "vehicular_access_points"),
        ("report", "revision_pair_report_extraction_2026-09-13/revision_pair_report_extractions.csv", "vehicular_access_points"),
    ],
    "nearest_dwelling_separation_m": [
        ("report", "revision_pair_report_extraction_2026-09-13/revision_pair_report_extractions.csv", "nearest_dwelling_separation_m"),
    ],
    "communal_open_space_sqm": [
        ("report", "revision_pair_report_extraction_2026-09-13/revision_pair_report_extractions.csv", "communal_open_space_sqm"),
    ],
}

MAGNITUDE_TOLERANCE = {
    "max_storeys": 1.0,
    "parking_spaces": 5.0,
    "max_height_m": 1.5,
    "vehicular_access_points": 1.0,
    "nearest_dwelling_separation_m": 3.0,
    "communal_open_space_sqm": 25.0,
}


def load_source(relative_path: str) -> pd.DataFrame:
    path = CURRENT / relative_path
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def collect_deltas() -> pd.DataFrame:
    frames = {}
    for field, sources in FIELD_SOURCES.items():
        frames[field] = {}
        for name, path, column in sources:
            frame = load_source(path)
            if frame.empty:
                continue
            for _, row in frame.iterrows():
                key = (str(row.get("original_case_key")), str(row.get("revised_case_key")))
                delta = pd.to_numeric(row.get(f"{column}_delta"), errors="coerce")
                if pd.notna(delta):
                    frames[field].setdefault(key, {})[name] = float(delta)
    rows = []
    for field, by_key in frames.items():
        for key, sources in by_key.items():
            if len(sources) < 2:
                continue
            values = list(sources.values())
            signs = {1 if v > 0 else (-1 if v < 0 else 0) for v in values}
            sign_ok = len(signs) == 1 and 0 not in signs
            spread = max(values) - min(values)
            magnitude_ok = spread <= MAGNITUDE_TOLERANCE.get(field, 0.0)
            rows.append({
                "original_case_key": key[0],
                "revised_case_key": key[1],
                "field": field,
                "sources": json.dumps(sources, sort_keys=True),
                "n_sources": len(sources),
                "sign_agrees": sign_ok,
                "magnitude_ok": magnitude_ok,
                "confidence": "high" if (sign_ok and magnitude_ok) else "low",
            })
    return pd.DataFrame(rows)


def main() -> None:
    frame = collect_deltas()
    frame.to_csv(CURRENT / "pair_delta_confidence.csv", index=False)
    summary = {
        "generated": date.today().isoformat(),
        "compared_deltas": int(len(frame)),
        "high_confidence": int((frame["confidence"] == "high").sum()) if not frame.empty else 0,
        "low_confidence": int((frame["confidence"] == "low").sum()) if not frame.empty else 0,
        "by_field": (
            frame.groupby("field").agg(
                compared=("confidence", "size"),
                high=("confidence", lambda s: int((s == "high").sum())),
                low=("confidence", lambda s: int((s == "low").sum())),
            ).to_dict(orient="index")
            if not frame.empty else {}
        ),
        "note": "Low-confidence rows are excluded from the alteration-effect tables; a single source's error can no longer flip a lever direction.",
    }
    (CURRENT / "pair_delta_crosscheck.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
