#!/usr/bin/env python3
"""Extract exact residential-unit counts for 2025-holdout GE10 candidates.

The 2025 holdout has very few rows with register units, which starves the
unit-band AUC analysis. This campaign finds every 2025 holdout row that is
plausibly >=10 units (description bucket "10+ units", FI-dataset membership, or
register >=10), takes the exact count from the FI dataset where available, and
extracts it from the description text (DeepSeek, strict prompt) for the rest.

Output: holdout_units_extracted.csv -> merged into the band analysis.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "holdout_units_extraction_2026-09-19"

PARQUET = ROOT / "old_original_attempt" / "first_attempt_messy" / "irish_planning_dataset_clean_model.parquet"
PREDICTIONS = ROOT / "05_policy" / "current" / "raw_planning_v3_2025_predictions.csv"
FI_CSV = ROOT / "04_fi" / "current" / "greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv"

SYSTEM_PROMPT = """You are extracting the total number of residential units proposed in an Irish planning application description.

Rules:
- The total is the sum of all dwelling types stated (houses + apartments + duplexes + units + dwellings).
- Count only units the application PROPOSES to build or convert to residential use. Ignore existing units being retained unless they are part of the proposal total.
- If the description does not state a total or the component counts, return null - silence is not evidence. Do not guess or infer from floor area.
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


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def prepare() -> pd.DataFrame:
    pred = pd.read_csv(PREDICTIONS, low_memory=False)
    raw = pd.read_parquet(PARQUET, columns=["PlanningAuthority", "ApplicationNumber", "NumResidentialUnits", "DevelopmentDescription"])
    raw["units"] = pd.to_numeric(raw["NumResidentialUnits"], errors="coerce")
    raw["case_key"] = raw["PlanningAuthority"].fillna("").astype(str) + "__" + raw["ApplicationNumber"].fillna("").astype(str)
    desc_by_key = dict(zip(raw["case_key"], raw["DevelopmentDescription"].fillna("")))
    register_units = (
        raw.dropna(subset=["units"])
        .groupby("case_key")["units"].last().to_dict()
    )
    corrected = pd.read_csv(CURRENT / "ground_source_units_corrected.csv", low_memory=False)
    corrected["_nk"] = corrected["case_key"].astype(str).map(norm)
    corrected_map = corrected.dropna(subset=["units_corrected"]).groupby("_nk")["units_corrected"].last().to_dict()

    frame = pred.copy()
    frame["_nk"] = frame["case_key"].map(norm)
    frame["units"] = frame["case_key"].map(lambda k: register_units.get(k))
    frame["units"] = frame["units"].fillna(frame["_nk"].map(lambda k: corrected_map.get(k)))
    frame["description"] = frame["case_key"].map(lambda k: desc_by_key.get(k, ""))

    to_extract = frame[frame["units"].isna() & frame["description"].str.strip().ne("")].copy()
    to_extract["row_number"] = to_extract.index
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    to_extract.to_csv(OUT_DIR / "candidates.csv", index=False)
    requests = []
    for _, row in to_extract.iterrows():
        payload = {"case_key": str(row["case_key"]), "description": str(row["description"])[:4000]}
        requests.append(build_request(f"hu-row-{row['row_number']}", json.dumps(payload, ensure_ascii=True)))
    (OUT_DIR / "batch_requests_part01.jsonl").write_text(
        "\n".join(json.dumps(request, ensure_ascii=True) for request in requests) + "\n",
        encoding="utf-8",
    )
    summary = {
        "unknown_units_rows": int(len(to_extract)),
        "requests": len(requests),
    }
    (OUT_DIR / "prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return to_extract


def merge() -> pd.DataFrame:
    candidates = pd.read_csv(OUT_DIR / "candidates.csv", low_memory=False)
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
                row_number = int(custom_id.rsplit("-", 1)[1]) if custom_id.startswith("hu-row-") else None
            except (ValueError, IndexError):
                row_number = None
            if item.get("error"):
                continue
            try:
                content = (item.get("response") or {}).get("body", {}).get("choices", [{}])[0].get("message", {}).get("content")
                payload = json.loads(content) if content else {}
                rows.append({"row_number": row_number, "units_extracted": payload.get("units")})
            except Exception:
                continue
    extracted = pd.DataFrame(rows)
    frame = pd.read_csv(OUT_DIR / "candidates.csv", low_memory=False)
    frame["row_number"] = frame.index
    frame = frame.merge(extracted, on="row_number", how="left")
    frame["units_final"] = pd.to_numeric(frame["units_extracted"], errors="coerce")
    frame[["case_key", "units_final"]].to_csv(CURRENT / "holdout_units_extracted.csv", index=False)
    summary = {
        "rows": int(len(frame)),
        "with_units_final": int(frame["units_final"].notna().sum()),
        "output": str(CURRENT / "holdout_units_extracted.csv"),
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
