#!/usr/bin/env python3
"""
LLM-first pass over OCR decision texts to delicately characterise refusal reasons.

This script does NOT do regex-only extraction; it asks an LLM to read each OCR text
and return structured JSON for refusal reasons plus characterisation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from openai import OpenAI


SYSTEM_PROMPT = """You are a careful planning-document analyst.
Task: read Irish planning decision OCR text and extract refusal reasons only.

Rules:
1) Extract ONLY explicit reasons for refusal / grounds for refusal.
2) Do not include planning conditions, procedural notes, table of contents, or applicant details.
3) If reasons are unclear, return an empty list and explain uncertainty briefly.
4) Keep each reason concise but faithful to the document wording.
5) Assign categories from this set (multiple allowed):
   - traffic_access
   - flooding_drainage
   - water_wastewater
   - design_layout
   - density_scale
   - residential_amenity
   - land_use_policy
   - heritage_archaeology
   - ecology_trees
   - premature_or_info_gap
   - other
6) Output valid JSON only following the requested schema.
"""


def safe_filename(value: str) -> str:
    value = str(value or "").strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:180]


def infer_case_key(file_stem: str) -> str:
    # Handles OCR names and original text names.
    stem = file_stem
    for suffix in (
        "_Decision_Reasons_ocr",
        "_Decision_Summary_ocr",
        "_Decision_ocr",
        "_Decision_Reasons",
        "_Decision_Summary",
        "_ocr",
        "_Decision",
    ):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem.lower()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def select_text_window(text: str, max_chars: int = 24000) -> str:
    """Prefer windows around refusal-related language; fall back to head/tail."""
    text = normalize_text(text)
    if len(text) <= max_chars:
        return text

    patterns = [
        r"reasons?\s+for\s+refusal",
        r"grounds?\s+for\s+refusal",
        r"refuse(?:s|d)?\s+permission",
        r"planning\s+authority\s+refuses",
    ]

    spans: List[Tuple[int, int]] = []
    lower = text.lower()
    for pat in patterns:
        for m in re.finditer(pat, lower, flags=re.IGNORECASE):
            start = max(0, m.start() - 3000)
            end = min(len(text), m.end() + 14000)
            spans.append((start, end))

    if spans:
        spans.sort()
        merged: List[Tuple[int, int]] = []
        for st, en in spans:
            if not merged or st > merged[-1][1]:
                merged.append((st, en))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], en))
        chunks = [text[st:en] for st, en in merged]
        joined = "\n\n".join(chunks)
        return joined[:max_chars]

    # fallback: blend beginning + end
    head = text[: int(max_chars * 0.7)]
    tail = text[-int(max_chars * 0.3) :]
    return (head + "\n\n[...TRIMMED...]\n\n" + tail)[:max_chars]


def parse_json_response(raw: str) -> Dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in model response.")
    return json.loads(m.group(0))


def load_source_index(source_csv: Path) -> Dict[str, Dict[str, str]]:
    if not source_csv.exists():
        return {}
    df = pd.read_csv(source_csv, low_memory=False)
    out: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        council = str(row.get("PlanningAuthority", "")).strip()
        app = str(row.get("ApplicationNumber", "")).strip()
        if not council or not app:
            continue
        key = f"{safe_filename(council)}_{safe_filename(app)}".lower()
        out[key] = {
            "council": council,
            "application_number": app,
            "decision": str(row.get("Decision", "")),
            "decision_date": str(row.get("DecisionDate", "")),
        }
    return out


def read_checkpoint(path: Path) -> Dict[str, Dict]:
    if not path.exists():
        return {}
    done: Dict[str, Dict] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            done[str(obj.get("case_key", "")).lower()] = obj
        except Exception:
            continue
    return done


def append_checkpoint(path: Path, payload: Dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def run_llm(
    client: OpenAI,
    model: str,
    text_for_model: str,
    file_name: str,
    max_output_tokens: int,
) -> Dict:
    def _call(user_payload: Dict, extra_system: str = "") -> str:
        system_msg = SYSTEM_PROMPT + ("\n" + extra_system if extra_system else "")
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=max_output_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    user_prompt = {
        "file_name": file_name,
        "instruction": "Extract and characterise refusal reasons from this OCR text.",
        "output_schema": {
            "found_refusal_reasons": "boolean",
            "document_summary": "short string",
            "confidence_overall": "number 0..1",
            "notes": "short string",
            "reasons": [
                {
                    "reason_index": "integer starting at 1",
                    "reason_text": "string",
                    "short_label": "string",
                    "categories": ["array of allowed category strings"],
                    "confidence": "number 0..1",
                    "evidence_quote": "short supporting quote from OCR text",
                }
            ],
        },
        "ocr_text": text_for_model,
    }

    raw = _call(user_prompt)
    try:
        data = parse_json_response(raw)
    except Exception:
        raw_retry = _call(
            user_prompt,
            extra_system=(
                "Return strictly valid JSON only. "
                "No markdown, no comments, no trailing commas."
            ),
        )
        data = parse_json_response(raw_retry)
    if "reasons" not in data or not isinstance(data["reasons"], list):
        data["reasons"] = []
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr-dir", default="downloads/ocr_text")
    parser.add_argument("--txt-dir", default="downloads/rejected_decisions")
    parser.add_argument("--source-csv", default="greater_than_10_units_with_flooding.csv")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--exclude-prefix", default="Kerry_County_Council_")
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--max-chars", type=int, default=24000)
    parser.add_argument("--max-output-tokens", type=int, default=450)
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    parser.add_argument("--checkpoint", default="downloads/llm_refusal_checkpoint.jsonl")
    parser.add_argument("--output-cases", default="downloads/llm_refusal_reasons_cases.csv")
    parser.add_argument("--output-long", default="downloads/llm_refusal_reasons_long.csv")
    parser.add_argument(
        "--output-merged",
        default="downloads/greater_than_10_units_with_flooding_with_llm_reasons.csv",
    )
    parser.add_argument("--review-from-checkpoint", default="")
    parser.add_argument("--review-threshold", type=float, default=0.7)
    parser.add_argument("--review-include-zero-reasons", action="store_true")
    parser.add_argument("--review-include-errors", action="store_true")
    parser.add_argument(
        "--only-case-keys",
        default="",
        help="Comma-separated case_key list to process (overrides other selection).",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is not set. Set it in your shell and re-run this script."
        )

    ocr_dir = Path(args.ocr_dir)
    txt_dir = Path(args.txt_dir)
    checkpoint_path = Path(args.checkpoint)
    out_cases = Path(args.output_cases)
    out_long = Path(args.output_long)
    out_merged = Path(args.output_merged)
    for p in (checkpoint_path, out_cases, out_long, out_merged):
        p.parent.mkdir(parents=True, exist_ok=True)

    source_index = load_source_index(Path(args.source_csv))
    done = read_checkpoint(checkpoint_path)
    review_keys = set()
    if args.review_from_checkpoint:
        review_done = read_checkpoint(Path(args.review_from_checkpoint))
        for case_key, row in review_done.items():
            try:
                conf = float(row.get("confidence_overall", 0) or 0)
            except Exception:
                conf = 0.0
            reasons = row.get("reasons", [])
            reason_count = len(reasons) if isinstance(reasons, list) else 0
            status = str(row.get("status", "")).lower()
            if conf < args.review_threshold:
                review_keys.add(case_key)
                continue
            if args.review_include_zero_reasons and reason_count == 0:
                review_keys.add(case_key)
                continue
            if args.review_include_errors and status == "error":
                review_keys.add(case_key)
                continue

    # Build one best input text per case, using both OCR text and original txt files.
    case_candidates: Dict[str, List[Dict[str, object]]] = {}
    for f in sorted(ocr_dir.glob("*_ocr.txt")):
        if args.exclude_prefix and f.name.startswith(args.exclude_prefix):
            continue
        case_key = infer_case_key(f.stem)
        case_candidates.setdefault(case_key, []).append(
            {"path": f, "source_type": "ocr_pdf"}
        )
    for f in sorted(txt_dir.glob("*.txt")):
        if args.exclude_prefix and f.name.startswith(args.exclude_prefix):
            continue
        case_key = infer_case_key(f.stem)
        case_candidates.setdefault(case_key, []).append(
            {"path": f, "source_type": "txt_original"}
        )

    def pick_best(case_key: str, candidates: List[Dict[str, object]]) -> Dict[str, object]:
        def score(c: Dict[str, object]) -> int:
            p = c["path"]
            if not isinstance(p, Path):
                return 0
            name = p.name
            size = int(p.stat().st_size) if p.exists() else 0
            if c["source_type"] == "txt_original" and "_Decision_Reasons" in name:
                return 1000000 + size
            if c["source_type"] == "txt_original":
                return 700000 + size
            return 500000 + size

        chosen = sorted(candidates, key=score, reverse=True)[0]
        chosen["alt_source_count"] = max(0, len(candidates) - 1)
        chosen["all_sources"] = ";".join(sorted(str(c["path"].name) for c in candidates))
        return chosen

    only_keys = set()
    if args.only_case_keys:
        only_keys = {k.strip().lower() for k in args.only_case_keys.split(",") if k.strip()}

    selected_docs: List[Dict[str, object]] = []
    for case_key, candidates in sorted(case_candidates.items()):
        if only_keys and case_key not in only_keys:
            continue
        if not only_keys and review_keys and case_key not in review_keys:
            continue
        selected = pick_best(case_key, candidates)
        selected["case_key"] = case_key
        selected_docs.append(selected)

    if args.max_files and args.max_files > 0:
        selected_docs = selected_docs[: args.max_files]

    client = OpenAI(api_key=api_key)
    processed = 0
    skipped = 0

    for i, doc in enumerate(selected_docs, start=1):
        file_path = doc["path"]
        case_key = str(doc["case_key"])
        if case_key in done and case_key not in review_keys and not only_keys:
            skipped += 1
            continue

        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        text_for_model = select_text_window(raw, max_chars=args.max_chars)
        status = "ok"
        error = ""
        payload: Dict = {}
        t0 = time.perf_counter()
        try:
            payload = run_llm(
                client,
                args.model,
                text_for_model,
                file_path.name,
                max_output_tokens=args.max_output_tokens,
            )
        except Exception as exc:
            status = "error"
            error = str(exc)[:500]
            payload = {
                "found_refusal_reasons": False,
                "document_summary": "",
                "confidence_overall": 0.0,
                "notes": "",
                "reasons": [],
            }

        row = {
            "case_key": case_key,
            "file_name": file_path.name,
            "source_path": str(file_path),
            "source_type": str(doc.get("source_type", "")),
            "alt_source_count": int(doc.get("alt_source_count", 0)),
            "all_sources": str(doc.get("all_sources", "")),
            "status": status,
            "error": error,
            "elapsed_sec": round(time.perf_counter() - t0, 2),
            "input_chars": len(raw),
            "model_chars": len(text_for_model),
            "model": args.model,
            "found_refusal_reasons": bool(payload.get("found_refusal_reasons", False)),
            "document_summary": str(payload.get("document_summary", "")),
            "confidence_overall": payload.get("confidence_overall", 0),
            "notes": str(payload.get("notes", "")),
            "reasons": payload.get("reasons", []),
        }
        append_checkpoint(checkpoint_path, row)
        done[case_key] = row
        processed += 1
        print(
            f"[{i}/{len(selected_docs)}] {file_path.name} ({row['source_type']}) -> "
            f"{status} ({len(row['reasons'])} reasons)"
        )
        if args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    # Build outputs from checkpoint (including previous runs)
    cases_rows: List[Dict] = []
    long_rows: List[Dict] = []
    for case_key, item in sorted(done.items()):
        meta = source_index.get(case_key, {})
        reasons = item.get("reasons", [])
        case = {
            "case_key": case_key,
            "council": meta.get("council", ""),
            "application_number": meta.get("application_number", ""),
            "decision": meta.get("decision", ""),
            "decision_date": meta.get("decision_date", ""),
            "file_name": item.get("file_name", ""),
            "status": item.get("status", ""),
            "source_type": item.get("source_type", ""),
            "alt_source_count": item.get("alt_source_count", 0),
            "error": item.get("error", ""),
            "model": item.get("model", ""),
            "found_refusal_reasons": item.get("found_refusal_reasons", False),
            "confidence_overall": item.get("confidence_overall", 0),
            "document_summary": item.get("document_summary", ""),
            "notes": item.get("notes", ""),
            "reason_count": len(reasons),
        }
        cases_rows.append(case)
        if reasons:
            for r in reasons:
                long_rows.append(
                    {
                        **case,
                        "reason_index": r.get("reason_index", ""),
                        "reason_text": r.get("reason_text", ""),
                        "short_label": r.get("short_label", ""),
                        "categories": ";".join(r.get("categories", []))
                        if isinstance(r.get("categories", []), list)
                        else str(r.get("categories", "")),
                        "reason_confidence": r.get("confidence", 0),
                        "evidence_quote": r.get("evidence_quote", ""),
                    }
                )
        else:
            long_rows.append(
                {
                    **case,
                    "reason_index": "",
                    "reason_text": "",
                    "short_label": "",
                    "categories": "",
                    "reason_confidence": 0,
                    "evidence_quote": "",
                }
            )

    cases_df = pd.DataFrame(cases_rows)
    long_df = pd.DataFrame(long_rows)
    cases_df.to_csv(out_cases, index=False, encoding="utf-8")
    long_df.to_csv(out_long, index=False, encoding="utf-8")

    src = Path(args.source_csv)
    if src.exists():
        source_df = pd.read_csv(src, low_memory=False)
        source_df["case_key"] = (
            source_df["PlanningAuthority"].fillna("").astype(str).map(safe_filename).str.lower()
            + "_"
            + source_df["ApplicationNumber"].fillna("").astype(str).map(safe_filename).str.lower()
        )
        merged = source_df.merge(
            cases_df[
                [
                    "case_key",
                    "found_refusal_reasons",
                    "reason_count",
                    "confidence_overall",
                    "document_summary",
                    "notes",
                    "status",
                ]
            ],
            on="case_key",
            how="left",
        )
        merged["reason_count"] = merged["reason_count"].fillna(0).astype(int)
        merged["has_llm_refusal_reasons"] = merged["reason_count"] > 0
        merged.to_csv(out_merged, index=False, encoding="utf-8")

    print(f"Processed this run: {processed} | Skipped from checkpoint: {skipped}")
    print(f"Wrote: {out_cases}")
    print(f"Wrote: {out_long}")
    print(f"Wrote: {out_merged}")
    print(f"Checkpoint: {checkpoint_path}")


if __name__ == "__main__":
    main()
