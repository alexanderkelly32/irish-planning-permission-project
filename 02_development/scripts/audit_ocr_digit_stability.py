#!/usr/bin/env python3
"""Digit-stability audit: re-OCR a bounded sample of reports at 300 DPI and
compare the numeric values with the 140-DPI extraction.

The 140-DPI pass is what all pair deltas are built on; digit misreads there
silently corrupt deltas. This measures the corruption rate per field so the
"reliant on the planner report" risk becomes a number.

Output: raw_planning_ocr_digit_stability.json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import fitz
import numpy as np
import pandas as pd
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
REPORTS = ROOT / "02_development" / "source_data" / "planner_reports"

FIELDS = {
    "max_storeys": "doc_max_storeys",
    "max_height_m": "doc_max_height_m",
    "parking_spaces": "doc_parking_spaces",
    "vehicular_access_points": "doc_vehicular_access_points",
    "nearest_dwelling_separation_m": "doc_nearest_dwelling_separation_m",
}
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def high_dpi_text(pdf_path: Path, page_limit: int, dpi: int) -> str:
    doc = fitz.open(str(pdf_path))
    max_pages = min(len(doc), max(1, page_limit))
    zoom = max(1.2, dpi / 96.0)
    mat = fitz.Matrix(zoom, zoom)
    engine = RapidOCR()
    lines: list[str] = []
    for page_idx in range(max_pages):
        try:
            pix = doc[page_idx].get_pixmap(matrix=mat, alpha=False)
            result, _ = engine(pix.tobytes("png"))
            if result:
                lines.extend(x[1] for x in result if len(x) > 1 and str(x[1]).strip())
        except Exception:
            continue
    return "\n".join(lines)


def _numbers_near(text: str, value: float, window: int = 120) -> list[float]:
    clean = " ".join(text.split())
    needle = str(value).rstrip("0").rstrip(".")
    candidates = []
    for match in NUMBER_PATTERN.finditer(clean):
        token = match.group(0)
        if abs(float(token) - value) <= max(0.5, abs(value) * 0.15):
            start = max(0, match.start() - window // 2)
            snippet = clean[start:match.end() + window // 2]
            candidates.append((float(token), snippet))
    return candidates


def main() -> None:
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--sample", type=int, default=40)
    parser.add_argument("--page-limit", type=int, default=25)
    args = parser.parse_args()

    rows = []
    for csv_path in sorted(REPORTS.rglob("report_ocr_extractions.csv")):
        frame = pd.read_csv(csv_path, low_memory=False)
        for _, row in frame.iterrows():
            text_path = Path(str(row.get("text_path") or ""))
            if not text_path.exists():
                continue
            values = {field: row.get(column) for field, column in FIELDS.items() if column in frame.columns and pd.notna(row.get(column))}
            if not values:
                continue
            pdf_path = text_path.parent.parent / (text_path.stem.replace("_ocr", "") + ".pdf")
            if not pdf_path.exists():
                continue
            rows.append({"pdf": str(pdf_path), "values": values, "low_dpi_text": text_path.read_text(encoding="utf-8", errors="replace")})
    rng = np.random.default_rng(20260916)
    sample = [rows[i] for i in rng.choice(len(rows), size=min(args.sample, len(rows)), replace=False)] if rows else []

    results = []
    for item in sample:
        high_text = high_dpi_text(Path(item["pdf"]), page_limit=args.page_limit, dpi=300)
        for field, value in item["values"].items():
            value = float(value)
            low_hits = _numbers_near(item["low_dpi_text"], value)
            high_hits = _numbers_near(high_text, value)
            low_confirms = any(abs(hit[0] - value) <= max(0.5, abs(value) * 0.1) for hit in low_hits)
            high_confirms = any(abs(hit[0] - value) <= max(0.5, abs(value) * 0.1) for hit in high_hits)
            results.append({
                "field": field,
                "extracted_value": value,
                "confirmed_at_140dpi": bool(low_confirms),
                "confirmed_at_300dpi": bool(high_confirms),
                "stable": bool(low_confirms and high_confirms),
            })

    frame = pd.DataFrame(results)
    if frame.empty:
        payload = {"status": "no_comparable_values"}
    else:
        by_field = {}
        for field, group in frame.groupby("field"):
            by_field[field] = {
                "n": int(len(group)),
                "confirmed_140": round(float(group["confirmed_at_140dpi"].mean()), 4),
                "confirmed_300": round(float(group["confirmed_at_300dpi"].mean()), 4),
                "stable": round(float(group["stable"].mean()), 4),
            }
        payload = {
            "generated": date.today().isoformat(),
            "reports_sampled": len(sample),
            "values_compared": int(len(frame)),
            "overall_stable_rate": round(float(frame["stable"].mean()), 4),
            "by_field": by_field,
            "caveat": "Digit-stability of extracted numeric values between the 140-DPI production pass and a 300-DPI re-OCR. A low stable rate means deltas built on these values carry digit noise.",
        }
    (CURRENT / "raw_planning_ocr_digit_stability.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
