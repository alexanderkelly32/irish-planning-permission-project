#!/usr/bin/env python3
"""Build the human document-extraction review pack (verified tier)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from structured_document_extraction import EXTRACTION_FIELDS, build_document_cohort

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "document_extraction_review_2026-09-04"
OCR_DIR = ROOT / "03_refusal" / "documents" / "ocr"
FI_DIR = ROOT / "04_fi" / "source_data" / "fi_case_text"


def select_review_cohort(cohort: pd.DataFrame, per_authority: int = 20, seed: int = 20260904) -> pd.DataFrame:
    """Deterministic, authority-stratified document sample for human extraction."""
    frame = cohort.copy()
    authority_counts = frame["authority"].value_counts()
    top_authorities = list(authority_counts.index[:8])
    selected = []
    for authority in top_authorities:
        group = frame[frame["authority"] == authority].copy()
        group["_order"] = [
            hashlib.sha256(f"{seed}|{text_path}".encode("utf-8")).hexdigest()
            for text_path in group["text_path"]
        ]
        selected.append(group.sort_values("_order").head(per_authority).drop(columns="_order"))
    rest = frame[~frame["authority"].isin(top_authorities)].copy()
    if not rest.empty:
        rest["_order"] = [
            hashlib.sha256(f"{seed}|{text_path}".encode("utf-8")).hexdigest()
            for text_path in rest["text_path"]
        ]
        selected.append(rest.sort_values("_order").head(40).drop(columns="_order"))
    return pd.concat(selected, ignore_index=True)


def build_review_rows(selected: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in selected.iterrows():
        text = Path(str(row["text_path"])).read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        entry = {
            "review_id": "",
            "case_key": str(row["case_key"]),
            "authority": str(row["authority"]),
            "document_type": str(row["document_type"]),
            "source_file": Path(str(row["text_path"])).name,
            "document_text": text,
        }
        for field in EXTRACTION_FIELDS:
            entry[f"extracted_{field}"] = ""
        entry.update({"extraction_notes": "", "extracted_by": "", "extracted_at": ""})
        rows.append(entry)
    frame = pd.DataFrame(rows)
    frame["review_id"] = [f"D{index + 1:03d}" for index in range(len(frame))]
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-authority", type=int, default=20)
    args = parser.parse_args()

    cohort = build_document_cohort(OCR_DIR, FI_DIR)
    selected = select_review_cohort(cohort, per_authority=args.per_authority)
    review_rows = build_review_rows(selected)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    review_rows.to_csv(OUT_DIR / "extract_rows.csv", index=False)
    summary = {
        "document_rows_in_corpus": int(len(cohort)),
        "review_rows": int(len(review_rows)),
        "by_authority": review_rows["authority"].value_counts().to_dict(),
        "by_document_type": review_rows["document_type"].value_counts().to_dict(),
        "fields": EXTRACTION_FIELDS,
    }
    (OUT_DIR / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
