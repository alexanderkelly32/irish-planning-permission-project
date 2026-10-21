#!/usr/bin/env python3
"""Refusal-reason coverage driver for recent large residential schemes.

Closes the rationale gap for refused GE10 applications decided 2021-2025 by
reusing the existing pipeline pieces:

  python 03_refusal/scripts/run_refusal_coverage.py gap
  python 03_refusal/scripts/run_refusal_coverage.py download
  python 03_refusal/scripts/run_refusal_coverage.py ocr
  python 03_refusal/scripts/run_refusal_coverage.py prepare
  python 02_development/scripts/run_deepseek_extraction.py --out-dir 03_refusal/current/llm_new_ge10 --model deepseek-v4-pro
  python 03_refusal/scripts/run_refusal_coverage.py merge
  python 05_policy/scripts/build_comparable_metadata.py   # rebuild display packs

Each stage is resumable. New extractions land in
03_refusal/current/refusal_reasons_cases_llm_new.csv and are merged into the
display metadata as a source AFTER the human-verified retagged master - the
canonical master itself is never modified.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "03_refusal" / "scripts"))
sys.path.insert(0, str(ROOT / "02_development" / "scripts"))

GE10_MASTER = ROOT / "03_refusal" / "current" / "greater_than_10_units_with_refusal_reasons_master.csv"
CANONICAL = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
LLM_NEW = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_llm_new.csv"
GE10_SCORED = ROOT / "05_policy" / "current" / "ge10_scored_2024_25.csv"
GAP_CSV = ROOT / "03_refusal" / "current" / "refusal_reasons_gap_2021_2025.csv"
DOCS_DIR = ROOT / "03_refusal" / "documents" / "downloaded"
OCR_DIR = ROOT / "03_refusal" / "documents" / "ocr"
WORK_DIR = ROOT / "03_refusal" / "current" / "llm_new_ge10"

DECISION_LO = "2021-01-01"
DECISION_HI = "2025-12-23"


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def safe_filename(value: str) -> str:
    value = str(value or "").strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:180]


def join_key(row: pd.Series) -> str:
    return f"{norm(row['PlanningAuthority'])}__{norm(row['ApplicationNumber'])}"


def _pdf_paths(stem: str) -> list[Path]:
    return [DOCS_DIR / f"{stem}_Decision.pdf", DOCS_DIR / f"{stem}_Decision_Reasons.pdf"]


def _text_paths(stem: str) -> list[Path]:
    return [OCR_DIR / f"{stem}_Decision_ocr.txt", DOCS_DIR / f"{stem}_Decision_Reasons.txt"]


def _has_pdf(stem: str) -> bool:
    return any(path.exists() for path in _pdf_paths(stem))


def _has_text(stem: str) -> bool:
    return any(path.exists() for path in _text_paths(stem))


def _read_text_for(stem: str) -> tuple[str, str]:
    for path in _text_paths(stem):
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore"), path.suffix
    for path in _pdf_paths(stem):
        if path.exists():
            return _read_ocr_for(path), "pdf"
    return "", "none"


def load_gap() -> pd.DataFrame:
    ge10 = pd.read_csv(GE10_MASTER, low_memory=False)
    decision = ge10["Decision"].fillna("").astype(str).str.upper()
    refused = decision.str.contains("REFUS")
    decided = pd.to_datetime(ge10["DecisionDate"], errors="coerce")
    in_window = (decided >= DECISION_LO) & (decided <= DECISION_HI)
    reason_count = pd.to_numeric(ge10["reason_count"], errors="coerce").fillna(0)
    ge10 = ge10[refused & in_window & (reason_count <= 0)].copy()
    ge10["_join"] = ge10.apply(join_key, axis=1)

    covered: set[str] = set()
    for path in (CANONICAL, LLM_NEW):
        if path.exists():
            frame = pd.read_csv(path, low_memory=False)
            if "council" in frame.columns and "application_number" in frame.columns:
                with_reasons = frame[pd.to_numeric(frame["reason_count"], errors="coerce").fillna(0) > 0]
                covered |= set(with_reasons["council"].map(norm) + "__" + with_reasons["application_number"].map(norm))
    ge10 = ge10[~ge10["_join"].isin(covered)].copy()

    # Holdout refused schemes with no reasons anywhere (some live outside the GE10 window/master).
    if GE10_SCORED.exists():
        scored = pd.read_csv(GE10_SCORED, low_memory=False)
        holdout_refused = scored[scored["outcome"].astype(str).str.upper().str.contains("REFUS")].copy()
        holdout_refused["_join"] = (
            holdout_refused["council"].map(norm) + "__"
            + holdout_refused["case_key"].astype(str).str.split("__", n=1).str[-1].map(norm)
        )
        holdout_refused = holdout_refused[~holdout_refused["_join"].isin(covered)]
        ge10_joins = set(ge10["_join"])
        links = dict(zip(ge10["_join"], ge10["LinkAppDetails"]))
        extra_rows = []
        for _, row in holdout_refused.iterrows():
            if row["_join"] in ge10_joins:
                continue
            ge10_row = ge10[ge10["_join"] == row["_join"]]
            extra_rows.append({
                "PlanningAuthority": row["council"],
                "ApplicationNumber": str(row["case_key"]).split("__", n=1)[-1],
                "Decision": "REFUSED",
                "DecisionDate": None,
                "LinkAppDetails": links.get(row["_join"], ""),
                "_join": row["_join"],
                "reason_count": 0,
            })
        extra = pd.DataFrame(extra_rows)
        if len(extra):
            ge10 = pd.concat([ge10, extra], ignore_index=True)

    ge10["stem"] = ge10["PlanningAuthority"].map(safe_filename) + "_" + ge10["ApplicationNumber"].map(safe_filename)
    ge10["has_pdf"] = ge10["stem"].map(_has_pdf)
    ge10["has_ocr"] = ge10["stem"].map(_has_text)
    return ge10.reset_index(drop=True)


def stage_gap() -> None:
    gap = load_gap()
    gap.to_csv(GAP_CSV, index=False, encoding="utf-8")
    print(f"gap rows: {len(gap)} | with local pdf: {int(gap['has_pdf'].sum())} | with ocr: {int(gap['has_ocr'].sum())} | with eplanning link: {int(gap['LinkAppDetails'].notna().sum())}")
    by_council = gap.groupby("PlanningAuthority").agg(
        cases=("case_key", "size"), with_pdf=("has_pdf", "sum"), with_link=("LinkAppDetails", lambda s: s.notna().sum())
    ).sort_values("cases", ascending=False)
    print(by_council.to_string())
    print(f"wrote: {GAP_CSV}")


def stage_download(limit: int = 0) -> None:
    from download_all_decisions import download_decision_v3

    gap = load_gap()
    pending = gap[~gap["has_pdf"]].copy()
    if limit > 0:
        pending = pending.head(limit)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading {len(pending)} decision documents...")
    success = 0
    for _, row in pending.iterrows():
        url = str(row.get("LinkAppDetails") or "").strip()
        stem = str(row["stem"])
        filename = f"{stem}_Decision.pdf"
        if _has_pdf(stem):
            success += 1
            continue
        if not url.startswith("http"):
            print(f"  SKIP {stem}: no link")
            continue
        try:
            status, doc_type = asyncio.run(download_decision_v3(url, DOCS_DIR, filename, str(row['PlanningAuthority']), str(row['ApplicationNumber'])))
        except Exception as exc:
            status, doc_type = "error", str(type(exc).__name__)
        if status in ("success", "success_reasons", "success_agile") and _has_pdf(stem):
            success += 1
        else:
            print(f"  FAIL {stem}: {status} ({doc_type})")
    print(f"downloaded/confirmed: {success} of {len(pending)}")


def _read_ocr_for(pdf_path: Path) -> str:
    from llm_refusal_batch_prepare import read_pdf_ocr_text, read_pdf_text

    text = read_pdf_text(pdf_path)
    if len(re.sub(r"\s+", " ", text).strip()) >= 800:
        return text
    return read_pdf_ocr_text(pdf_path, page_limit=8, dpi=220)


def stage_ocr(limit: int = 0) -> None:
    gap = load_gap()
    pending = gap[~gap["has_ocr"] & gap["has_pdf"]].copy()
    if limit > 0:
        pending = pending.head(limit)
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    print(f"OCR-ing {len(pending)} decision PDFs...")
    done = 0
    for _, row in pending.iterrows():
        stem = str(row["stem"])
        out_path = OCR_DIR / f"{stem}_Decision_ocr.txt"
        if out_path.exists():
            done += 1
            continue
        text = ""
        for path in _pdf_paths(stem):
            if path.exists():
                text = _read_ocr_for(path)
                if text.strip():
                    break
        if not text.strip():
            print(f"  EMPTY {stem}")
            continue
        out_path.write_text(text, encoding="utf-8")
        done += 1
    print(f"ocr written: {done} of {len(pending)}")


def stage_prepare(part_size: int = 1500) -> None:
    from llm_refusal_batch_prepare import select_text_window
    from retag_weak_themes import SYSTEM_PROMPT, build_request

    gap = load_gap()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for _, row in gap.iterrows():
        stem = str(row["stem"])
        text, source = _read_text_for(stem)
        if not text.strip():
            continue
        window = select_text_window(text, max_chars=14000)
        if len(window) < 200:
            continue
        custom_id = str(row["_join"])
        rows.append((custom_id, build_request(custom_id, window, model="deepseek-v4-pro"), source))

    parts = [rows[i:i + part_size] for i in range(0, len(rows), part_size)]
    for number, part in enumerate(parts, start=1):
        out = WORK_DIR / f"batch_requests_part{number:02d}.jsonl"
        with out.open("w", encoding="utf-8") as handle:
            for custom_id, request, _source in part:
                handle.write(json.dumps(request, ensure_ascii=True) + "\n")
    meta = pd.DataFrame([{"custom_id": r[0], "source": r[2]} for r in rows])
    meta.to_csv(WORK_DIR / "prepare_meta.csv", index=False, encoding="utf-8")
    print(f"prepared {len(rows)} requests in {len(parts)} part(s) -> {WORK_DIR}")
    for number, part in enumerate(parts, start=1):
        print(f"  part{number:02d}: {len(part)} rows")


def stage_merge() -> None:
    from run_deepseek_extraction import complete_custom_ids

    gap = load_gap()
    meta = dict(zip(gap["_join"], gap[["PlanningAuthority", "ApplicationNumber", "Decision", "DecisionDate", "case_key"]].values.tolist()))
    out_rows = []
    long_rows = []
    for part_file in sorted(WORK_DIR.glob("batch_output_part*.jsonl")):
        for line in part_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            custom_id = str(item.get("custom_id", ""))
            council, app, decision, decision_date, case_key = meta.get(custom_id, ["", "", "", "", ""])
            if item.get("error"):
                long_rows.append({"case_key": case_key, "council": council, "application_number": app,
                                  "decision": decision, "decision_date": decision_date, "status": "error",
                                  "reason_count": 0, "reasons_joined": "", "case_primary_tags": "",
                                  "case_top_primary_tag": "", "tag_evidence": "", "tag_confidence": "",
                                  "tag_extraction_model": "deepseek-v4-pro", "error": str(item["error"])[:200]})
                continue
            try:
                content = item["response"]["body"]["choices"][0]["message"]["content"]
                payload = json.loads(content)
            except Exception:
                payload = {}
            evidence = payload.get("evidence") or {}
            reasons_joined = "; ".join(str(v) for v in evidence.values() if str(v).strip())
            tags = str(payload.get("case_primary_tags") or "")
            top = str(payload.get("case_top_primary_tag") or "")
            confidence = str(payload.get("confidence") or "")
            note = str(payload.get("note") or "")
            reason_count = len(evidence)
            out_rows.append({
                "case_key": case_key, "council": council, "application_number": app,
                "decision": decision, "decision_date": decision_date, "status": str(payload.get("status") or ""),
                "reason_count": reason_count, "reasons_joined": reasons_joined,
                "case_primary_tags": tags, "case_top_primary_tag": top,
                "tag_evidence": json.dumps(evidence), "tag_confidence": confidence,
                "tag_extraction_model": "deepseek-v4-pro", "note": note,
            })
    frame = pd.DataFrame(out_rows)
    existing = pd.read_csv(LLM_NEW, low_memory=False) if LLM_NEW.exists() else pd.DataFrame()
    if len(existing):
        frame = pd.concat([existing, frame], ignore_index=True).drop_duplicates("case_key", keep="first")
    frame.to_csv(LLM_NEW, index=False, encoding="utf-8")
    with_reasons = int((frame["reason_count"] > 0).sum())
    print(f"merged {len(out_rows)} new responses; llm_new total {len(frame)} rows, {with_reasons} with reasons -> {LLM_NEW}")
    total = load_gap()
    print(f"remaining gap after merge: {len(total)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["gap", "download", "ocr", "prepare", "merge"])
    parser.add_argument("--limit", type=int, default=0, help="cap download/ocr rows (0 = all)")
    args = parser.parse_args()
    if args.stage == "gap":
        stage_gap()
    elif args.stage == "download":
        stage_download(limit=args.limit)
    elif args.stage == "ocr":
        stage_ocr(limit=args.limit)
    elif args.stage == "prepare":
        stage_prepare()
    elif args.stage == "merge":
        stage_merge()


if __name__ == "__main__":
    main()
