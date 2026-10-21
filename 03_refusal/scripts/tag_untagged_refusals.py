#!/usr/bin/env python3
"""Tag the untagged refusal cases with themes using DeepSeek (coverage scale-up)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REFUSAL_MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
OUT_DIR = ROOT / "03_refusal" / "current" / "theme_tagging_2026-09-09"

THEMES = [
    "density_scale", "design_layout", "traffic_access", "residential_amenity",
    "flooding_drainage", "land_use_policy", "premature_or_info_gap",
    "heritage_archaeology", "ecology_trees", "water_wastewater", "other",
]

SYSTEM_PROMPT = """You are tagging Irish planning refusal decision texts with refusal-reason themes.

Rules:
- Use only the text provided. Assign only themes the text clearly supports.
- Themes (semicolon-separated, lowercase, from this list only):
  density_scale, design_layout, traffic_access, residential_amenity,
  flooding_drainage, land_use_policy, premature_or_info_gap,
  heritage_archaeology, ecology_trees, water_wastewater, other
- case_primary_tags: all applicable themes, semicolon-separated.
- case_top_primary_tag: the single dominant theme.
- If no theme is supported, return empty strings and confidence "low".
- Return exactly one compact JSON object and nothing else:
  {"status": "ok|unclear", "case_primary_tags": "design_layout;residential_amenity",
   "case_top_primary_tag": "design_layout", "confidence": "high|medium|low",
   "note": "short factual note"}
"""


def build_request(custom_id: str, user_prompt: str, model: str = "deepseek-v4-pro") -> dict:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "max_completion_tokens": 300,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def prepare() -> pd.DataFrame:
    master = pd.read_csv(REFUSAL_MASTER, low_memory=False)
    untagged = master[
        master["case_primary_tags"].fillna("").astype(str).str.strip().eq("")
        & pd.to_numeric(master["reason_count"], errors="coerce").fillna(0).gt(0)
    ].copy()
    untagged["row_number"] = untagged.index
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    untagged.to_csv(OUT_DIR / "untagged_cases.csv", index=False)
    requests = []
    for _, row in untagged.iterrows():
        payload = {
            "case_key": str(row.get("case_key")),
            "council": str(row.get("council") or ""),
            "application_number": str(row.get("application_number") or ""),
            "text": str(row.get("reasons_joined") or "")[:14000],
        }
        requests.append(build_request(
            f"refusal-tag-row-{row['row_number']}",
            json.dumps(payload, ensure_ascii=True),
        ))
    (OUT_DIR / "tag_requests_part01.jsonl").write_text(
        "\n".join(json.dumps(request, ensure_ascii=True) for request in requests) + "\n",
        encoding="utf-8",
    )
    summary = {"untagged_cases": int(len(untagged)), "requests": len(requests)}
    (OUT_DIR / "prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return untagged


def flatten(jsonl_text: str) -> pd.DataFrame:
    rows = []
    for line in jsonl_text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", "")
        row_number = int(custom_id.rsplit("-", 1)[1]) if custom_id.startswith("refusal-tag-row-") else None
        error = item.get("error")
        if error:
            rows.append({"row_number": row_number, "api_error": json.dumps(error, ensure_ascii=True)})
            continue
        try:
            body = (item.get("response") or {}).get("body") or {}
            choices = body.get("choices") or []
            content = (choices[0].get("message") or {}).get("content")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
            payload = json.loads(content)
            rows.append({
                "row_number": row_number,
                "api_error": "",
                "case_primary_tags": payload.get("case_primary_tags", ""),
                "case_top_primary_tag": payload.get("case_top_primary_tag", ""),
                "confidence": payload.get("confidence", ""),
                "note": payload.get("note", ""),
            })
        except Exception as exc:
            rows.append({"row_number": row_number, "api_error": str(exc)})
    return pd.DataFrame(rows)


def merge(master: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    merged = master.copy()
    merged["case_primary_tags"] = merged["case_primary_tags"].fillna("")
    merged["case_top_primary_tag"] = merged["case_top_primary_tag"].fillna("")
    for _, result in results.iterrows():
        if result.get("api_error"):
            continue
        index = result["row_number"]
        if index not in merged.index:
            continue
        merged.at[index, "case_primary_tags"] = str(result.get("case_primary_tags") or "")
        merged.at[index, "case_top_primary_tag"] = str(result.get("case_top_primary_tag") or "")
        merged.at[index, "tag_extraction_model"] = "deepseek-v4-pro"
        merged.at[index, "tag_confidence"] = str(result.get("confidence") or "")
    return merged


if __name__ == "__main__":
    prepare()
