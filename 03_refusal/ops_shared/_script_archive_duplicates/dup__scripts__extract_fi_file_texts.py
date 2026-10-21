#!/usr/bin/env python3
"""
Extract text from downloaded FI files:
- direct extraction when possible (PDF/DOCX/TXT)
- OCR fallback for image-like files and low-text PDFs

Outputs:
- fi_file_text_index.csv (one row per FI file with extraction stats)
- fi_case_text_summary.csv (one row per case)
- fi_file_text/ (per-file extracted text files)
- fi_case_text/ (per-case concatenated text files)
"""
from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path
from typing import Dict, List
from xml.etree import ElementTree as ET

import fitz
import pandas as pd
from pypdf import PdfReader
from rapidocr_onnxruntime import RapidOCR


DEFAULT_INPUT = Path("extraction_of_site_data/fi_documents_long_downloaded.csv")
DEFAULT_FILE_INDEX = Path("extraction_of_site_data/fi_file_text_index.csv")
DEFAULT_CASE_SUMMARY = Path("extraction_of_site_data/fi_case_text_summary.csv")
DEFAULT_FILE_TEXT_DIR = Path("extraction_of_site_data/fi_file_text")
DEFAULT_CASE_TEXT_DIR = Path("extraction_of_site_data/fi_case_text")


def clean_text(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"nan", "nat", "none"} else s


def safe_filename(s: str) -> str:
    s = clean_text(s).replace(" ", "_").replace("/", "_").replace("\\", "_")
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return s[:180] if len(s) > 180 else s


def path_key(path: Path) -> str:
    h = hashlib.sha1()
    h.update(str(path).encode("utf-8", errors="ignore"))
    return h.hexdigest()[:16]


def read_pdf_text(path: Path, page_limit: int) -> str:
    text: List[str] = []
    reader = PdfReader(str(path))
    pages = min(len(reader.pages), max(1, page_limit))
    for i in range(pages):
        try:
            t = reader.pages[i].extract_text() or ""
            if t.strip():
                text.append(t)
        except Exception:
            continue
    return "\n".join(text).strip()


def read_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            return ""
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    parts = [el.text for el in root.iter() if el.text]
    return " ".join(parts).strip()


