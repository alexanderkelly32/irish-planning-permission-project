#!/usr/bin/env python3
"""Theme-tag the ORIGINAL refusal decision notices of refused-arm pairs.

Steps: OCR decision PDFs -> strict evidence-bound theme tagging (DeepSeek) ->
merge into refused_arm_themes.csv keyed by original_case_key.

This is the diagnosis data for the theme-matched alteration effects: it lets us
test whether changing the lever THAT THE REFUSAL ACTUALLY CITED precedes grants
more often than refusals.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
DECISIONS = ROOT / "02_development" / "source_data" / "refused_arm_decisions"
OUT_DIR = CURRENT / "refused_arm_theme_tagging_2026-09-16"

THEMES = [
    "density_scale", "design_layout", "traffic_access", "residential_amenity",
    "flooding_drainage", "land_use_policy", "premature_or_info_gap",
    "heritage_archaeology", "ecology_trees", "water_wastewater", "other",
]

SYSTEM_PROMPT = """You are tagging Irish planning refusal decision texts with refusal-reason themes.

Strict definitions:
- heritage_archaeology: protected structure, recorded monument, architectural conservation area, archaeology, or impact on the character/setting of a NAMED heritage asset. Mere "character of the area" or "visual amenity" WITHOUT a heritage/archaeology reference is NOT heritage.
- land_use_policy: zoning or land-use designation conflict, development-plan land-use policy, unauthorised/unacceptable use class. Density/height/scale concerns are density_scale, NOT land_use_policy. Design or layout concerns are design_layout.
- traffic_access: access, parking, road safety, sightlines, turning, highway impact.
- density_scale: scale, height, density, bulk, massing, overdevelopment.
- design_layout: design quality, layout, appearance, finishes, materials.
- residential_amenity: impact on neighbouring residential amenity, overlooking, overshadowing, separation distances, noise.
- other: ONLY when a reason clearly fits no other theme.

Rules:
- Use only the text provided. Assign only themes the text clearly supports.
- For every assigned theme give a short verbatim quote from the text as evidence.
- case_primary_tags: all applicable themes, semicolon-separated (lowercase, from the list only).
- case_top_primary_tag: the single dominant theme.
- If no theme is supported, return empty strings and confidence "low".
- Return exactly one compact JSON object and nothing else:
  {"status": "ok|unclear", "case_primary_tags": "traffic_access;design_layout",
   "case_top_primary_tag": "traffic_access", "confidence": "high|medium|low",
   "evidence": {"traffic_access": "short verbatim quote"}, "note": "short factual note"}
