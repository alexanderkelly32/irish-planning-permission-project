#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd
from pypdf import PdfReader

try:
    import fitz  # PyMuPDF
    from rapidocr_onnxruntime import RapidOCR

    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

_OCR_ENGINE = None


SYSTEM_PROMPT = (
    "Extract refusal reasons from Irish planning decision text. "
    "Return strict JSON only with keys: found, reasons, notes. "
    "found: 1 if refusal reasons are present, else 0. "
    "reasons: array of objects with keys t and cats. "
    "t is concise reason text. "
    "cats is array using only: "
    "traffic_access,flooding_drainage,water_wastewater,design_layout,density_scale,"
    "residential_amenity,land_use_policy,heritage_archaeology,ecology_trees,premature_or_info_gap,other. "
    "notes: short string or null."
)


def safe_filename(value: str) -> str:
    value = str(value or "").strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:180]


def read_pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path), strict=False)
    except Exception:
        return ""
    chunks = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunks)


def read_text_file(path: Path) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc, errors="ignore")
        except Exception:
            continue
    return ""


def read_pdf_ocr_text(path: Path, page_limit: int, dpi: int) -> str:
    if not OCR_AVAILABLE:
        return ""
    global _OCR_ENGINE
    try:
        if _OCR_ENGINE is None:
            _OCR_ENGINE = RapidOCR()
        doc = fitz.open(str(path))
        max_pages = min(len(doc), max(1, page_limit))
        zoom = max(1.2, dpi / 96.0)
        matrix = fitz.Matrix(zoom, zoom)
        out = []
        for i in range(max_pages):
            try:
                pix = doc[i].get_pixmap(matrix=matrix, alpha=False)
                img_bytes = pix.tobytes("png")
                result, _ = _OCR_ENGINE(img_bytes)
                if result:
                    out.extend(r[1] for r in result if len(r) > 1 and str(r[1]).strip())
            except Exception:
                continue
        return "\n".join(out)
    except Exception:
        return ""


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def select_text_window(text: str, max_chars: int) -> str:
    text = normalize_text(text)
    if max_chars <= 0:
        return text
    if len(text) <= max_chars:
        return text
    patterns = [
        r"reasons?\s+for\s+refusal",
        r"grounds?\s+for\s+refusal",
        r"refuse(?:s|d)?\s+permission",
        r"planning\s+authority\s+refuses",
    ]
    lower = text.lower()
    spans = []
    for pat in patterns:
        for m in re.finditer(pat, lower, flags=re.IGNORECASE):
            st = max(0, m.start() - 2500)
            en = min(len(text), m.end() + 9000)
            spans.append((st, en))
    if spans:
        spans.sort()
        merged = []
        for st, en in spans:
            if not merged or st > merged[-1][1]:
                merged.append((st, en))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], en))
        join = "\n\n".join(text[a:b] for a, b in merged)
        return join[:max_chars]
    head = text[: int(max_chars * 0.7)]
    tail = text[-int(max_chars * 0.3) :]
    return (head + "\n\n[...TRIMMED...]\n\n" + tail)[:max_chars]


def read_case_text(
    row: pd.Series,
    ocr_dir: Path,
    rejected_dir: Path,
    max_chars: int,
    prefer_source_file: bool,
    use_pdf_ocr: bool,
    pdf_ocr_min_chars: int,
    ocr_page_limit: int,
    ocr_dpi: int,
) -> tuple[str, str]:
    council = str(row.get("council", ""))
    app = str(row.get("application_number", ""))
    stem = f"{safe_filename(council)}_{safe_filename(app)}"

    # Build preferred source order.
    src = str(row.get("source_file", "")).strip()
    pdf_candidates = []
    txt_candidates = []
    if src:
        p = Path(src)
        if not p.exists():
            p2 = rejected_dir / p.name
            if p2.exists():
                p = p2
        if p.exists():
            if p.suffix.lower() == ".pdf":
                pdf_candidates.append(p)
            elif p.suffix.lower() == ".txt":
                txt_candidates.append(p)

    fallback_pdf = rejected_dir / f"{stem}_Decision.pdf"
    if fallback_pdf.exists() and fallback_pdf not in pdf_candidates:
        pdf_candidates.append(fallback_pdf)
    fallback_txts = [
        rejected_dir / f"{stem}_Decision_Reasons.txt",
        rejected_dir / f"{stem}_Decision_Summary.txt",
        rejected_dir / f"{stem}_Decision.txt",
    ]
    for p in fallback_txts:
        if p.exists() and p not in txt_candidates:
            txt_candidates.append(p)

    ocr_path = ocr_dir / f"{stem}_Decision_ocr.txt"

    source_order = ["pdf", "ocr"] if prefer_source_file else ["ocr", "pdf"]
    for source_kind in source_order:
        if source_kind == "pdf":
            for p in txt_candidates:
                txt = read_text_file(p)
                if txt.strip():
                    return select_text_window(txt, max_chars), "text_file"
        if source_kind == "ocr" and ocr_path.exists():
            txt = ocr_path.read_text(encoding="utf-8", errors="ignore")
            if txt.strip():
                return select_text_window(txt, max_chars), "ocr_text"
        if source_kind == "pdf":
            for p in pdf_candidates:
                txt = read_pdf_text(p)
                if len(normalize_text(txt)) >= pdf_ocr_min_chars:
                    return select_text_window(txt, max_chars), "pdf_text"
                if use_pdf_ocr:
                    ocr_txt = read_pdf_ocr_text(p, page_limit=ocr_page_limit, dpi=ocr_dpi)
                    if ocr_txt.strip():
                        return select_text_window(ocr_txt, max_chars), "pdf_ocr"
                if txt.strip():
                    return select_text_window(txt, max_chars), "pdf_text"

    return "", "none"


