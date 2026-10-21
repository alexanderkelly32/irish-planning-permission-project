#!/usr/bin/env python3
"""Retag the weak refusal themes (heritage_archaeology, land_use_policy, other)
with a stricter evidence-bound prompt, and prepare a verification pack.

Usage:
  python 03_refusal/scripts/retag_weak_themes.py prepare
  python 02_development/scripts/run_deepseek_extraction.py --out-dir 03_refusal/current/theme_retag_2026-09-10 --model deepseek-v4-pro
  python 03_refusal/scripts/retag_weak_themes.py merge
  python 03_refusal/scripts/build_theme_retag_verification_pack.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REFUSAL_MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
OUT_DIR = ROOT / "03_refusal" / "current" / "theme_retag_2026-09-10"

THEMES = [
    "density_scale", "design_layout", "traffic_access", "residential_amenity",
    "flooding_drainage", "land_use_policy", "premature_or_info_gap",
    "heritage_archaeology", "ecology_trees", "water_wastewater", "other",
]

WEAK_THEMES = {"heritage_archaeology", "land_use_policy", "other"}

SYSTEM_PROMPT = """You are re-tagging Irish planning refusal decision texts with refusal-reason themes.

You previously over-tagged three themes. Apply these strict definitions:

- heritage_archaeology: the text refers to a protected structure, recorded monument,
  architectural conservation area, archaeology, or impact on the character/setting of a
  named heritage asset. If the text only says "character of the area", "visual amenity"
  or "adjacent dwellings" WITHOUT a heritage/archaeology reference, it is NOT heritage.
- land_use_policy: the text cites a zoning or land-use designation conflict, a
  development-plan land-use policy, an unauthorised/unacceptable use class, or "contrary
  to the zoning/proper planning and sustainable development" in a land-use sense.
  Density, height, scale or massing concerns are density_scale, NOT land_use_policy.
  Design or layout concerns are design_layout, NOT land_use_policy.
- other: ONLY when a refusal reason clearly does not fit any other theme (for example
  purely legal or administrative grounds). If it fits any other theme, do not use other.

Rules:
- Use only the text provided. Assign only themes the text clearly supports.
- For every theme you assign, give a short verbatim quote from the text as evidence.
- Themes (semicolon-separated, lowercase, from this list only):
  density_scale, design_layout, traffic_access, residential_amenity,
  flooding_drainage, land_use_policy, premature_or_info_gap,
  heritage_archaeology, ecology_trees, water_wastewater, other
- case_primary_tags: all applicable themes, semicolon-separated.
- case_top_primary_tag: the single dominant theme.
- evidence: object mapping each assigned theme to a short verbatim quote (max 80 chars).
- If no theme is supported, return empty strings, empty evidence and confidence "low".
- Return exactly one compact JSON object and nothing else:
  {"status": "ok|unclear", "case_primary_tags": "design_layout;residential_amenity",
   "case_top_primary_tag": "design_layout", "confidence": "high|medium|low",
   "evidence": {"design_layout": "short verbatim quote"},
   "note": "short factual note"}
