#!/usr/bin/env python3
"""Run RapidOCR over downloaded planner-report PDFs (scans with watermark text only).

Supports --workers for parallel OCR across PDFs (each worker gets its own engine);
the resume index stays append-safe (workers return rows, the parent writes).
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter

import fitz
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "03_refusal" / "scripts"))
from ocr_decisions_only import sha1_path  # noqa: E402

DEFAULT_INPUT = ROOT / "02_development" / "source_data" / "planner_reports" / "MeathCC"

_WORKER_ENGINE = None


def _worker_init():
    global _WORKER_ENGINE
    from rapidocr_onnxruntime import RapidOCR

    _WORKER_ENGINE = RapidOCR()


def ocr_pdf(path: Path, engine, page_limit: int, dpi: int) -> tuple[str, int]:
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


def _ocr_one(pdf: Path, out_dir: Path, page_limit: int, dpi: int) -> dict:
    out_path = out_dir / (pdf.stem + "_ocr.txt")
    start = perf_counter()
    text, pages_used = "", 0
    status, err = "ok", ""
    try:
        text, pages_used = ocr_pdf(pdf, _WORKER_ENGINE, page_limit=page_limit, dpi=dpi)
        out_path.write_text(text, encoding="utf-8", errors="ignore")
    except Exception as exc:
        status, err = "error", str(exc)[:400]
    return {
        "file_name": pdf.name,
        "source_path": str(pdf),
        "output_path": str(out_path),
        "status": status,
        "error": err,
        "chars": len(text),
        "pages_used": pages_used,
        "page_limit": page_limit,
        "dpi": dpi,
        "elapsed_sec": round(perf_counter() - start, 2),
        "file_key": sha1_path(pdf),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--page-limit", type=int, default=45)
    parser.add_argument("--dpi", type=int, default=140)
    parser.add_argument("--progress-every", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--workers", type=int, default=3, help="parallel OCR workers (each runs its own engine; ~1GB RAM each)")
    args = parser.parse_args()

    out_dir = args.input_dir / "ocr_text"
    out_dir.mkdir(parents=True, exist_ok=True)
    index_csv = args.input_dir / "ocr_index.csv"
    pdfs = sorted(args.input_dir.glob("*.pdf"))
    existing = set()
    if index_csv.exists() and not args.overwrite:
        try:
            old = pd.read_csv(index_csv, low_memory=False)
            existing = set(old.loc[old["status"] == "ok", "file_name"].astype(str).tolist())
        except Exception:
            existing = set()

    pending = [
        pdf for pdf in pdfs
        if args.overwrite or not (
            pdf.name in existing
            or ((out_dir / (pdf.stem + "_ocr.txt")).exists() and (out_dir / (pdf.stem + "_ocr.txt")).stat().st_size > 0)
        )
    ]
    print(f"Pending OCR: {len(pending)} of {len(pdfs)}", flush=True)

    if not pending:
        print("Done. OCRed: 0 | OK: 0")
        return

    workers = max(1, min(args.workers, len(pending)))
    rows = []
    done = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as executor:
        futures = {
            executor.submit(_ocr_one, pdf, out_dir, args.page_limit, args.dpi): pdf
            for pdf in pending
        }
        for future in as_completed(futures):
            try:
                row = future.result()
            except Exception as exc:
                pdf = futures[future]
                row = {
                    "file_name": pdf.name, "source_path": str(pdf),
                    "output_path": str(out_dir / (pdf.stem + "_ocr.txt")),
                    "status": "error", "error": str(exc)[:400], "chars": 0,
                    "pages_used": 0, "page_limit": args.page_limit, "dpi": args.dpi,
                    "elapsed_sec": 0.0, "file_key": sha1_path(pdf),
                }
            rows.append(row)
            done += 1
            if done % args.progress_every == 0:
                print(f"Progress: {done}/{len(pending)} OCRed", flush=True)
            _append_index_row(index_csv, row)

    ok = int(len([row for row in rows if row["status"] == "ok"]))
    print(f"Done. OCRed: {done} | OK: {ok}")


def _append_index_row(index_csv: Path, row: dict) -> None:
    new_row = pd.DataFrame([row])
    if index_csv.exists():
        try:
            old = pd.read_csv(index_csv, low_memory=False)
            old = old[~old["file_name"].astype(str).isin(new_row["file_name"].astype(str))]
            pd.concat([old, new_row], ignore_index=True).to_csv(index_csv, index=False, encoding="utf-8")
        except Exception:
            new_row.to_csv(index_csv, index=False, encoding="utf-8")
    else:
        new_row.to_csv(index_csv, index=False, encoding="utf-8")


if __name__ == "__main__":
    main()
