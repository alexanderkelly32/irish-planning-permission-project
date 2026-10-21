#!/usr/bin/env python3
"""Build the verification pack for planner-report extractions."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "02_development" / "source_data" / "planner_reports" / "MeathCC"
OUT_DIR = ROOT / "02_development" / "current" / "planner_report_verification_2026-09-05"

EXTRACTION_FIELDS = [
    "max_height_m", "height_context", "max_storeys", "front_setback_m", "rear_setback_m",
    "side_setback_m", "upper_floor_setback_m", "nearest_dwelling_separation_m",
    "opposing_window_separation_m", "parking_spaces", "cycle_parking_spaces",
    "private_open_space_sqm", "communal_open_space_sqm", "vehicular_access_points",
]


def main() -> None:
    merged = pd.read_csv(BASE / "report_ocr_extractions.csv", low_memory=False)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for _, report in merged.iterrows():
        text_path = Path(str(report["text_path"]))
        text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else ""
        entry = {
            "verify_id": "",
            "case_key": str(report["case_key"]),
            "source_file": text_path.name,
            "document_text": text,
        }
        for field in EXTRACTION_FIELDS:
            entry[f"extracted_{field}"] = report.get(f"doc_{field}")
        entry.update({"extraction_note": str(report.get("doc_note") or ""),
                      "extraction_confidence": str(report.get("doc_confidence") or "")})
        for field in EXTRACTION_FIELDS:
            entry[f"verified_{field}"] = ""
        entry.update({"verified_by": "", "verified_at": "", "verify_notes": ""})
        rows.append(entry)
    frame = pd.DataFrame(rows)
    frame["verify_id"] = [f"R{index + 1:03d}" for index in range(len(frame))]
    frame.to_csv(OUT_DIR / "verify_rows.csv", index=False)
    summary = {
        "rows": int(len(frame)),
        "fields": EXTRACTION_FIELDS,
        "note": "Each row is one planner report with its OCR text and the extracted values; blank extracted cells mean the extractor found nothing explicitly stated.",
    }
    (OUT_DIR / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
