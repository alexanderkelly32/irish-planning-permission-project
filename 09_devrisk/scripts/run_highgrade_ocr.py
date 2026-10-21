"""Runner: higher-grade OCR pass over thin refusal-decision documents.

The original pipeline OCR'd at 140 DPI (median text 1.6k chars on the
zero-reason rows). This pass re-renders at 300 DPI with grayscale + 2x
upscale preprocessing, re-runs RapidOCR, and reports the text-length
improvement. Outputs feed a follow-up DeepSeek extraction sample.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

PDF_DIRS = [
    settings.ROOT / "03_refusal" / "documents" / "downloaded",
    settings.ROOT / "03_refusal" / "source_data" / "_archive_intermediate" / "rejected_decisions_ocr_subset",
    settings.ROOT / "03_refusal" / "source_data" / "_archive_intermediate" / "rejected_decisions_missing_text_subset",
]

OUT_DIR = settings.SILVER_DIR / "refusal_highgrade_ocr"
STATE_PATH = OUT_DIR / "state.json"


def weak_rows() -> pd.DataFrame:
    """Untagged refused rows whose texts are thin OR whose 'reasons' are likely
    OCR noise (both buckets benefit from a higher-grade OCR pass)."""
    master = pd.read_csv(settings.ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv", low_memory=False)
    refused = master[master["decision"].fillna("").astype(str).str.contains("^REFUSE", regex=True)].copy()
    refused["reason_count"] = pd.to_numeric(refused["reason_count"], errors="coerce")
    refused["raw_text_len"] = pd.to_numeric(refused["raw_text_len"], errors="coerce")
    thin = refused[(refused["case_top_primary_tag"].isna()) & ((refused["reason_count"] == 0) | (refused["raw_text_len"] < 4000))].copy()
    return thin


def locate_pdf(file_name: str) -> Path | None:
    for folder in PDF_DIRS:
        candidate = folder / file_name
        if candidate.exists():
            return candidate
    return None


def ocr_pdf_highgrade(path: Path, engine, page_limit: int = 12) -> tuple[str, int]:
    import fitz

    document = fitz.open(str(path))
    max_pages = min(len(document), max(1, page_limit))
    zoom = 300 / 96.0  # 300 DPI
    matrix = fitz.Matrix(zoom, zoom)
    lines: list[str] = []
    for page_idx in range(max_pages):
        try:
            pix = document[page_idx].get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csGRAY)
            result, _ = engine(pix.tobytes("png"))
            if result:
                lines.extend(str(item[1]).strip() for item in result if len(item) > 1 and str(item[1]).strip())
        except Exception:  # noqa: BLE001
            continue
    document.close()
    return "\n".join(lines).strip(), max_pages


if __name__ == "__main__":
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = {"done": {}, "errors": {}}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    rows = weak_rows()
    print(f"thin docs to re-OCR: {len(rows)}", flush=True)
    results = []
    processed = 0
    for _, row in rows.iterrows():
        file_name = str(row.get("available_files") or "")
        key = f"{row['council']}_{row['application_number']}"
        if not file_name or not file_name.endswith(".pdf") or key in state["done"]:
            continue
        pdf_path = locate_pdf(file_name)
        if pdf_path is None:
            state["errors"][key] = "pdf not located"
            continue
        try:
            text, pages = ocr_pdf_highgrade(pdf_path, engine)
            out_path = OUT_DIR / f"{key}_highgrade.txt"
            out_path.write_text(text, encoding="utf-8", errors="ignore")
            state["done"][key] = {"chars": len(text), "pages": pages, "old_chars": int(row["raw_text_len"] or 0)}
            results.append({"key": key, "new_chars": len(text), "old_chars": int(row["raw_text_len"] or 0)})
        except Exception as error:  # noqa: BLE001
            state["errors"][key] = f"{type(error).__name__}: {str(error)[:150]}"
        processed += 1
        if processed % 10 == 0:
            STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
            print(f"processed {processed}", flush=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    if results:
        frame = pd.DataFrame(results)
        improved = int((frame["new_chars"] > frame["old_chars"] * 1.5).sum())
        doubled = int((frame["new_chars"] > frame["old_chars"] * 2).sum())
        summary = {
            "docs_re_ocred": int(len(frame)),
            "median_old_chars": int(frame["old_chars"].median()),
            "median_new_chars": int(frame["new_chars"].median()),
            "improved_gt_50pct": improved,
            "improved_gt_100pct": doubled,
            "out_dir": str(OUT_DIR),
        }
        (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
