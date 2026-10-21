#!/usr/bin/env python3
"""
Extract refusal reasons from Irish planning decision files, tag themes,
and merge results back to the source planning dataset.

Inputs (defaults):
- decisions folder: ./downloads/rejected_decisions2
- source dataset:   ./greater_than_10_units_with_flooding.csv

Outputs (defaults):
- ./downloads/refusal_reasons_long.csv
- ./downloads/refusal_reasons_cases.csv
- ./downloads/refusal_reason_tag_counts.csv
- ./downloads/greater_than_10_units_with_flooding_with_refusal_reasons.csv
"""

from __future__ import annotations

import argparse
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from pypdf import PdfReader

try:
    import fitz  # PyMuPDF
    from rapidocr_onnxruntime import RapidOCR

    OCR_AVAILABLE = True
    OCR_IMPORT_ERROR = ""
except Exception as exc:
    OCR_AVAILABLE = False
    OCR_IMPORT_ERROR = str(exc)


logging.getLogger("pypdf").setLevel(logging.ERROR)


THEME_PATTERNS: Dict[str, List[str]] = {
    "traffic_access": [
        r"\btraffic\b",
        r"\baccess\b",
        r"\bjunction\b",
        r"\broad\b",
        r"\bparking\b",
        r"\bvisibility\b",
        r"\bdmurs\b",
        r"\btransport\b",
    ],
    "flooding_drainage": [
        r"\bflood",
        r"\bsurface water\b",
        r"\bdrainage\b",
        r"\bsuds\b",
        r"\battenuation\b",
        r"\boverland flow\b",
    ],
    "water_wastewater": [
        r"\birish water\b",
        r"\bwastewater\b",
        r"\bsewer\b",
        r"\bwater supply\b",
        r"\bfoul water\b",
    ],
    "design_layout": [
        r"\bdesign\b",
        r"\blayout\b",
        r"\burban design\b",
        r"\bpublic realm\b",
        r"\bstreetscape\b",
    ],
    "density_scale": [
        r"\bdensity\b",
        r"\boverdevelopment\b",
        r"\bscale\b",
        r"\bheight\b",
        r"\bmass(ing)?\b",
    ],
    "residential_amenity": [
        r"\bamenit",
        r"\boverlooking\b",
        r"\bovershadow",
        r"\bprivacy\b",
        r"\bdaylight\b",
        r"\bsunlight\b",
        r"\bnoise\b",
        r"\bopen space\b",
    ],
    "land_use_policy": [
        r"\bzoning\b",
        r"\bcounty development plan\b",
        r"\blocal area plan\b",
        r"\bpolicy\b",
        r"\bobjective\b",
        r"\bnational planning framework\b",
    ],
    "heritage_archaeology": [
        r"\bprotected structure\b",
        r"\barchitectural conservation area\b",
        r"\barchaeolog",
        r"\bheritage\b",
    ],
    "ecology_trees": [
        r"\becolog",
        r"\bbiodivers",
        r"\bhabitat",
        r"\bnatura\b",
        r"\bappropriate assessment\b",
        r"\btree\b",
    ],
    "premature_or_info_gap": [
        r"\bpremature\b",
        r"\binsufficient information\b",
        r"\binadequate information\b",
        r"\bunable to make a full assessment\b",
        r"\bclarify\b",
    ],
}


def safe_filename(value: str) -> str:
    value = str(value or "").strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:180]


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = text.replace("â€™", "'").replace("â€œ", '"').replace("â€", '"').replace("â€“", "-")
    text = text.replace("Â·", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_reason(text: str) -> str:
    text = normalize_whitespace(text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -:\t")


def dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = re.sub(r"\W+", "", item.lower())
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def infer_case_key(file_stem: str) -> str:
    for suffix in ("_Decision_Reasons", "_Decision_Summary", "_Decision"):
        if file_stem.endswith(suffix):
            return file_stem[: -len(suffix)].lower()
    return file_stem.lower()


def choose_best_file(files: List[Path]) -> Path:
    ordered = sorted(
        files,
        key=lambda p: (
            0
            if p.suffix.lower() == ".txt" and p.stem.endswith("_Decision_Reasons")
            else 1
            if p.suffix.lower() == ".txt"
            else 2
            if p.suffix.lower() == ".pdf"
            else 3,
            p.name,
        ),
    )
    return ordered[0]


def read_text_file(path: Path) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc, errors="ignore")
        except Exception:
            continue
    return ""


def read_pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path), strict=False)
    except Exception:
        return ""
    chunks: List[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunks)


