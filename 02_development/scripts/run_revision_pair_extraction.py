#!/usr/bin/env python3
"""Extract structured fields from BOTH sides of audited revision pairs.

Every accepted refused->granted pair in the queue gets one request containing
the original and revised descriptions; the model returns structured fields for
each side ("silence is not evidence"). Deltas are computed where both sides are
stated. This grows the structured-delta pairs that feed the blind backtest,
lever contrasts and the recommendation evidence.

Usage:
  python run_revision_pair_extraction.py prepare
  python run_deepseek_extraction.py --out-dir 02_development/current/revision_pair_extraction_2026-09-13 --model deepseek-v4-pro
  python run_revision_pair_extraction.py merge
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
QUEUE = CURRENT / "full_revision_candidate_queue.csv"
OUT_DIR = CURRENT / "revision_pair_extraction_2026-09-13"

PAIR_FIELDS = [
    "max_storeys", "parking_spaces", "cycle_parking_spaces",
    "open_space_sqm", "max_height_m", "vehicular_access_points",
]

SYSTEM_PROMPT = """You are extracting structured building details from TWO Irish planning application descriptions: the original refused proposal and its revised resubmission.

Rules:
- Extract only values explicitly stated in each text. Silence is not evidence; return null for anything not stated.
- max_storeys: maximum number of storeys explicitly stated (digits or words). Use 1.5 for "storey and a half"; for ranges return the maximum.
- parking_spaces / cycle_parking_spaces: counts of proposed car / cycle parking spaces explicitly stated.
- open_space_sqm: proposed open-space area in square metres explicitly stated (private or communal, whichever is stated; convert hectares to sqm).
- max_height_m: maximum building height in metres explicitly stated. Do NOT convert storeys to metres.
- vehicular_access_points: number of proposed vehicle entrances/access points explicitly stated.
- Return exactly one compact JSON object and nothing else:
  {"status": "ok|unclear",
   "original": {"max_storeys": 5, "parking_spaces": 40, "cycle_parking_spaces": null,
                "open_space_sqm": null, "max_height_m": null, "vehicular_access_points": 1},
   "revised":  {"max_storeys": 4, "parking_spaces": 44, "cycle_parking_spaces": null,
                "open_space_sqm": null, "max_height_m": null, "vehicular_access_points": 1},
   "confidence": "high|medium|low", "note": "short factual note"}
"""


def build_request(custom_id: str, user_prompt: str, model: str = "deepseek-v4-pro") -> dict:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "max_completion_tokens": 700,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def accepted_pairs() -> pd.DataFrame:
    queue = pd.read_csv(QUEUE, low_memory=False)
    accepted = queue[queue["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")].copy()
    return accepted


def prepare() -> pd.DataFrame:
    pairs = accepted_pairs()
    pairs["row_number"] = pairs.index
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(OUT_DIR / "pairs.csv", index=False)
    requests = []
    for _, row in pairs.iterrows():
        payload = {
            "original_case_key": str(row.get("original_case_key")),
            "revised_case_key": str(row.get("revised_case_key")),
            "original": str(row.get("original_description") or "")[:6000],
            "revised": str(row.get("revised_description") or "")[:6000],
        }
        requests.append(build_request(
            f"pair-extract-row-{row['row_number']}",
            json.dumps(payload, ensure_ascii=True),
        ))
    (OUT_DIR / "batch_requests_part01.jsonl").write_text(
        "\n".join(json.dumps(request, ensure_ascii=True) for request in requests) + "\n",
        encoding="utf-8",
    )
    summary = {"accepted_pairs": int(len(pairs)), "requests": len(requests)}
    (OUT_DIR / "prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return pairs


def flatten(jsonl_text: str) -> pd.DataFrame:
    rows = []
    for line in jsonl_text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", "")
        try:
            row_number = int(custom_id.rsplit("-", 1)[1]) if custom_id.startswith("pair-extract-row-") else None
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
            original = payload.get("original") or {}
            revised = payload.get("revised") or {}
            row = {"row_number": row_number, "api_error": "", "confidence": payload.get("confidence", "")}
            for field in PAIR_FIELDS:
                row[f"original_{field}"] = original.get(field)
                row[f"revised_{field}"] = revised.get(field)
            rows.append(row)
        except Exception as exc:
            rows.append({"row_number": row_number, "api_error": str(exc)})
    return pd.DataFrame(rows)


def merge() -> pd.DataFrame:
    pairs = pd.read_csv(OUT_DIR / "pairs.csv", low_memory=False)
    output_paths = sorted(OUT_DIR.glob("batch_output_part*.jsonl"))
    if not output_paths:
        raise FileNotFoundError("batch_output_part*.jsonl not found - run the DeepSeek runner first.")
    frames = [flatten(path.read_text(encoding="utf-8", errors="replace")) for path in output_paths]
    results = pd.concat(frames, ignore_index=True)
    results = results.drop_duplicates("row_number", keep="last")
    merged = pairs[["row_number", "original_case_key", "revised_case_key", "planning_authority"]].merge(
        results, on="row_number", how="left"
    )
    merged = merged[merged["api_error"].fillna("").eq("")]
    merged = merged.drop(columns=["row_number", "api_error"])

    delta_rows = []
    for _, row in merged.iterrows():
        record = {
            "original_case_key": row["original_case_key"],
            "revised_case_key": row["revised_case_key"],
        }
        for field in PAIR_FIELDS:
            original = pd.to_numeric(row.get(f"original_{field}"), errors="coerce")
            revised = pd.to_numeric(row.get(f"revised_{field}"), errors="coerce")
            if pd.isna(original) or pd.isna(revised):
                record[f"{field}_delta"] = None
                record[f"original_{field}"] = original if not pd.isna(original) else None
                record[f"revised_{field}"] = revised if not pd.isna(revised) else None
            else:
                record[f"original_{field}"] = float(original)
                record[f"revised_{field}"] = float(revised)
                record[f"{field}_delta"] = float(revised - original)
        delta_rows.append(record)
    frame = pd.DataFrame(delta_rows)
    frame.to_csv(OUT_DIR / "revision_pair_structured_extractions.csv", index=False)
    deltas = frame.dropna(subset=[f"{field}_delta" for field in PAIR_FIELDS], how="all")
    summary = {
        "pairs": int(len(frame)),
        "pairs_with_any_delta": int(len(deltas)),
        "per_field_delta_counts": {
            field: int(frame[f"{field}_delta"].notna().sum()) for field in PAIR_FIELDS
        },
        "output": str(OUT_DIR / "revision_pair_structured_extractions.csv"),
    }
    (OUT_DIR / "merge_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return frame


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "merge"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        merge()
