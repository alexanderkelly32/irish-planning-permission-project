#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


ALLOWED_CATS = {
    "traffic_access",
    "flooding_drainage",
    "water_wastewater",
    "design_layout",
    "density_scale",
    "residential_amenity",
    "land_use_policy",
    "heritage_archaeology",
    "ecology_trees",
    "premature_or_info_gap",
    "other",
}


def _extract_response_text(obj: Dict[str, Any]) -> str | None:
    resp = obj.get("response", {})
    if isinstance(resp, dict) and "body" in resp and isinstance(resp["body"], dict):
        resp = resp["body"]
    output = resp.get("output") if isinstance(resp, dict) else None
    if output and isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for chunk in content:
                if not isinstance(chunk, dict):
                    continue
                text = chunk.get("text")
                if isinstance(text, str):
                    return text
    return None


def _parse_json(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start : end + 1])
        raise


def _normalize_reasons(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = data.get("reasons", [])
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("t", "")).strip()
        if not text:
            continue
        cats = item.get("cats", [])
        if not isinstance(cats, list):
            cats = []
        cats = [str(c).strip() for c in cats if str(c).strip() in ALLOWED_CATS]
        if not cats:
            cats = ["other"]
        out.append({"t": text, "cats": cats})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-output-jsonl", default="extraction_of_site_data/_llm_batch/llm_refusal_batch_output.jsonl")
    parser.add_argument("--base-cases", default="extraction_of_site_data/refusal_reasons_cases_final.csv")
    parser.add_argument("--base-long", default="extraction_of_site_data/refusal_reasons_long_final.csv")
    parser.add_argument("--source-wide", default="extraction_of_site_data/ground_source_extracted_final_wide.csv")
    parser.add_argument("--out-cases", default="extraction_of_site_data/refusal_reasons_cases_llm.csv")
    parser.add_argument("--out-long", default="extraction_of_site_data/refusal_reasons_long_llm.csv")
    parser.add_argument("--out-merged", default="extraction_of_site_data/ground_source_extracted_final_wide_with_refusal_reasons_llm.csv")
    args = parser.parse_args()

    base_cases = pd.read_csv(args.base_cases)
    base_long = pd.read_csv(args.base_long)

    llm_cases_rows = []
    llm_long_rows = []

    with Path(args.batch_output_jsonl).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            case_key = str(obj.get("custom_id", "")).strip().lower()
            if not case_key:
                continue
            text = _extract_response_text(obj)
            if not text:
                continue
            try:
                data = _parse_json(text)
            except Exception:
                continue
            reasons = _normalize_reasons(data)
            reason_count = len(reasons)
            reason_join = " || ".join(r["t"] for r in reasons) if reasons else ""
            primary_tags = sorted({c for r in reasons for c in r["cats"]})

            llm_cases_rows.append(
                {
                    "case_key": case_key,
                    "llm_reason_count": reason_count,
                    "llm_reasons_joined": reason_join,
                    "llm_case_primary_tags": ";".join(primary_tags),
                    "llm_case_top_primary_tag": (primary_tags[0] if primary_tags else ""),
                }
            )

            for i, r in enumerate(reasons, start=1):
                llm_long_rows.append(
                    {
                        "case_key": case_key,
                        "reason_index": i,
                        "reason_text": r["t"],
                        "primary_tag": r["cats"][0],
                        "all_tags": ";".join(r["cats"]),
                        "extraction_source": "llm",
                        "extraction_method": "llm_batch",
                    }
                )

    llm_cases = pd.DataFrame(llm_cases_rows).drop_duplicates(subset=["case_key"], keep="last")
    llm_long = pd.DataFrame(llm_long_rows)
    if not llm_long.empty:
        llm_long = llm_long.drop_duplicates(subset=["case_key", "reason_text"])

    merged_cases = base_cases.merge(llm_cases, on="case_key", how="left")
    base_rc = pd.to_numeric(merged_cases.get("reason_count", 0), errors="coerce").fillna(0)
    llm_rc = pd.to_numeric(merged_cases.get("llm_reason_count", 0), errors="coerce").fillna(0)
    use_llm = llm_rc > base_rc

    merged_cases["reason_count"] = merged_cases["reason_count"].where(~use_llm, merged_cases["llm_reason_count"])
    merged_cases["reasons_joined"] = merged_cases["reasons_joined"].where(~use_llm, merged_cases["llm_reasons_joined"])
    merged_cases["case_primary_tags"] = merged_cases["case_primary_tags"].where(~use_llm, merged_cases["llm_case_primary_tags"])
    merged_cases["case_top_primary_tag"] = merged_cases["case_top_primary_tag"].where(~use_llm, merged_cases["llm_case_top_primary_tag"])
    merged_cases["extraction_source"] = merged_cases["extraction_source"].where(~use_llm, "llm")
    merged_cases["extraction_method"] = merged_cases["extraction_method"].where(~use_llm, "llm_batch")

    merged_cases = merged_cases.drop(
        columns=[
            "llm_reason_count",
            "llm_reasons_joined",
            "llm_case_primary_tags",
            "llm_case_top_primary_tag",
        ],
        errors="ignore",
    )

    keep_llm_keys = set(merged_cases.loc[use_llm, "case_key"].dropna().astype(str).str.lower().tolist())
    drop_base_idx = []
    if keep_llm_keys and not base_long.empty:
        ck = base_long["case_key"].fillna("").astype(str).str.lower()
        drop_base_idx = base_long.index[ck.isin(keep_llm_keys)].tolist()
    merged_long = base_long.drop(index=drop_base_idx, errors="ignore")
    if not llm_long.empty:
        merged_long = pd.concat([merged_long, llm_long], ignore_index=True)
    merged_long = merged_long.drop_duplicates(subset=["case_key", "reason_text"], keep="last")

    merged_cases.to_csv(args.out_cases, index=False)
    merged_long.to_csv(args.out_long, index=False)

    source_wide = pd.read_csv(args.source_wide, low_memory=False)
    out = source_wide.copy()
    council = out["PlanningAuthority"].fillna("").astype(str).str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    app = out["ApplicationNumber"].fillna("").astype(str).str.replace(r"[^A-Za-z0-9._-]+", "_", regex=True)
    out["case_key"] = (council + "_" + app).str.lower()
    join_cols = ["case_key", "reason_count", "reasons_joined", "case_primary_tags", "case_top_primary_tag"]
    stale_cols = [c for c in out.columns if c in join_cols or c.endswith("_x") or c.endswith("_y")]
    out = out.drop(columns=[c for c in stale_cols if c != "case_key"], errors="ignore")
    out = out.merge(merged_cases[join_cols], on="case_key", how="left")
    out.to_csv(args.out_merged, index=False)

    print(f"Wrote: {args.out_cases}")
    print(f"Wrote: {args.out_long}")
    print(f"Wrote: {args.out_merged}")
    print(f"LLM upgraded cases: {int(use_llm.sum())}")


if __name__ == "__main__":
    main()