"""


def build_request(custom_id: str, user_prompt: str, model: str = "deepseek-v4-pro") -> dict:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "max_completion_tokens": 500,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def _source_paths(source: str) -> tuple[Path, Path, Path, Path]:
    """(pairs_csv, decisions_dir, out_dir, output_csv) per arm."""
    if source == "granted_arm":
        return (
            CURRENT / "full_revision_candidate_queue.csv",
            ROOT / "02_development" / "source_data" / "granted_arm_decisions",
            CURRENT / f"granted_arm_theme_tagging_{OUT_DIR.name.split('_')[-1]}",
            CURRENT / "granted_arm_themes.csv",
        )
    return (
        CURRENT / "refused_refused_audit_merged.csv",
        ROOT / "02_development" / "source_data" / "refused_arm_decisions",
        OUT_DIR,
        CURRENT / "refused_arm_themes.csv",
    )


def ocr_decision_docs(source: str = "refused_arm") -> None:
    _, decisions_dir, _, _ = _source_paths(source)
    for council_dir in sorted(decisions_dir.iterdir()) if decisions_dir.exists() else []:
        if not council_dir.is_dir() or not list(council_dir.glob("*.pdf")):
            continue
        command = [
            sys.executable, str(ROOT / "02_development" / "scripts" / "ocr_planner_reports.py"),
            "--input-dir", str(council_dir), "--workers", "3",
        ]
        print(f"RUN: {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def prepare(source: str = "refused_arm") -> pd.DataFrame:
    pairs_csv, decisions_dir, out_dir, _output_csv = _source_paths(source)
    merged = pd.read_csv(pairs_csv, low_memory=False)
    if source == "granted_arm":
        accepted = merged[merged["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")].copy()
    else:
        accepted = merged[merged["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")].copy()
    accepted["row_number"] = accepted.index
    accepted["_decision_text"] = ""
    out_dir.mkdir(parents=True, exist_ok=True)
    requests = []
    for _, row in accepted.iterrows():
        text = ""
        council = ""
        url = str(row.get("original_source_url") or "")
        ref = url.rsplit("/", 2)[1] if "/" in url else ""
        for council_dir in sorted(decisions_dir.iterdir()) if decisions_dir.exists() else []:
            if not council_dir.is_dir():
                continue
            candidate = council_dir / f"{ref}_decision.pdf"
            if not candidate.exists():
                continue
            ocr_path = council_dir / "ocr_text" / f"{ref}_decision_ocr.txt"
            if ocr_path.exists():
                text = ocr_path.read_text(encoding="utf-8", errors="replace")
                council = council_dir.name
                break
        payload = {
            "original_case_key": str(row.get("original_case_key")),
            "council": council,
            "text": text[:14000],
        }
        requests.append(build_request(
            f"rr-theme-row-{row['row_number']}",
            json.dumps(payload, ensure_ascii=True),
        ))
        accepted.at[row["row_number"], "_decision_text"] = text
    accepted.to_csv(out_dir / "pairs.csv", index=False)
    (out_dir / "batch_requests_part01.jsonl").write_text(
        "\n".join(json.dumps(request, ensure_ascii=True) for request in requests) + "\n",
        encoding="utf-8",
    )
    summary = {"source": source, "pairs": int(len(accepted)), "requests": len(requests)}
    (out_dir / "prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return accepted


def flatten(jsonl_text: str) -> pd.DataFrame:
    rows = []
    for line in jsonl_text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", "")
        try:
            row_number = int(custom_id.rsplit("-", 1)[1]) if custom_id.startswith("rr-theme-row-") else None
        except (ValueError, IndexError):
            row_number = None
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
                "evidence": json.dumps(payload.get("evidence") or {}, ensure_ascii=True),
            })
        except Exception as exc:
            rows.append({"row_number": row_number, "api_error": str(exc)})
    return pd.DataFrame(rows)


def merge(source: str = "refused_arm") -> pd.DataFrame:
    _pairs_csv, _decisions_dir, out_dir, output_csv = _source_paths(source)
    pairs = pd.read_csv(out_dir / "pairs.csv", low_memory=False)
    output_paths = sorted(out_dir.glob("batch_output_part*.jsonl"))
    if not output_paths:
        raise FileNotFoundError("batch_output_part*.jsonl not found - run the DeepSeek runner first.")
    frames = [flatten(path.read_text(encoding="utf-8", errors="replace")) for path in output_paths]
    results = pd.concat(frames, ignore_index=True).drop_duplicates("row_number", keep="last")
    merged = pairs[["row_number", "original_case_key", "_decision_text"]].merge(results, on="row_number", how="left")
    merged = merged[merged["api_error"].fillna("").eq("")]
    merged = merged.drop(columns=["row_number", "api_error"])
    merged.to_csv(output_csv, index=False)
    tagged = merged[merged["case_primary_tags"].fillna("").astype(str).str.strip().ne("")]
    summary = {
        "source": source,
        "pairs": int(len(merged)),
        "tagged": int(len(tagged)),
        "output": str(output_csv),
    }
    (out_dir / "merge_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return merged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["ocr", "prepare", "merge"])
    parser.add_argument("--source", type=str, default="refused_arm", choices=["refused_arm", "granted_arm"])
    args = parser.parse_args()
    if args.action == "ocr":
        ocr_decision_docs(args.source)
    elif args.action == "prepare":
        prepare(args.source)
    else:
        merge(args.source)


if __name__ == "__main__":
    main()