def build_body(text: str, max_output_tokens: int, model: str) -> dict:
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": text}]},
        ],
        "max_output_tokens": max_output_tokens,
        "text": {"format": {"type": "json_object"}},
    }
    if model.startswith("gpt-5"):
        body["reasoning"] = {"effort": "minimal"}
    else:
        body["temperature"] = 0
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-csv", default="extraction_of_site_data/refusal_reasons_cases_final.csv")
    parser.add_argument("--ocr-dir", default="extraction_of_site_data/ocr_text")
    parser.add_argument("--rejected-dir", default="extraction_of_site_data/rejected_decisions")
    parser.add_argument("--output-jsonl", default="extraction_of_site_data/_llm_batch/llm_refusal_batch_input.jsonl")
    parser.add_argument("--meta-csv", default="extraction_of_site_data/_llm_batch/llm_refusal_batch_meta.csv")
    parser.add_argument("--max-output-tokens", type=int, default=220)
    parser.add_argument("--max-chars", type=int, default=12000)
    parser.add_argument("--include-only-failed", action="store_true")
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--start-row", type=int, default=0)
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--prefer-source-file", action="store_true")
    parser.add_argument("--use-pdf-ocr", action="store_true")
    parser.add_argument("--pdf-ocr-min-chars", type=int, default=1200)
    parser.add_argument("--ocr-page-limit", type=int, default=8)
    parser.add_argument("--ocr-dpi", type=int, default=220)
    args = parser.parse_args()

    df = pd.read_csv(args.cases_csv)
    if args.include_only_failed:
        rc = pd.to_numeric(df.get("reason_count", 0), errors="coerce").fillna(0)
        df = df[rc <= 0]
    if args.start_row and args.start_row > 0:
        df = df.iloc[args.start_row :].copy()
    if args.max_rows and args.max_rows > 0:
        df = df.head(args.max_rows)

    out_jsonl = Path(args.output_jsonl)
    out_meta = Path(args.meta_csv)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    ocr_dir = Path(args.ocr_dir)
    rejected_dir = Path(args.rejected_dir)

    with out_jsonl.open("w", encoding="utf-8") as fj, out_meta.open("w", newline="", encoding="utf-8") as fm:
        meta_writer = csv.DictWriter(
            fm,
            fieldnames=["case_key", "council", "application_number", "text_source", "text_chars", "custom_id"],
        )
        meta_writer.writeheader()

        for _, row in df.iterrows():
            case_key = str(row.get("case_key", "")).strip().lower()
            if not case_key:
                continue
            text, text_source = read_case_text(
                row,
                ocr_dir=ocr_dir,
                rejected_dir=rejected_dir,
                max_chars=args.max_chars,
                prefer_source_file=args.prefer_source_file,
                use_pdf_ocr=args.use_pdf_ocr,
                pdf_ocr_min_chars=args.pdf_ocr_min_chars,
                ocr_page_limit=args.ocr_page_limit,
                ocr_dpi=args.ocr_dpi,
            )
            if not text:
                continue
            custom_id = case_key

            req = {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/v1/responses",
                "body": build_body(text, args.max_output_tokens, args.model),
            }
            fj.write(json.dumps(req, ensure_ascii=True) + "\n")
            meta_writer.writerow(
                {
                    "case_key": case_key,
                    "council": str(row.get("council", "")),
                    "application_number": str(row.get("application_number", "")),
                    "text_source": text_source,
                    "text_chars": len(text),
                    "custom_id": custom_id,
                }
            )

    print(f"Wrote: {out_jsonl}")
    print(f"Wrote: {out_meta}")
    print(f"Rows prepared: {len(df)}")


if __name__ == "__main__":
    main()
