#!/usr/bin/env python3
"""Build the two verification packs for the new extraction layers.

Pack 1 - pair-delta verification (100 rows): for pairs with report-sourced
deltas, show the OCR text context around each side's value and the extracted
original/revised numbers; the reviewer confirms or corrects them against the
PDF text. Measures the delta error rate directly.

Pack 2 - refused-arm theme verification (50 rows): decision-text excerpts with
the extracted tags; the reviewer confirms/corrects the theme tags.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
REPORTS = ROOT / "02_development" / "source_data" / "planner_reports"
DECISIONS = ROOT / "02_development" / "source_data" / "refused_arm_decisions"

sys.path.insert(0, str(ROOT / "02_development" / "scripts"))
from run_planner_report_download import COUNCIL_PATH  # noqa: E402

FIELDS = ["max_storeys", "max_height_m", "parking_spaces", "vehicular_access_points", "nearest_dwelling_separation_m"]


def context_snippet(text: str, value: str, width: int = 260) -> str:
    if not text:
        return ""
    clean = " ".join(text.split())
    needle = str(value).replace(".", ".")
    position = clean.find(needle)
    if position < 0:
        position = max(0, len(clean) // 2)
    start = max(0, position - width // 2)
    return clean[start:start + width]


def build_delta_pack(sample: int = 100) -> None:
    out_dir = CURRENT / f"pair_delta_verification_{date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(
        CURRENT / "revision_pair_report_extraction_2026-09-13" / "revision_pair_report_extractions.csv",
        low_memory=False,
    )
    delta_fields = [f for f in FIELDS if f"{f}_delta" in frame.columns]
    rows = []
    for _, row in frame.iterrows():
        for field in delta_fields:
            delta = pd.to_numeric(row.get(f"{field}_delta"), errors="coerce")
            if pd.isna(delta):
                continue
            rows.append({
                "original_case_key": str(row.get("original_case_key")),
                "revised_case_key": str(row.get("revised_case_key")),
                "field": field,
                "original_value": row.get(f"original_{field}"),
                "revised_value": row.get(f"revised_{field}"),
                "extracted_delta": float(delta),
            })
    candidates = pd.DataFrame(rows)
    rng = random.Random(20260916)
    if candidates.empty:
        print(json.dumps({"status": "no_delta_rows"}))
        return
    sample_rows = candidates.sample(n=min(sample, len(candidates)), random_state=42)

    pack = []
    for _, row in sample_rows.iterrows():
        original_text = ""
        revised_text = ""
        council = ""
        for name, path in COUNCIL_PATH.items():
            ref = str(row["original_case_key"]).split("_")[-1]
            for side_key in ["original", "revised"]:
                case_key = str(row.get(f"{side_key}_case_key"))
                ref_value = case_key.split("_")[-1]
                ocr_dir = REPORTS / path / "ocr_text"
                for text_file in ocr_dir.glob(f"{ref_value}_planner_report*_ocr.txt"):
                    text = text_file.read_text(encoding="utf-8", errors="replace")
                    value = row.get(f"{side_key}_value")
                    snippet = context_snippet(text, str(value)) if value is not None else ""
                    if side_key == "original":
                        original_text = snippet
                    else:
                        revised_text = snippet
                    council = name
                    break
        pack.append({
            "verify_id": "",
            "council": council,
            "field": row["field"],
            "original_case_key": row["original_case_key"],
            "revised_case_key": row["revised_case_key"],
            "extracted_original_value": row["original_value"],
            "extracted_revised_value": row["revised_value"],
            "extracted_delta": row["extracted_delta"],
            "original_text_context": original_text,
            "revised_text_context": revised_text,
            "verified_original_value": "",
            "verified_revised_value": "",
            "correct_delta_direction": "",
            "verified_by": "",
            "verified_at": "",
            "verify_notes": "",
        })
    frame_out = pd.DataFrame(pack)
    frame_out["verify_id"] = [f"D{i + 1:03d}" for i in range(len(frame_out))]
    frame_out.to_csv(out_dir / "verify_rows.csv", index=False)
    (out_dir / "pack_summary.json").write_text(json.dumps({
        "rows": int(len(frame_out)),
        "note": "Check each pair's original/revised values against the text context; correct the values and confirm the delta direction. Save as verify_rows_fixed.csv.",
    }, indent=2), encoding="utf-8")
    print(json.dumps({"pack": "pair_delta_verification", "rows": int(len(frame_out)), "dir": str(out_dir)}, indent=2))


def build_theme_pack(sample: int = 50) -> None:
    out_dir = CURRENT / f"refused_theme_verification_{date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    themes = pd.read_csv(CURRENT / "refused_arm_themes.csv", low_memory=False)
    tagged = themes[themes["case_primary_tags"].fillna("").astype(str).str.strip().ne("")].copy()
    rng = random.Random(20260916)
    if tagged.empty:
        print(json.dumps({"status": "no_tagged_rows"}))
        return
    sample_rows = tagged.sample(n=min(sample, len(tagged)), random_state=42)
    pack = []
    for _, row in sample_rows.iterrows():
        text = ""
        key = str(row.get("original_case_key"))
        ref = key.split("_")[-1]
        for council_dir in sorted(DECISIONS.iterdir()):
            if not council_dir.is_dir():
                continue
            ocr_path = council_dir / "ocr_text" / f"{ref}_decision_ocr.txt"
            if ocr_path.exists():
                text = " ".join(ocr_path.read_text(encoding="utf-8", errors="replace").split())[:8000]
                break
        pack.append({
            "verify_id": "",
            "original_case_key": key,
            "decision_text": text,
            "extracted_tags": str(row.get("case_primary_tags") or ""),
            "extracted_top_tag": str(row.get("case_top_primary_tag") or ""),
            "extracted_evidence": str(row.get("evidence") or ""),
            "verified_tags": "",
            "verified_top_tag": "",
            "verified_by": "",
            "verified_at": "",
            "verify_notes": "",
        })
    frame_out = pd.DataFrame(pack)
    frame_out["verify_id"] = [f"T{i + 1:03d}" for i in range(len(frame_out))]
    frame_out.to_csv(out_dir / "verify_rows.csv", index=False)
    (out_dir / "pack_summary.json").write_text(json.dumps({
        "rows": int(len(frame_out)),
        "note": "Check each extracted theme against the decision text; correct tags/top tag. Save as verify_rows_fixed.csv.",
    }, indent=2), encoding="utf-8")
    print(json.dumps({"pack": "refused_theme_verification", "rows": int(len(frame_out)), "dir": str(out_dir)}, indent=2))


if __name__ == "__main__":
    build_delta_pack()
    build_theme_pack()
