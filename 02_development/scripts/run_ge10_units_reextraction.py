#!/usr/bin/env python3
"""Re-extract unit totals for ALL extraction-only rows in the ground source.

The verification pack showed the original extraction is unreliable for South
Dublin, Wexford and part of Cork. This campaign re-extracts every row whose
register units are null using the strict prompt, and writes an overlay
(ge10_units_reextracted.csv) with agreement stats vs the stored values.

READ-ONLY: the ground-source CSV is never modified. Corrections are applied
separately, with provenance.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "ge10_units_reextraction_2026-09-20"
SOURCE = CURRENT / "height_storeys_extraction_2026-09-04" / "ground_source_storeys_verified.csv"

SYSTEM_PROMPT = """You are extracting the total number of residential units proposed in an Irish planning application description.

Rules:
- The total is the sum of all dwelling types stated (houses + apartments + duplexes + units + dwellings).
- Count only units the application PROPOSES to build or convert to residential use.
- If the description does not state a total or the component counts, return null - silence is not evidence.
- Return exactly one compact JSON object and nothing else:
  {"units": 42}  or  {"units": null}
"""


def build_request(custom_id: str, user_prompt: str, model: str = "deepseek-v4-pro") -> dict:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "max_completion_tokens": 200,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def prepare() -> pd.DataFrame:
    source = pd.read_csv(SOURCE, low_memory=False)
    register = pd.to_numeric(source["NumResidentialUnits"], errors="coerce")
    pool = source[register.isna()].copy()
    pool["row_number"] = pool.index
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pool.to_csv(OUT_DIR / "target_rows.csv", index=False)
    requests = []
    for _, row in pool.iterrows():
        payload = {"case_key": str(row.get("case_key")), "description": str(row.get("DevelopmentDescription") or "")[:4000]}
        requests.append(build_request(f"reunits-row-{row['row_number']}", json.dumps(payload, ensure_ascii=True)))
    (OUT_DIR / "batch_requests_part01.jsonl").write_text(
        "\n".join(json.dumps(request, ensure_ascii=True) for request in requests) + "\n",
        encoding="utf-8",
    )
    summary = {"rows": int(len(pool)), "requests": len(requests)}
    (OUT_DIR / "prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return pool


def merge() -> pd.DataFrame:
    target = pd.read_csv(OUT_DIR / "target_rows.csv", low_memory=False)
    output_paths = sorted(OUT_DIR.glob("batch_output_part*.jsonl"))
    if not output_paths:
        raise FileNotFoundError("batch_output_part*.jsonl not found - run the DeepSeek runner first.")
    rows = []
    for path in output_paths:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            custom_id = item.get("custom_id", "")
            try:
                row_number = int(custom_id.rsplit("-", 1)[1]) if custom_id.startswith("reunits-row-") else None
            except (ValueError, IndexError):
                row_number = None
            if item.get("error") or row_number is None:
                continue
            try:
                content = (item.get("response") or {}).get("body", {}).get("choices", [{}])[0].get("message", {}).get("content")
                payload = json.loads(content) if content else {}
                rows.append({"row_number": row_number, "units_reextracted": payload.get("units")})
            except Exception:
                continue
    results = pd.DataFrame(rows)
    merged = target.merge(results, on="row_number", how="left")
    merged = merged.drop(columns=["row_number"])
    merged.to_csv(CURRENT / "ge10_units_reextracted.csv", index=False)
    stored = pd.to_numeric(merged["units_total_best"], errors="coerce")
    new = pd.to_numeric(merged["units_reextracted"], errors="coerce")
    both = merged[stored.notna() & new.notna()]
    agree = ((stored - new).abs() <= new.clip(lower=0) * 0.05 + 0.5)
    summary = {
        "rows": int(len(merged)),
        "reextracted_nonnull": int(new.notna().sum()),
        "compared_with_stored": int(len(both)),
        "agreement_with_stored": round(float(agree.sum() / max(len(both), 1)), 4) if len(both) else None,
        "output": str(CURRENT / "ge10_units_reextracted.csv"),
        "note": "Overlay only - the ground source is untouched. Apply corrections only after a verification sample.",
    }
    (OUT_DIR / "merge_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return merged


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "merge"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        merge()
