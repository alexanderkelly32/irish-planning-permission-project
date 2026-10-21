#!/usr/bin/env python3
"""Phase 1: national Section 28 guidelines standards layer.

Scans 05_policy/documents/national_guidelines/ for the seven national
guideline PDFs, extracts their text (they are born-digital), and LLM-extracts
QUANTITATIVE standards (field, value, unit, context, clause reference) that a
scheme can be checked against.

Workflow:
  1. Drop the guideline PDFs into 05_policy/documents/national_guidelines/
     (or add source_url values to the manifest and run --download).
  2. python build_national_guidelines_layer.py prepare
  3. run_deepseek_extraction.py --out-dir ... --parts 1
  4. python build_national_guidelines_layer.py merge

Outputs: national_guideline_standards.csv + standards layer summary.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GUIDELINES_DIR = ROOT / "05_policy" / "documents" / "national_guidelines"
OUT_DIR = ROOT / "05_policy" / "current" / "national_guideline_standards_2026-09-20"

GUIDELINES = [
    {"name": "Sustainable Urban Housing: Design Standards for New Apartments", "years": "2020/2023", "source_url": ""},
    {"name": "Design Manual for Urban Roads and Streets (DMURS)", "years": "2013/2019", "source_url": ""},
    {"name": "Urban Development and Building Heights Guidelines", "years": "2018", "source_url": ""},
    {"name": "The Planning System and Flood Risk Management Guidelines", "years": "2009", "source_url": ""},
    {"name": "Quality Housing for Sustainable Communities", "years": "2007", "source_url": ""},
    {"name": "Sustainable Rural Housing Guidelines", "years": "2005", "source_url": ""},
    {"name": "Sustainable Residential Development in Urban Areas", "years": "2009", "source_url": ""},
]

SYSTEM_PROMPT = """You are extracting quantitative planning standards from an Irish national planning guideline document.

Rules:
- Extract only standards stated explicitly with a number and a unit (metres, square metres, percent, ratio, number of spaces, degrees, etc.).
- Fields: name the measurable thing (e.g. "minimum floor area for one-bed apartment", "rear garden depth", "car parking per unit", "minimum room width", "ceiling height").
- Include the clause/section reference if the text states one (e.g. "SPPR 3", "section 4.2").
- Silence is not evidence: if a chunk contains no quantitative standard, return an empty list.
- Return exactly one compact JSON object and nothing else:
  {"standards": [{"field": "...", "value": 24, "unit": "sqm", "context": "short quote", "clause": "SPPR 3"}]}
"""


def build_request(custom_id: str, user_prompt: str, model: str = "deepseek-v4-pro") -> dict:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "max_completion_tokens": 600,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def pdf_text(pdf_path: Path) -> str:
    import fitz

    doc = fitz.open(str(pdf_path))
    pages = []
    for page in doc:
        try:
            pages.append(page.get_text())
        except Exception:
            continue
    return "\n".join(pages)


def chunk_text(text: str, max_chars: int = 7000) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        start = end
    return chunks


def parse_guideline_links() -> list[dict]:
    """Extract the national-guidance table from the user's index file."""
    index = ROOT / "02_development" / "current" / "irish_planning_development_plan_index.md"
    if not index.exists():
        return []
    text = index.read_text(encoding="utf-8", errors="replace")
    section = text.split("## National planning guidance")[-1].split("## National cross-check")[0]
    rows = []
    for line in section.splitlines():
        if not line.startswith("| **"):
            continue
        match = re.search(r"\*\*([^*]+)\*\*.*?\[([^\]]+)\]\((https?://[^)]+)\)", line)
        if match:
            rows.append({"name": match.group(1).strip(), "source_url": match.group(3)})
    return rows


