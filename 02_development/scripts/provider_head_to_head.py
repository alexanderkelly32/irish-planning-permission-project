#!/usr/bin/env python3
"""Provider head-to-head: DeepSeek vs gpt-5 extraction recall/precision on the
same 100 planner-report texts.

Prepares identical request files for both providers; the DeepSeek side runs via
the existing billing-safe runner; the OpenAI side uses the Batch API
(submit_openai_batch.py). When both sides return, score.py compares extracted
value counts and overlap (a shared set of "gold" values is NOT required - the
comparison is per-text: does gpt-5 find values DeepSeek missed?).

Usage:
  python provider_head_to_head.py prepare
  python run_deepseek_extraction.py --out-dir ... --parts 1
  (submit the openai batch when credit exists)
  python provider_head_to_head.py compare
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "provider_head_to_head_2026-09-16"

sys.path.insert(0, str(ROOT / "02_development" / "scripts"))
from structured_document_extraction import EXTRACTION_FIELDS, SYSTEM_PROMPT  # noqa: E402


def build_request(custom_id: str, user_prompt: str, model: str) -> dict:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "max_completion_tokens": 1200,
            "reasoning_effort": "low",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def prepare() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for csv_path in sorted((ROOT / "02_development" / "source_data" / "planner_reports").rglob("report_ocr_extractions.csv")):
        frame = pd.read_csv(csv_path, low_memory=False)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    rng = random.Random(20260916)
    sample = combined.sample(n=min(100, len(combined)), random_state=42)
    rows = []
    deepseek = []
    openai = []
    for index, (_, row) in enumerate(sample.iterrows()):
        text_path = Path(str(row.get("text_path") or ""))
        if not text_path.exists():
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")[:9000]
        payload = {"case_key": str(row.get("case_key")), "text": text}
        user_prompt = json.dumps(payload, ensure_ascii=True)
        custom_id = f"hh-row-{index}"
        deepseek.append(build_request(custom_id, user_prompt, "deepseek-v4-pro"))
        openai.append(build_request(custom_id, user_prompt, "gpt-5"))
        rows.append({"case_key": str(row.get("case_key")), "text_path": str(text_path)})
    (OUT_DIR / "deepseek_requests_part01.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=True) for r in deepseek) + "\n", encoding="utf-8")
    (OUT_DIR / "openai_requests.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=True) for r in openai) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT_DIR / "cases.csv", index=False)
    summary = {"texts": len(rows), "deepseek_requests": len(deepseek), "openai_requests": len(openai)}
    (OUT_DIR / "prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def parse_outputs(path: Path) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", "")
        try:
            content = (item.get("response") or {}).get("body", {}).get("choices", [{}])[0].get("message", {}).get("content")
            payload = json.loads(content) if content else {}
            results[custom_id] = {
                field: payload.get(field) for field in EXTRACTION_FIELDS
            }
        except Exception:
            results[custom_id] = {}
    return results


def compare() -> None:
    deepseek_path = OUT_DIR / "batch_output_part01.jsonl"
    openai_path = OUT_DIR / "openai_output.jsonl"
    if not deepseek_path.exists():
        print(json.dumps({"status": "deepseek_output_missing"}))
        return
    if not openai_path.exists():
        print(json.dumps({"status": "openai_output_missing", "note": "submit openai_requests.jsonl via the OpenAI Batch API and save the result as openai_output.jsonl"}))
        return
    deepseek = parse_outputs(deepseek_path)
    openai_ = parse_outputs(openai_path)
    shared = set(deepseek) & set(openai_)
    rows = []
    for custom_id in sorted(shared):
        for field in EXTRACTION_FIELDS:
            rows.append({
                "field": field,
                "deepseek": deepseek[custom_id].get(field),
                "gpt5": openai_[custom_id].get(field),
            })
    frame = pd.DataFrame(rows)
    by_field = {}
    for field, group in frame.groupby("field"):
        ds_nonnull = int(group["deepseek"].notna().sum())
        gpt_nonnull = int(group["gpt5"].notna().sum())
        both = int(group.notna().all(axis=1).sum())
        agree = 0
        agree_n = 0
        for _, row in group.iterrows():
            if pd.notna(row["deepseek"]) and pd.notna(row["gpt5"]):
                agree_n += 1
                try:
                    a = float(row["deepseek"])
                    b = float(row["gpt5"])
                except (TypeError, ValueError):
                    if str(row["deepseek"]).strip().lower() == str(row["gpt5"]).strip().lower():
                        agree += 1
                    continue
                if abs(a - b) <= max(0.5, abs(b) * 0.15):
                    agree += 1
        by_field[field] = {
            "deepseek_found": ds_nonnull,
            "gpt5_found": gpt_nonnull,
            "both_found": both,
            "agreement_when_both": round(agree / agree_n, 4) if agree_n else None,
        }
    payload = {
        "shared_texts": len(shared),
        "by_field": by_field,
        "caveat": "Recall comparison only - precision needs human verification. Agreement on overlapping values measures consistency.",
    }
    (OUT_DIR / "comparison.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "compare"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        compare()
