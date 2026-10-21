#!/usr/bin/env python3
"""Ingest the downloaded council-plan corpus into the policy index.

Extracts text from the corpus PDFs/DOCX files, writes extracted_text entries,
and appends authority/period rows to policy_documents_index.csv so the
objective-code layer scan picks them up.

.doc files (one in the corpus) are skipped with a note - they need a converter.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = ROOT / "05_policy" / "current"
CORPUS = ROOT / "05_policy" / "documents" / "corpus" / "documents"
EXTRACTED = ROOT / "05_policy" / "documents" / "extracted_text" / "corpus"

AUTHORITY_NAMES = {
    "cavan": "Cavan County Council",
    "clare": "Clare County Council",
    "louth": "Louth County Council",
    "donegal": "Donegal County Council",
    "kerry": "Kerry County Council",
    "leitrim": "Leitrim County Council",
    "cork_city": "Cork City Council",
    "laois": "Laois County Council",
    "offaly": "Offaly County Council",
    "fingal": "Fingal County Council",
    "kilkenny": "Kilkenny County Council",
    "meath": "Meath County Council",
    "galway_county": "Galway County Council",
    "limerick": "Limerick City and County Council",
    "roscommon": "Roscommon County Council",
    "waterford": "Waterford City and County Council",
    "westmeath": "Westmeath County Council",
    "dun_laoghaire_rathdown": "Dun Laoghaire Rathdown County Council",
    "longford": "Longford County Council",
    "mayo": "Mayo County Council",
    "monaghan": "Monaghan County Council",
    "wexford": "Wexford County Council",
    "carlow": "Carlow County Council",
    "cork_county": "Cork County Council",
    "dublin_city": "Dublin City Council",
    "galway_city": "Galway City Council",
    "kildare": "Kildare County Council",
    "south_dublin": "South Dublin County Council",
    "tipperary": "Tipperary County Council",
    "wicklow": "Wicklow County Council",
    "sligo": "Sligo County Council",
}

PERIOD_PATTERN = re.compile(r"(20\d{2})\s*[-–]\s*(20\d{2})")


def parse_period(text: str | None):
    if not text:
        return None, None
    match = PERIOD_PATTERN.search(str(text))
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def pdf_text(path: Path) -> str:
    import fitz

    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        try:
            pages.append(page.get_text())
        except Exception:
            continue
    return "\n".join(pages)


def docx_text(path: Path) -> str:
    import zipfile
    from xml.etree import ElementTree

    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = [node.text or "" for node in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")]
    return "\n".join(paragraphs)

def main() -> None:
    index_path = POLICY_DIR / "policy_documents_index.csv"
    index = pd.read_csv(index_path, low_memory=False)
    inventory = None
    inventory_path = POLICY_DIR / "policy_details" / "verified_document_inventory.csv"
    if inventory_path.exists():
        inventory = pd.read_csv(inventory_path, low_memory=False)
    rows = []
    log = []
    for authority_slug, authority in AUTHORITY_NAMES.items():
        council_dir = CORPUS / authority_slug
        if not council_dir.exists():
            continue
        for file in sorted(council_dir.iterdir()):
            if file.suffix.lower() == ".doc":
                log.append({"file": str(file), "status": "skipped_doc_needs_converter"})
                continue
            name = file.stem.split("__", 1)[-1]
            start, end = parse_period(name)
            source_url = ""
            if (start is None or end is None) and inventory is not None:
                local = f"documents/{authority_slug}/{file.name}"
                hit = inventory[inventory["local_path"] == local]
                if len(hit):
                    row = hit.iloc[0]
                    for field in ("source_seed", "source_page", "link_text"):
                        start, end = parse_period(row.get(field))
                        if start is not None and end is not None:
                            break
                    source_url = str(row.get("url") or row.get("final_url") or "")
            label = f"{authority} - {name}"
            text = None
            if file.suffix.lower() == ".pdf":
                try:
                    text = pdf_text(file)
                except Exception as exc:
                    log.append({"file": str(file), "status": f"pdf_error: {str(exc)[:80]}"})
            elif file.suffix.lower() == ".docx":
                try:
                    text = docx_text(file)
                except Exception as exc:
                    log.append({"file": str(file), "status": f"docx_error: {str(exc)[:80]}"})
            if not text:
                log.append({"file": str(file), "status": "empty_text"})
                continue
            text_path = EXTRACTED / authority_slug / (file.stem + ".txt")
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(text, encoding="utf-8", errors="ignore")
            start_key = start if start is not None else "noyr"
            end_key = end if end is not None else "noyr"
            rows.append({
                "doc_id": f"{authority_slug}__{start_key}_{end_key}__{file.stem[:60]}",
                "authority": authority,
                "document_label": label,
                "document_type": "corpus_document",
                "coverage_start_year": start,
                "coverage_end_year": end,
                "source_url": source_url,
                "relative_file": str(file.relative_to(ROOT / "05_policy" / "documents" / "corpus")),
                "extracted_text_path": str(text_path.relative_to(ROOT / "05_policy")),
                "extraction_status": "ok",
                "extraction_error": "",
                "page_count": None,
                "total_chars": len(text),
                "nonempty_pages": None,
                "low_text_ratio": None,
                "note": "corpus ingestion 2026-09-21",
            })

    if "document_type" in index.columns:
        index = index[index["document_type"] != "corpus_document"]
    new_rows = pd.DataFrame(rows)
    combined = pd.concat([index, new_rows], ignore_index=True).drop_duplicates("doc_id", keep="last")
    combined.to_csv(index_path, index=False)
    summary = {
        "ingested": int(len(new_rows)),
        "index_total": int(len(combined)),
        "skipped_or_errors": log,
    }
    (POLICY_DIR / "corpus_ingestion_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"ingested": int(len(new_rows)), "index_total": int(len(combined))}, indent=2))


if __name__ == "__main__":
    main()