def read_pdf_ocr_text(path: Path, ocr_engine, page_limit: int = 8, dpi: int = 220) -> str:
    if not OCR_AVAILABLE:
        return ""
    try:
        doc = fitz.open(str(path))
        max_pages = min(len(doc), max(1, page_limit))
        chunks: List[str] = []
        zoom = max(1.2, dpi / 96.0)
        matrix = fitz.Matrix(zoom, zoom)
        for i in range(max_pages):
            try:
                pix = doc[i].get_pixmap(matrix=matrix, alpha=False)
                img_bytes = pix.tobytes("png")
                result, _ = ocr_engine(img_bytes)
                if result:
                    chunks.extend(x[1] for x in result if len(x) > 1 and str(x[1]).strip())
            except Exception:
                continue
        return "\n".join(chunks)
    except Exception:
        return ""


def extract_numbered_sections(text: str) -> List[str]:
    patterns = [
        r"(?ms)^\s*(\d{1,3}|[IVXLCDM]{1,8})[\.\)]\s+(.*?)(?=^\s*(?:\d{1,3}|[IVXLCDM]{1,8})[\.\)]\s+|\Z)",
        r"(?ms)^\s*Reason(?:\s+for\s+Refusal)?\s*(?:No\.?|#)?\s*(\d{1,3})\s*[:\-]\s*(.*?)(?=^\s*Reason(?:\s+for\s+Refusal)?\s*(?:No\.?|#)?\s*\d{1,3}\s*[:\-]|\Z)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            reasons = [clean_reason(m[1]) for m in matches if clean_reason(m[1])]
            if reasons:
                return reasons
    return []


def split_by_refusal_phrase(text: str) -> List[str]:
    phrase = re.compile(
        r"(?i)(contrary to the proper planning and sustainable development of the area\.?)"
    )
    parts = phrase.split(text)
    reasons: List[str] = []
    for i in range(0, len(parts) - 1, 2):
        chunk = clean_reason(parts[i] + " " + parts[i + 1])
        if len(chunk) >= 70:
            reasons.append(chunk)
    return reasons


def extract_reasons(raw_text: str) -> Tuple[List[str], str]:
    text = normalize_whitespace(raw_text)
    if not text:
        return [], "empty_text"

    section_patterns = [
        r"(?is)Reasons?\s+for\s+refusal\s*[:\-]?\s*(.+)$",
        r"(?is)Grounds?\s+for\s+refusal\s*[:\-]?\s*(.+)$",
        r"(?is)The\s+planning\s+authority\s+refuses\s+permission\s+for\s+the\s+following\s+reasons\s*[:\-]?\s*(.+)$",
    ]
    section_text = ""
    for pattern in section_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            section_text = match.group(1).strip()
            break

    if section_text:
        numbered = extract_numbered_sections(section_text)
        if numbered:
            return dedupe_preserve_order(numbered), "numbered"

    explicit_reason_blocks = extract_numbered_sections(text)
    if explicit_reason_blocks:
        return dedupe_preserve_order(explicit_reason_blocks), "numbered"

    fallback = split_by_refusal_phrase(section_text or text)
    if fallback:
        return dedupe_preserve_order(fallback), "phrase_split"

    return [], "not_found"


def load_source_index(source_csv: Path) -> Dict[str, Dict[str, str]]:
    if not source_csv.exists():
        return {}
    df = pd.read_csv(source_csv, low_memory=False)
    index: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        council = str(row.get("PlanningAuthority", "")).strip()
        app = str(row.get("ApplicationNumber", "")).strip()
        if not council or not app:
            continue
        key = f"{safe_filename(council)}_{safe_filename(app)}".lower()
        index[key] = {
            "council": council,
            "application_number": app,
            "decision": str(row.get("Decision", "")),
            "decision_date": str(row.get("DecisionDate", "")),
            "source_row_status": str(row.get("ApplicationStatus", "")),
        }
    return index


def classify_reason(reason_text: str) -> Tuple[str, str]:
    text = (reason_text or "").lower()
    hits: List[str] = []
    for tag, patterns in THEME_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                hits.append(tag)
                break
    if not hits:
        return "other", "other"
    return hits[0], ";".join(hits)


def build_case_key_from_source(df: pd.DataFrame) -> pd.Series:
    council = df["PlanningAuthority"].fillna("").astype(str).map(safe_filename)
    app = df["ApplicationNumber"].fillna("").astype(str).map(safe_filename)
    return (council + "_" + app).str.lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="downloads/rejected_decisions")
    parser.add_argument("--source-csv", default="greater_than_10_units_with_flooding.csv")
    parser.add_argument("--output-long", default="downloads/refusal_reasons_long.csv")
    parser.add_argument("--output-cases", default="downloads/refusal_reasons_cases.csv")
    parser.add_argument("--output-tag-counts", default="downloads/refusal_reason_tag_counts.csv")
    parser.add_argument(
        "--output-merged",
        default="downloads/greater_than_10_units_with_flooding_with_refusal_reasons.csv",
    )
    parser.add_argument("--use-ocr", action="store_true")
    parser.add_argument("--ocr-page-limit", type=int, default=8)
    parser.add_argument("--progress-every", type=int, default=50)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    source_csv = Path(args.source_csv)
    if not input_dir.exists():
        raise SystemExit(f"Input folder not found: {input_dir}")

    source_index = load_source_index(source_csv)

    case_files: Dict[str, List[Path]] = defaultdict(list)
    for file_path in input_dir.iterdir():
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".txt", ".pdf", ".djvu"}:
            continue
        case_files[infer_case_key(file_path.stem)].append(file_path)

    long_rows: List[Dict[str, object]] = []
    case_rows: List[Dict[str, object]] = []
    ocr_engine = RapidOCR() if (args.use_ocr and OCR_AVAILABLE) else None

    for idx_case, (case_key, files) in enumerate(sorted(case_files.items()), start=1):
        if args.progress_every > 0 and idx_case % args.progress_every == 0:
            print(f"Progress: {idx_case}/{len(case_files)}")
        chosen = choose_best_file(files)
        ext = chosen.suffix.lower()

        if ext == ".txt":
            raw_text = read_text_file(chosen)
            extraction_source = "text_file"
        elif ext == ".pdf":
            raw_text = read_pdf_text(chosen)
            extraction_source = "pdf_text"
        else:
            raw_text = ""
            extraction_source = "djvu_unsupported"

        reasons, method = extract_reasons(raw_text)

        if (
            args.use_ocr
            and ext == ".pdf"
            and not reasons
            and OCR_AVAILABLE
            and ocr_engine is not None
            and len((raw_text or "").strip()) < 1200
        ):
            ocr_text = read_pdf_ocr_text(chosen, ocr_engine=ocr_engine, page_limit=args.ocr_page_limit)
            ocr_reasons, ocr_method = extract_reasons(ocr_text)
            if ocr_reasons:
                raw_text = ocr_text
                reasons = ocr_reasons
                method = ocr_method
                extraction_source = "pdf_ocr"

        meta = source_index.get(case_key, {})
        base_case = {
            "case_key": case_key,
            "council": meta.get("council", ""),
            "application_number": meta.get("application_number", ""),
            "decision": meta.get("decision", ""),
            "decision_date": meta.get("decision_date", ""),
            "source_row_status": meta.get("source_row_status", ""),
            "source_file": str(chosen),
            "available_files": "; ".join(sorted(p.name for p in files)),
            "extraction_source": extraction_source,
            "extraction_method": method,
            "raw_text_len": len(raw_text or ""),
            "reason_count": len(reasons),
        }

        if reasons:
            enriched_reasons: List[Dict[str, object]] = []
            for idx, reason in enumerate(reasons, start=1):
                primary_tag, all_tags = classify_reason(reason)
                enriched_reasons.append(
                    {
                        "reason_index": idx,
                        "reason_text": reason,
                        "reason_char_len": len(reason),
                        "primary_tag": primary_tag,
                        "all_tags": all_tags,
                    }
                )
                long_rows.append({**base_case, **enriched_reasons[-1]})

            case_tags = sorted(
                {t for row in enriched_reasons for t in str(row["all_tags"]).split(";") if t}
            )
            case_rows.append(
                {
                    **base_case,
                    "reasons_joined": " || ".join([r["reason_text"] for r in enriched_reasons]),
                    "case_primary_tags": ";".join(case_tags),
                    "case_top_primary_tag": Counter([r["primary_tag"] for r in enriched_reasons]).most_common(1)[0][0],
                }
            )
        else:
            long_rows.append(
                {
                    **base_case,
                    "reason_index": "",
                    "reason_text": "",
                    "reason_char_len": 0,
                    "primary_tag": "",
                    "all_tags": "",
                }
            )
            case_rows.append(
                {
                    **base_case,
                    "reasons_joined": "",
                    "case_primary_tags": "",
                    "case_top_primary_tag": "",
                }
            )

    long_df = pd.DataFrame(long_rows)
    cases_df = pd.DataFrame(case_rows)

    out_long = Path(args.output_long)
    out_cases = Path(args.output_cases)
    out_tags = Path(args.output_tag_counts)
    out_merged = Path(args.output_merged)
    for out in (out_long, out_cases, out_tags, out_merged):
        out.parent.mkdir(parents=True, exist_ok=True)

    long_df.to_csv(out_long, index=False, encoding="utf-8")
    cases_df.to_csv(out_cases, index=False, encoding="utf-8")

    tag_counts = (
        long_df[long_df["reason_text"].fillna("").str.len() > 0]["primary_tag"]
        .value_counts(dropna=False)
        .rename_axis("primary_tag")
        .reset_index(name="reason_count")
    )
    tag_counts.to_csv(out_tags, index=False, encoding="utf-8")

    if source_csv.exists():
        src = pd.read_csv(source_csv, low_memory=False)
        src["case_key"] = build_case_key_from_source(src)
        merged = src.merge(
            cases_df[
                [
                    "case_key",
                    "reason_count",
                    "reasons_joined",
                    "case_primary_tags",
                    "case_top_primary_tag",
                    "extraction_source",
                    "extraction_method",
                ]
            ],
            how="left",
            on="case_key",
        )
        merged["reason_count"] = merged["reason_count"].fillna(0).astype(int)
        merged["has_refusal_reasons"] = merged["reason_count"] > 0
        merged.to_csv(out_merged, index=False, encoding="utf-8")

    total_cases = len(cases_df)
    matched = int((cases_df["reason_count"] > 0).sum()) if total_cases else 0
    total_reasons = int(cases_df["reason_count"].sum()) if total_cases else 0
    print(f"Cases processed: {total_cases}")
    print(f"Cases with >=1 reason: {matched}")
    print(f"Total extracted reasons: {total_reasons}")
    print(f"OCR enabled: {args.use_ocr} (available={OCR_AVAILABLE})")
    if args.use_ocr and not OCR_AVAILABLE and OCR_IMPORT_ERROR:
        print(f"OCR import issue: {OCR_IMPORT_ERROR}")
    print(f"Wrote: {out_long}")
    print(f"Wrote: {out_cases}")
    print(f"Wrote: {out_tags}")
    print(f"Wrote: {out_merged}")


if __name__ == "__main__":
    main()