def ocr_with_fitz(path: Path, engine: RapidOCR, page_limit: int, dpi: int) -> tuple[str, int]:
    doc = fitz.open(str(path))
    pages = min(len(doc), max(1, page_limit))
    zoom = max(1.2, dpi / 96.0)
    mat = fitz.Matrix(zoom, zoom)
    lines: List[str] = []
    for i in range(pages):
        try:
            pix = doc[i].get_pixmap(matrix=mat, alpha=False)
            result, _ = engine(pix.tobytes("png"))
            if result:
                for item in result:
                    if len(item) > 1 and str(item[1]).strip():
                        lines.append(str(item[1]).strip())
        except Exception:
            continue
    return "\n".join(lines).strip(), pages


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract FI file text (direct + OCR fallback).")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--file-index", default=str(DEFAULT_FILE_INDEX))
    parser.add_argument("--case-summary", default=str(DEFAULT_CASE_SUMMARY))
    parser.add_argument("--file-text-dir", default=str(DEFAULT_FILE_TEXT_DIR))
    parser.add_argument("--case-text-dir", default=str(DEFAULT_CASE_TEXT_DIR))
    parser.add_argument("--pdf-page-limit", type=int, default=20)
    parser.add_argument("--ocr-page-limit", type=int, default=20)
    parser.add_argument("--ocr-dpi", type=int, default=180)
    parser.add_argument("--pdf-direct-min-chars", type=int, default=120)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    file_index_path = Path(args.file_index)
    case_summary_path = Path(args.case_summary)
    file_text_dir = Path(args.file_text_dir)
    case_text_dir = Path(args.case_text_dir)
    file_text_dir.mkdir(parents=True, exist_ok=True)
    case_text_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, low_memory=False, dtype={"ApplicationNumber": str})
    df = df[(df["is_fi_doc"] == True) & (df["download_status"].fillna("") == "saved")].copy()
    df["download_path"] = df["download_path"].fillna("").astype(str)
    df = df[df["download_path"].str.strip() != ""].copy()
    df = df.drop_duplicates(subset=["download_path"]).copy()

    done_paths = set()
    if file_index_path.exists() and not args.overwrite:
        try:
            old = pd.read_csv(file_index_path, low_memory=False)
            done_paths = set(old["download_path"].astype(str).tolist())
        except Exception:
            done_paths = set()

    engine = RapidOCR()
    rows: List[Dict[str, object]] = []
    total = len(df)
    processed = 0

    for _, row in df.iterrows():
        src = Path(clean_text(row.get("download_path")))
        if (not args.overwrite) and str(src) in done_paths:
            continue

        ext = src.suffix.lower()
        case_key = clean_text(row.get("case_key"))
        authority = clean_text(row.get("PlanningAuthority"))
        app = clean_text(row.get("ApplicationNumber"))
        method = ""
        text = ""
        pages_used = 0
        status = "ok"
        err = ""

        try:
            if not src.exists():
                status = "missing"
            elif ext == ".pdf":
                direct = read_pdf_text(src, page_limit=args.pdf_page_limit)
                if len(direct) >= args.pdf_direct_min_chars:
                    text = direct
                    method = "pdf_text_layer"
                    pages_used = min(args.pdf_page_limit, len(PdfReader(str(src)).pages))
                else:
                    text, pages_used = ocr_with_fitz(src, engine=engine, page_limit=args.ocr_page_limit, dpi=args.ocr_dpi)
                    method = "pdf_ocr"
            elif ext in {".djvu", ".tif", ".tiff", ".jpg", ".jpeg", ".png"}:
                text, pages_used = ocr_with_fitz(src, engine=engine, page_limit=args.ocr_page_limit, dpi=args.ocr_dpi)
                method = "image_ocr"
            elif ext == ".docx":
                text = read_docx_text(src)
                method = "docx_xml"
            elif ext in {".txt", ".csv", ".json", ".xml"}:
                text = src.read_text(encoding="utf-8", errors="ignore")
                method = "plain_text"
            else:
                # fallback: try PDF magic via fitz
                try:
                    _ = fitz.open(str(src))
                    text, pages_used = ocr_with_fitz(src, engine=engine, page_limit=args.ocr_page_limit, dpi=args.ocr_dpi)
                    method = "fitz_ocr_fallback"
                except Exception:
                    status = "unsupported"
                    method = "none"
        except Exception as exc:
            status = "error"
            err = f"{type(exc).__name__}: {str(exc)[:300]}"

        text = clean_text(text)
        text_file = ""
        if status == "ok" and text:
            stem = f"{safe_filename(authority)}_{safe_filename(app)}_{path_key(src)}.txt"
            out = file_text_dir / stem
            out.write_text(text, encoding="utf-8", errors="ignore")
            text_file = str(out)

        rows.append(
            {
                "case_key": case_key,
                "PlanningAuthority": authority,
                "ApplicationNumber": app,
                "download_path": str(src),
                "file_ext": ext,
                "status": status,
                "error": err,
                "method": method,
                "pages_used": pages_used,
                "text_chars": len(text),
                "text_path": text_file,
                "doc_type": clean_text(row.get("doc_type")),
                "doc_comment": clean_text(row.get("doc_comment")),
                "doc_name": clean_text(row.get("doc_name")),
                "portal_type": clean_text(row.get("portal_type")),
            }
        )

        processed += 1
        if args.progress_every > 0 and processed % args.progress_every == 0:
            print(f"Progress: {processed}/{total}", flush=True)

    new_df = pd.DataFrame(rows)
    if file_index_path.exists() and not args.overwrite:
        try:
            old = pd.read_csv(file_index_path, low_memory=False)
            keep = old[~old["download_path"].astype(str).isin(new_df["download_path"].astype(str))]
            out_df = pd.concat([keep, new_df], ignore_index=True)
        except Exception:
            out_df = new_df
    else:
        out_df = new_df
    ensure_parent(file_index_path)
    out_df.to_csv(file_index_path, index=False)

    # Build case-level text corpus.
    case_rows: List[Dict[str, object]] = []
    ok_with_text = out_df[(out_df["status"] == "ok") & (out_df["text_chars"].fillna(0) > 0)].copy()
    for case_key, group in ok_with_text.groupby("case_key", dropna=False):
        g = group.sort_values(["ApplicationNumber", "download_path"], ascending=True)
        authority = clean_text(g["PlanningAuthority"].iloc[0]) if len(g) else ""
        app = clean_text(g["ApplicationNumber"].iloc[0]) if len(g) else ""
        texts: List[str] = []
        files: List[str] = []
        for _, r in g.iterrows():
            tp = Path(clean_text(r.get("text_path")))
            if tp.exists():
                t = tp.read_text(encoding="utf-8", errors="ignore").strip()
                if t:
                    header = f"[FILE] {Path(clean_text(r.get('download_path'))).name}\n[TYPE] {clean_text(r.get('doc_type'))}\n"
                    texts.append(header + t)
                    files.append(clean_text(r.get("download_path")))
        combined = "\n\n" + ("\n\n" + ("-" * 80) + "\n\n").join(texts) if texts else ""
        combined = combined.strip()
        case_text_path = ""
        if combined:
            fn = f"{safe_filename(authority)}_{safe_filename(app)}_{safe_filename(str(case_key))}_fi_text.txt"
            out_case = case_text_dir / fn
            out_case.write_text(combined, encoding="utf-8", errors="ignore")
            case_text_path = str(out_case)
        case_rows.append(
            {
                "case_key": case_key,
                "PlanningAuthority": authority,
                "ApplicationNumber": app,
                "fi_files_with_text": len(texts),
                "fi_text_chars_total": len(combined),
                "fi_case_text_path": case_text_path,
                "source_files_joined": " || ".join(files),
            }
        )

    case_df = pd.DataFrame(case_rows)
    ensure_parent(case_summary_path)
    case_df.to_csv(case_summary_path, index=False)

    ok_count = int((out_df["status"] == "ok").sum()) if len(out_df) else 0
    with_text_count = int((out_df["text_chars"].fillna(0) > 0).sum()) if len(out_df) else 0
    print(f"Done. Indexed files: {len(out_df)} | status=ok: {ok_count} | with text: {with_text_count}")
    print(f"File index: {file_index_path}")
    print(f"Case summary: {case_summary_path}")
    print(f"File text dir: {file_text_dir}")
    print(f"Case text dir: {case_text_dir}")


if __name__ == "__main__":
    main()