"""


def build_request(custom_id: str, user_prompt: str, model: str = "deepseek-v4-pro", max_completion_tokens: int = 500) -> dict:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "max_completion_tokens": max_completion_tokens,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def select_weak_theme_cases(master: pd.DataFrame) -> pd.DataFrame:
    tags = master["case_primary_tags"].fillna("").astype(str)
    has_weak = tags.apply(lambda value: bool(WEAK_THEMES & {
        part.strip() for part in value.split(";") if part.strip()
    }))
    with_text = master["reasons_joined"].fillna("").astype(str).str.strip().ne("")
    return master[has_weak & with_text].copy()


def prepare() -> pd.DataFrame:
    master = pd.read_csv(REFUSAL_MASTER, low_memory=False)
    selected = select_weak_theme_cases(master)
    selected["row_number"] = selected.index
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    selected.to_csv(OUT_DIR / "retag_cases.csv", index=False)
    requests = []
    for _, row in selected.iterrows():
        payload = {
            "case_key": str(row.get("case_key")),
            "council": str(row.get("council") or ""),
            "application_number": str(row.get("application_number") or ""),
            "previous_tags": str(row.get("case_primary_tags") or ""),
            "text": str(row.get("reasons_joined") or "")[:14000],
        }
        requests.append(build_request(
            f"retag-row-{row['row_number']}",
            json.dumps(payload, ensure_ascii=True),
        ))
    (OUT_DIR / "batch_requests_part01.jsonl").write_text(
        "\n".join(json.dumps(request, ensure_ascii=True) for request in requests) + "\n",
        encoding="utf-8",
    )
    summary = {"weak_theme_cases": int(len(selected)), "requests": len(requests)}
    (OUT_DIR / "prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return selected


def flatten(jsonl_text: str) -> pd.DataFrame:
    rows = []
    for line in jsonl_text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", "")
        row_number = int(custom_id.rsplit("-", 1)[1]) if custom_id.startswith("retag-row-") else None
        error = item.get("error")
        if error:
            rows.append({"row_number": row_number, "api_error": json.dumps(error, ensure_ascii=True)})
            continue
        try:
            body = (item.get("response") or {}).get("body") or {}
            choices = body.get("choices") or []
            content = (choices[0].get("message") or {}).get("content")
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            payload = json.loads(content)
            rows.append({
                "row_number": row_number,
                "api_error": "",
                "case_primary_tags": payload.get("case_primary_tags", ""),
                "case_top_primary_tag": payload.get("case_top_primary_tag", ""),
                "confidence": payload.get("confidence", ""),
                "evidence": json.dumps(payload.get("evidence") or {}, ensure_ascii=True),
                "note": payload.get("note", ""),
            })
        except Exception as exc:
            rows.append({"row_number": row_number, "api_error": str(exc)})
    return pd.DataFrame(rows)


def patch_failed() -> pd.DataFrame:
    """Rebuild requests for rows whose responses failed to parse (e.g. truncated
    JSON) with a larger completion-token budget, into the next part file."""
    failed_rows: dict[int, str] = {}
    for output_path in sorted(OUT_DIR.glob("batch_output_part*.jsonl")):
        frame = flatten(output_path.read_text(encoding="utf-8", errors="replace"))
        for _, row in frame[frame["api_error"].ne("")].iterrows():
            if row["row_number"] is not None:
                failed_rows[int(row["row_number"])] = str(row["api_error"])
    if not failed_rows:
        print(json.dumps({"patch_requests": 0}))
        return pd.DataFrame()
    cases = pd.read_csv(OUT_DIR / "retag_cases.csv", low_memory=False)
    cases = cases[cases["row_number"].isin(failed_rows.keys())].copy()
    part_number = len(list(OUT_DIR.glob("batch_requests_part*.jsonl"))) + 1
    requests = []
    for _, row in cases.iterrows():
        payload = {
            "case_key": str(row.get("case_key")),
            "council": str(row.get("council") or ""),
            "application_number": str(row.get("application_number") or ""),
            "previous_tags": str(row.get("case_primary_tags") or ""),
            "text": str(row.get("reasons_joined") or "")[:14000],
        }
        requests.append(build_request(
            f"retag-row-{row['row_number']}",
            json.dumps(payload, ensure_ascii=True),
            max_completion_tokens=1000,
        ))
    (OUT_DIR / f"batch_requests_part{part_number:02d}.jsonl").write_text(
        "\n".join(json.dumps(request, ensure_ascii=True) for request in requests) + "\n",
        encoding="utf-8",
    )
    summary = {
        "patch_requests": len(requests),
        "part": part_number,
        "failed_rows": sorted(failed_rows.keys()),
        "note": "Run the DeepSeek runner with --parts {part} then merge again.".format(part=part_number),
    }
    (OUT_DIR / "patch_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return cases


def merge() -> pd.DataFrame:
    master = pd.read_csv(REFUSAL_MASTER, low_memory=False)
    output_paths = sorted(OUT_DIR.glob("batch_output_part*.jsonl"))
    if not output_paths:
        raise FileNotFoundError("batch_output_part*.jsonl not found - run the DeepSeek runner first.")
    frames = []
    for output_path in output_paths:
        frames.append(flatten(output_path.read_text(encoding="utf-8", errors="replace")))
    results = pd.concat(frames, ignore_index=True)
    results = results.drop_duplicates("row_number", keep="last")
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
        merged.at[index, "tag_extraction_model"] = "deepseek-v4-pro-retag"
        merged.at[index, "tag_confidence"] = str(result.get("confidence") or "")
        merged.at[index, "tag_evidence"] = str(result.get("evidence") or "")
    target = OUT_DIR / "refusal_reasons_cases_master_retagged.csv"
    merged.to_csv(target, index=False)
    summary = {
        "rows": int(len(merged)),
        "retagged_rows": int(results["api_error"].eq("").sum()) if not results.empty else 0,
        "errors": int(results["api_error"].ne("").sum()) if not results.empty else 0,
        "output": str(target),
        "note": "Master copy with weak-theme rows replaced by the stricter retag; the canonical master is untouched.",
    }
    (OUT_DIR / "merge_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return merged


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "merge", "patch-failed"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "patch-failed":
        patch_failed()
    else:
        merge()
