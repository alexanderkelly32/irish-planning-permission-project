"""Runner: small DeepSeek sample on the improved OCR texts.

Waits until >= 15 high-grade texts exist (or uses whatever is there),
builds batch_requests_part01.jsonl in the sample out-dir using the same
extraction schema as the refusal campaign, then the standard deepseek runner
processes it. Result: batch_output_part01.jsonl for comparison against the
old thin-text yield.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SYSTEM_PROMPT = (
    "Extract refusal reasons from Irish planning decision text. Return strict JSON only with keys: found, reasons, notes. "
    "found: 1 if refusal reasons are present, else 0. reasons: array of objects with keys t and cats. "
    "t is concise reason text. cats is array using only: traffic_access,flooding_drainage,water_wastewater,design_layout,"
    "density_scale,residential_amenity,land_use_policy,heritage_archaeology,ecology_trees,premature_or_info_gap,other. "
    "notes: short string or null."
)

OUT_DIR = settings.SILVER_DIR / "llm_highgrade_sample"


def build_sample(limit: int = 15) -> int:
    ocr_dir = settings.SILVER_DIR / "refusal_highgrade_ocr"
    texts = sorted(ocr_dir.glob("*_highgrade.txt"))
    texts = [t for t in texts if t.stat().st_size > 400]
    if len(texts) < 8:
        print(f"only {len(texts)} improved texts yet - waiting", flush=True)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for text_path in texts[:limit]:
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
    out = OUT_DIR / "batch_requests_part01.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"sample batch -> {out} ({len(rows)} rows)", flush=True)
    return len(rows)


if __name__ == "__main__":
    build_sample()
