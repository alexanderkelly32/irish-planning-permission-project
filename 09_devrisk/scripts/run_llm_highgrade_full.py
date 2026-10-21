"""Runner: full DeepSeek extraction over all improved OCR texts (chunked).

Builds batch_requests_partNN.jsonl (100 rows each) from every *_highgrade.txt
in the OCR folder, then runs the standard deepseek runner per part.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402
from scripts.run_llm_highgrade_sample import SYSTEM_PROMPT  # noqa: E402

OCR_DIR = settings.SILVER_DIR / "refusal_highgrade_ocr"
OUT_DIR = settings.SILVER_DIR / "llm_highgrade_full"
CHUNK = 100


def build_parts() -> int:
    texts = sorted(OCR_DIR.glob("*_highgrade.txt"))
    texts = [t for t in texts if t.stat().st_size > 400]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    part = 1
    rows: list[dict] = []
    for text_path in texts:
        key = text_path.stem.replace("_highgrade", "")
        content = text_path.read_text(encoding="utf-8", errors="ignore")
        rows.append({
            "custom_id": key,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "deepseek-v4-pro",
                "max_completion_tokens": 500,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
            },
        })
        if len(rows) >= CHUNK:
            out = OUT_DIR / f"batch_requests_part{part:02d}.jsonl"
            with out.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            part += 1
            rows = []
    if rows:
        out = OUT_DIR / f"batch_requests_part{part:02d}.jsonl"
        with out.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        part += 1
    return part - 1


if __name__ == "__main__":
    parts = build_parts()
    print(f"built {parts} batch parts in {OUT_DIR}", flush=True)
    if parts:
        result = subprocess.run(
            [sys.executable, "-u", "-X", "utf8",
             str(settings.ROOT / "02_development" / "scripts" / "run_deepseek_extraction.py"),
             "--out-dir", str(OUT_DIR)],
            capture_output=False,
        )
        print("deepseek extraction exit:", result.returncode, flush=True)