def download_guideline_pdfs() -> dict:
    import requests

    GUIDELINES_DIR.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    }
    results = []
    for entry in parse_guideline_links():
        name, page_url = entry["name"], entry["source_url"]
        record = {"name": name, "status": "", "pdf": ""}
        try:
            page = requests.get(page_url, headers=headers, timeout=60)
            pdf_links = re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', page.text, re.IGNORECASE)
            pdf_links = list(dict.fromkeys(pdf_links))
            if not pdf_links:
                record["status"] = "no_pdf_found"
                results.append(record)
                continue
            from urllib.parse import urljoin

            chosen = None
            for link in pdf_links:
                absolute = urljoin(page_url, link)
                try:
                    content = requests.get(absolute, headers=headers, timeout=180).content
                except Exception:
                    continue
                if len(content) > 300_000:
                    chosen = absolute
                    break
            if chosen is None:
                record["status"] = "pdfs_too_small_or_unreachable"
                results.append(record)
                continue
            target = GUIDELINES_DIR / (re.sub(r"[^a-zA-Z0-9]+", "_", name) + ".pdf")
            content = requests.get(chosen, headers=headers, timeout=300).content
            target.write_bytes(content)
            record["status"] = "ok"
            record["pdf"] = str(target)
        except Exception as exc:
            record["status"] = f"error: {str(exc)[:120]}"
        results.append(record)
    (OUT_DIR / "download_summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def prepare() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GUIDELINES_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(GUIDELINES_DIR.glob("*.pdf"))
    manifest = pd.DataFrame(GUIDELINES)
    manifest.to_csv(OUT_DIR / "guidelines_manifest.csv", index=False)
    rows = []
    requests = []
    row_number = 0
    for pdf in pdfs:
        text = pdf_text(pdf)
        for chunk_index, chunk in enumerate(chunk_text(text)):
            rows.append({"row_number": row_number, "source_file": pdf.name, "chunk_index": chunk_index})
            requests.append(build_request(
                f"guide-row-{row_number}",
                json.dumps({"document": pdf.name, "chunk_index": chunk_index, "text": chunk}, ensure_ascii=True),
            ))
            row_number += 1
    pd.DataFrame(rows).to_csv(OUT_DIR / "chunks.csv", index=False)
    (OUT_DIR / "batch_requests_part01.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=True) for r in requests) + "\n", encoding="utf-8")
    summary = {"pdfs_found": [p.name for p in pdfs], "chunks": row_number, "requests": len(requests)}
    (OUT_DIR / "prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def merge() -> None:
    chunks = pd.read_csv(OUT_DIR / "chunks.csv", low_memory=False)
    output_paths = sorted(OUT_DIR.glob("batch_output_part*.jsonl"))
    if not output_paths:
        raise FileNotFoundError("batch_output_part*.jsonl not found - run the DeepSeek runner first.")
    rows = []
    for path in output_paths:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            custom_id = item.get("custom_id", "")
            try:
                row_number = int(custom_id.rsplit("-", 1)[1]) if custom_id.startswith("guide-row-") else None
            except (ValueError, IndexError):
                row_number = None
            if item.get("error") or row_number is None:
                continue
            try:
                content = (item.get("response") or {}).get("body", {}).get("choices", [{}])[0].get("message", {}).get("content")
                payload = json.loads(content) if content else {}
                for standard in payload.get("standards") or []:
                    rows.append({**standard, "row_number": row_number})
            except Exception:
                continue
    standards = pd.DataFrame(rows)
    merged = standards.merge(chunks, on="row_number", how="left")
    merged = merged.drop(columns=["row_number", "chunk_index"])
    merged.to_csv(ROOT / "05_policy" / "current" / "national_guideline_standards.csv", index=False)
    summary = {
        "standards": int(len(merged)),
        "by_document": merged["source_file"].value_counts().to_dict() if not merged.empty else {},
    }
    (OUT_DIR / "merge_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["download", "prepare", "merge"])
    args = parser.parse_args()
    if args.action == "download":
        print(json.dumps(download_guideline_pdfs(), indent=2))
    elif args.action == "prepare":
        prepare()
    else:
        merge()
