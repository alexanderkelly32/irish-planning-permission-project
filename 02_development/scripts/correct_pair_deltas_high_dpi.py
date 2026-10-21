#!/usr/bin/env python3
"""High-DPI correction pass for the numeric values that feed the alteration tables.

Only the reports UNDERLYING pair deltas for parking/height (the fields the
digit-stability audit showed weakest) are re-OCR'd at 300 DPI. Where the
high-DPI pass clearly confirms a different number than the production
140-DPI extraction, a correction row is recorded and applied.

Steps: prepare -> (overnight chain runs OCR) -> apply -> rebuild tables.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "high_dpi_corrections_2026-09-17"

NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")

PAIR_CSVS = [
    CURRENT / "revision_pair_report_extraction_2026-09-13" / "revision_pair_report_extractions.csv",
    CURRENT / "revision_pair_report_extraction_2026-09-13" / "revision_pair_report_extractions_refused_arm.csv",
]
TARGET_FIELDS = ["max_height_m", "parking_spaces"]


def _ref_from_case_key(case_key: object) -> str:
    return str(case_key).split("_")[-1]


def collect_reports() -> pd.DataFrame:
    rows = []
    reports_root = ROOT / "02_development" / "source_data" / "planner_reports"

    queue = pd.read_csv(CURRENT / "full_revision_candidate_queue.csv", low_memory=False)
    key_council = {}
    for _, qrow in queue.iterrows():
        for prefix in ["original", "revised"]:
            key_council[str(qrow.get(f"{prefix}_case_key"))] = str(qrow.get("planning_authority") or "")
    refused = pd.read_csv(CURRENT / "refused_refused_audit_merged.csv", low_memory=False)
    for _, rrow in refused.iterrows():
        for prefix in ["original", "revised"]:
            key_council.setdefault(str(rrow.get(f"{prefix}_case_key")), str(rrow.get("planning_authority") or ""))

    from run_planner_report_download import COUNCIL_PATH

    seen = set()
    for csv_path in PAIR_CSVS:
        if not csv_path.exists():
            continue
        frame = pd.read_csv(csv_path, low_memory=False)
        for _, row in frame.iterrows():
            for field in TARGET_FIELDS:
                delta = pd.to_numeric(row.get(f"{field}_delta"), errors="coerce")
                if pd.isna(delta) or float(delta) == 0.0:
                    continue
                for side in ["original", "revised"]:
                    case_key = str(row.get(f"{side}_case_key"))
                    value = pd.to_numeric(row.get(f"{side}_{field}"), errors="coerce")
                    if pd.isna(value):
                        continue
                    council_dir = COUNCIL_PATH.get(key_council.get(case_key, ""))
                    if not council_dir:
                        continue
                    base = reports_root / council_dir
                    ref = _ref_from_case_key(case_key)
                    candidates = [
                        base / f"{ref}_planner_report.pdf",
                        base / f"{ref}_planner_report_1.pdf",
                        *sorted(base.glob(f"{ref}_planner_report*.pdf")),
                    ]
                    pdf = next((p for p in candidates if p.exists()), None)
                    if pdf is None:
                        continue
                    key = (str(pdf), field, side, float(value))
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "pdf": str(pdf),
                        "field": field,
                        "side": side,
                        "low_dpi_value": float(value),
                        "pair_csv": str(csv_path),
                        "original_case_key": str(row.get("original_case_key")),
                        "revised_case_key": str(row.get("revised_case_key")),
                    })
    return pd.DataFrame(rows)


def prepare() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = collect_reports()
    rows.to_csv(OUT_DIR / "target_reports.csv", index=False)
    print(json.dumps({"target_reports": int(len(rows)), "fields": TARGET_FIELDS}, indent=2))


def _ocr_one(target_row: tuple, page_limit: int) -> dict:
    sys.path.insert(0, str(ROOT / "02_development" / "scripts"))
    from audit_ocr_digit_stability import high_dpi_text

    pdf = Path(target_row[0])
    field = target_row[1]
    side = target_row[2]
    low_value = float(target_row[3])
    if not pdf.exists():
        return None
    text = high_dpi_text(pdf, page_limit=page_limit, dpi=300)
    candidates = []
    for match in NUMBER_PATTERN.finditer(text):
        token = match.group(0)
        try:
            number = float(token)
        except ValueError:
            continue
        if abs(number - low_value) <= max(0.5, abs(low_value) * 0.15):
            candidates.append(number)
    if not candidates:
        return {
            "pdf": str(pdf), "field": field, "side": side,
            "low_dpi_value": low_value, "high_dpi_confirmed": None,
            "correction": "none_found",
        }
    majority = float(max(set(candidates), key=candidates.count))
    if abs(majority - low_value) <= max(0.5, abs(low_value) * 0.05):
        return {
            "pdf": str(pdf), "field": field, "side": side,
            "low_dpi_value": low_value, "high_dpi_confirmed": majority,
            "correction": "confirmed",
        }
    return {
        "pdf": str(pdf), "field": field, "side": side,
        "low_dpi_value": low_value, "high_dpi_confirmed": majority,
        "correction": "correct_to_high_dpi",
    }


def ocr_high_dpi(page_limit: int = 25, workers: int = 3) -> None:
    from concurrent.futures import ProcessPoolExecutor, as_completed

    rows = pd.read_csv(OUT_DIR / "target_reports.csv", low_memory=False)
    targets = [
        (row["pdf"], row["field"], row["side"], row["low_dpi_value"])
        for _, row in rows.iterrows()
    ]
    corrections = []
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_ocr_one, target, page_limit): target for target in targets}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                target = futures[future]
                result = {
                    "pdf": target[0], "field": target[1], "side": target[2],
                    "low_dpi_value": target[3], "high_dpi_confirmed": None,
                    "correction": f"error: {exc}",
                }
            if result is not None:
                corrections.append(result)
            done += 1
            if done % 25 == 0:
                print(f"Progress: {done}/{len(targets)} high-DPI checked", flush=True)
    frame = pd.DataFrame(corrections)
    frame.to_csv(OUT_DIR / "corrections.csv", index=False)
    print(json.dumps(frame["correction"].value_counts().to_dict(), indent=2))


def apply_corrections() -> None:
    corrections = pd.read_csv(OUT_DIR / "corrections.csv", low_memory=False)
    to_fix = corrections[corrections["correction"] == "correct_to_high_dpi"]
    applied = 0
    for csv_path in PAIR_CSVS:
        if not csv_path.exists():
            continue
        frame = pd.read_csv(csv_path, low_memory=False)
        for _, fix in to_fix.iterrows():
            for side in ["original", "revised"]:
                field = fix["field"]
                ref = Path(fix["pdf"]).stem.split("_planner_report")[0]
                mask = frame[f"{side}_case_key"].astype(str).str.split("_").str[-1].eq(ref)
                if mask.any():
                    index = frame[mask].index[0]
                    frame.at[index, f"{side}_{field}"] = float(fix["high_dpi_confirmed"])
                    applied += 1
        for _, row in frame.iterrows():
            for field in TARGET_FIELDS:
                o = pd.to_numeric(row.get(f"original_{field}"), errors="coerce")
                r = pd.to_numeric(row.get(f"revised_{field}"), errors="coerce")
                if pd.notna(o) and pd.notna(r):
                    frame.at[_, f"{field}_delta"] = round(float(r) - float(o), 6)
        frame.to_csv(csv_path, index=False)
    (OUT_DIR / "apply_summary.json").write_text(json.dumps({
        "corrections_applied": applied,
        "note": "Values where the 300-DPI pass clearly confirmed a different number were corrected; deltas recomputed.",
    }, indent=2), encoding="utf-8")
    print(json.dumps({"corrections_applied": applied}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "ocr", "apply"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "ocr":
        ocr_high_dpi()
    else:
        apply_corrections()
