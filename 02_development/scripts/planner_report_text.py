#!/usr/bin/env python3
"""Extract text from downloaded planner-report PDFs and prep the extraction batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz
import pandas as pd

from structured_document_extraction import EXTRACTION_FIELDS, build_request, prepare_campaign

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS = ROOT / "02_development" / "source_data" / "planner_reports"


def extract_report_text(pdf_path: Path, text_dir: Path) -> str | None:
    """Extract a text layer from a planner-report PDF; None when no text exists."""
    try:
        document = fitz.open(pdf_path)
    except Exception:
        return None
    pages = [page.get_text() for page in document]
    document.close()
    text = "\n".join(pages).strip()
    if not text:
        return None
    text_dir.mkdir(parents=True, exist_ok=True)
    output = text_dir / (pdf_path.stem + ".txt")
    output.write_text(text, encoding="utf-8")
    return str(output)


def build_report_cohort(report_dir: Path, text_dir: Path) -> pd.DataFrame:
    rows = []
    for pdf_path in sorted(report_dir.glob("*.pdf")):
        text_path = extract_report_text(pdf_path, text_dir)
        if not text_path:
            continue
        rows.append({
            "case_key": pdf_path.stem.split("_planner_report")[0],
            "authority": report_dir.parent.name,
            "document_type": "planner_report",
            "text_path": text_path,
            "doc_chars": Path(text_path).stat().st_size,
        })
    frame = pd.DataFrame(rows).drop_duplicates("text_path").reset_index(drop=True)
    frame["row_number"] = frame.index
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--requests-per-part", type=int, default=300)
    args = parser.parse_args()

    text_dir = args.reports / "MeathCC" / "text"
    cohort = build_report_cohort(args.reports / "MeathCC", text_dir)
    cohort.to_csv(args.reports / "MeathCC" / "report_cohort.csv", index=False)
    parts, manifest = prepare_campaign(cohort, requests_per_part=args.requests_per_part)
    for index, part in enumerate(parts, start=1):
        (args.reports / "MeathCC" / f"report_batch_part{index:02d}.jsonl").write_text(
            "\n".join(json.dumps(request, ensure_ascii=True) for request in part) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "reports_with_text": int(len(cohort)),
        "request_parts": len(parts),
        "requests_total": sum(len(part) for part in parts),
    }, indent=2))


if __name__ == "__main__":
    main()
