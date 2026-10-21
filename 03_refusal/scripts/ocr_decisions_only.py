#!/usr/bin/env python3
"""
Run OCR only (no reason extraction/mining) on planning decision PDFs.

Defaults:
- Input PDFs:    ./downloads/rejected_decisions
- OCR text out:  ./downloads/ocr_text
- OCR index CSV: ./downloads/ocr_text_index.csv

By default, files with names starting `Kerry_County_Council_` are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from time import perf_counter

import fitz
import pandas as pd
from rapidocr_onnxruntime import RapidOCR


def sha1_path(path: Path) -> str:
    h = hashlib.sha1()
    h.update(str(path).encode("utf-8", errors="ignore"))
    return h.hexdigest()[:16]


def ocr_pdf(path: Path, engine: RapidOCR, page_limit: int, dpi: int) -> tuple[str, int]:
    doc = fitz.open(str(path))
    max_pages = min(len(doc), max(1, page_limit))
    zoom = max(1.2, dpi / 96.0)
    mat = fitz.Matrix(zoom, zoom)
    lines: list[str] = []
    for page_idx in range(max_pages):
        try:
            pix = doc[page_idx].get_pixmap(matrix=mat, alpha=False)
            result, _ = engine(pix.tobytes("png"))
            if result:
                lines.extend(x[1] for x in result if len(x) > 1 and str(x[1]).strip())
        except Exception:
            continue
    return ("\n".join(lines)).strip(), max_pages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="downloads/rejected_decisions")
    parser.add_argument("--output-dir", default="downloads/ocr_text")
    parser.add_argument("--index-csv", default="downloads/ocr_text_index.csv")
    parser.add_argument("--exclude-prefix", default="Kerry_County_Council_")
    parser.add_argument("--page-limit", type=int, default=12)
    parser.add_argument("--dpi", type=int, default=140)
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    idx_csv = Path(args.index_csv)
    out_dir.mkdir(parents=True, exist_ok=True)
    idx_csv.parent.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(in_dir.glob("*.pdf"))
    if args.exclude_prefix:
        pdfs = [p for p in pdfs if not p.name.startswith(args.exclude_prefix)]

    existing = set()
    if idx_csv.exists() and not args.overwrite:
        try:
            old = pd.read_csv(idx_csv, low_memory=False)
            existing = set(old.loc[old["status"] == "ok", "file_name"].astype(str).tolist())
        except Exception:
            existing = set()

    engine = RapidOCR()
    rows: list[dict] = []
    total = len(pdfs)
    done = 0
    skipped = 0

    for i, pdf in enumerate(pdfs, start=1):
        out_name = pdf.stem + "_ocr.txt"
        out_path = out_dir / out_name
        if (not args.overwrite) and pdf.name in existing and out_path.exists():
            skipped += 1
            continue

        start = perf_counter()
        text = ""
        pages_used = 0
        status = "ok"
        err = ""
        try:
            text, pages_used = ocr_pdf(pdf, engine, page_limit=args.page_limit, dpi=args.dpi)
            out_path.write_text(text, encoding="utf-8", errors="ignore")
        except Exception as exc:
            status = "error"
            err = str(exc)[:400]

        rows.append(
            {
                "file_name": pdf.name,
                "source_path": str(pdf),
                "output_path": str(out_path),
                "status": status,
                "error": err,
                "chars": len(text),
                "pages_used": pages_used,
                "page_limit": args.page_limit,
                "dpi": args.dpi,
                "elapsed_sec": round(perf_counter() - start, 2),
                "file_key": sha1_path(pdf),
            }
        )
        done += 1
        if args.progress_every > 0 and done % args.progress_every == 0:
            print(f"Progress: {done}/{total} OCRed (skipped existing: {skipped})")

    new_df = pd.DataFrame(rows)
    if idx_csv.exists() and not args.overwrite:
        try:
            old = pd.read_csv(idx_csv, low_memory=False)
            old = old[~old["file_name"].astype(str).isin(new_df["file_name"].astype(str))]
            out_df = pd.concat([old, new_df], ignore_index=True)
        except Exception:
            out_df = new_df
    else:
        out_df = new_df
    out_df.to_csv(idx_csv, index=False, encoding="utf-8")

    ok = int((out_df["status"] == "ok").sum()) if len(out_df) else 0
    print(f"Done. Total indexed: {len(out_df)} | OK: {ok} | Newly OCRed: {done} | Skipped: {skipped}")
    print(f"OCR text folder: {out_dir}")
    print(f"Index CSV: {idx_csv}")


if __name__ == "__main__":
    main()
