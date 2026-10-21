#!/usr/bin/env python3
"""
Extract structured FI request items from per-case FI text corpus without truncation.

Inputs:
- extraction_of_site_data/fi_case_text_summary.csv
- extraction_of_site_data/fi_case_text/*.txt

Outputs:
- extraction_of_site_data/fi_request_items_long.csv
- extraction_of_site_data/fi_request_items_cases.csv
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd


DEFAULT_CASE_SUMMARY = Path("extraction_of_site_data/fi_case_text_summary.csv")
DEFAULT_LONG_OUTPUT = Path("extraction_of_site_data/fi_request_items_long.csv")
DEFAULT_CASE_OUTPUT = Path("extraction_of_site_data/fi_request_items_cases.csv")


FILE_HEADER_RE = re.compile(r"^\[FILE\]\s*(.+?)\s*$", flags=re.MULTILINE)
TYPE_HEADER_RE = re.compile(r"^\[TYPE\]\s*(.+?)\s*$", flags=re.MULTILINE)
BLOCK_SPLIT_RE = re.compile(r"\n\s*-{40,}\s*\n", flags=re.MULTILINE)

NUMBERED_ITEM_RE = re.compile(
    r"(?ms)^\s*(?:\(?\d{1,3}[.)]|\d{1,3}\s*[-:])\s+(.+?)(?=^\s*(?:\(?\d{1,3}[.)]|\d{1,3}\s*[-:])\s+|\Z)"
)
BULLET_ITEM_RE = re.compile(
    r"(?ms)^\s*(?:[-*•]\s+)(.+?)(?=^\s*(?:[-*•]\s+)|\Z)"
)
LETTERED_ITEM_RE = re.compile(
    r"(?ms)^\s*(?:\(?[a-zA-Z][.)])\s+(.+?)(?=^\s*(?:\(?[a-zA-Z][.)])\s+|\Z)"
)


def clean(v: object) -> str:
    if v is None:
        return ""
    s = str(v)
    if s.lower() in {"nan", "none", "nat"}:
        return ""
    return s


@dataclass
class DocBlock:
    file_name: str
    doc_type: str
    text: str


def parse_case_text_blocks(full_text: str) -> List[DocBlock]:
    text = clean(full_text)
    if not text.strip():
        return []

    blocks = BLOCK_SPLIT_RE.split(text)
    out: List[DocBlock] = []
    for block in blocks:
        b = block.strip()
        if not b:
            continue
        fm = FILE_HEADER_RE.search(b)
        tm = TYPE_HEADER_RE.search(b)
        file_name = fm.group(1).strip() if fm else ""
        doc_type = tm.group(1).strip() if tm else ""

        # Remove metadata header lines only; keep all body text intact.
        body = re.sub(r"^\[FILE\].*$", "", b, flags=re.MULTILINE)
        body = re.sub(r"^\[TYPE\].*$", "", body, flags=re.MULTILINE).strip()
        if body:
            out.append(DocBlock(file_name=file_name, doc_type=doc_type, text=body))
    return out


def extract_items_from_text(text: str) -> tuple[List[str], str]:
    t = clean(text).strip()
    if not t:
        return [], "empty"

    numbered = [m.group(1).strip() for m in NUMBERED_ITEM_RE.finditer(t) if m.group(1).strip()]
    if len(numbered) >= 2:
        return numbered, "numbered"

    bullets = [m.group(1).strip() for m in BULLET_ITEM_RE.finditer(t) if m.group(1).strip()]
    if len(bullets) >= 2:
        return bullets, "bulleted"

    lettered = [m.group(1).strip() for m in LETTERED_ITEM_RE.finditer(t) if m.group(1).strip()]
    if len(lettered) >= 2:
        return lettered, "lettered"

    # Fallback: paragraph-level split; preserve all text content.
    paras = [p.strip() for p in re.split(r"\n\s*\n+", t) if p.strip()]
    if len(paras) >= 2:
        return paras, "paragraph"

    # Final fallback: one full item with the complete document text.
    return [t], "single_full_text"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract structured FI request items without truncation.")
    parser.add_argument("--case-summary", default=str(DEFAULT_CASE_SUMMARY))
    parser.add_argument("--long-output", default=str(DEFAULT_LONG_OUTPUT))
    parser.add_argument("--case-output", default=str(DEFAULT_CASE_OUTPUT))
    args = parser.parse_args()

    case_summary_path = Path(args.case_summary)
    long_output_path = Path(args.long_output)
    case_output_path = Path(args.case_output)

    cases = pd.read_csv(case_summary_path, low_memory=False, dtype={"ApplicationNumber": str})
    need = {"case_key", "PlanningAuthority", "ApplicationNumber", "fi_case_text_path"}
    missing = [c for c in need if c not in cases.columns]
    if missing:
        raise ValueError(f"Missing columns in case summary: {missing}")

    long_rows: List[dict] = []
    case_rows: List[dict] = []

    for _, row in cases.iterrows():
        case_key = clean(row.get("case_key"))
        authority = clean(row.get("PlanningAuthority"))
        app = clean(row.get("ApplicationNumber"))
        case_text_path = Path(clean(row.get("fi_case_text_path")))

        if not case_text_path.exists():
            case_rows.append(
                {
                    "case_key": case_key,
                    "PlanningAuthority": authority,
                    "ApplicationNumber": app,
                    "fi_case_text_path": str(case_text_path),
                    "documents_parsed": 0,
                    "request_items_count": 0,
                    "status": "missing_case_text",
                }
            )
            continue

        full_text = case_text_path.read_text(encoding="utf-8", errors="ignore")
        blocks = parse_case_text_blocks(full_text)
        item_count = 0

        for doc_i, block in enumerate(blocks, start=1):
            items, method = extract_items_from_text(block.text)
            for item_i, item_text in enumerate(items, start=1):
                item_count += 1
                long_rows.append(
                    {
                        "case_key": case_key,
                        "PlanningAuthority": authority,
                        "ApplicationNumber": app,
                        "fi_case_text_path": str(case_text_path),
                        "document_index": doc_i,
                        "document_file_name": block.file_name,
                        "document_type": block.doc_type,
                        "item_index_within_document": item_i,
                        "extraction_method": method,
                        "request_item_text": item_text,  # intentionally untruncated
                    }
                )

        case_rows.append(
            {
                "case_key": case_key,
                "PlanningAuthority": authority,
                "ApplicationNumber": app,
                "fi_case_text_path": str(case_text_path),
                "documents_parsed": len(blocks),
                "request_items_count": item_count,
                "status": "ok",
            }
        )

    long_df = pd.DataFrame(long_rows)
    case_df = pd.DataFrame(case_rows)

    long_output_path.parent.mkdir(parents=True, exist_ok=True)
    case_output_path.parent.mkdir(parents=True, exist_ok=True)
    long_df.to_csv(long_output_path, index=False)
    case_df.to_csv(case_output_path, index=False)

    print(f"Wrote: {long_output_path} ({len(long_df)} rows)")
    print(f"Wrote: {case_output_path} ({len(case_df)} rows)")
    if len(case_df):
        print("Case status counts:")
        print(case_df["status"].value_counts(dropna=False).to_string())
    if len(case_df):
        print(f"Cases with >=1 request item: {(case_df['request_items_count'].fillna(0) > 0).sum()}")


if __name__ == "__main__":
    main()
