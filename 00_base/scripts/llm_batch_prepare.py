#!/usr/bin/env python3
"""
Prepare a Batch API JSONL file for LLM extraction from DevelopmentDescription.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pandas as pd

SYSTEM_PROMPT = (
    "Extract structured fields from a planning development description. "
    "Return STRICT JSON with ONLY these keys and no extra text: "
    "u,uh,ua,ud,ut,ub,b1,b2,b3,b4,b5,p,cp,ha,sqm,fa,os,st,ra,ca,cr,ss,ph,hr,hc,hm,hcr,hco,hh,hi. "
    "Use numbers (ints or decimals) or null. Flags are 1 or null. "
    "If unknown use null. Keep output as short as possible."
)

USER_TEMPLATE = "desc: {desc}"


def build_body(desc: str, max_output_tokens: int) -> dict:
    return {
        "model": "gpt-4.1-mini",
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": USER_TEMPLATE.format(desc=desc)}]},
        ],
        "max_output_tokens": max_output_tokens,
        "temperature": 0,
        "text": {"format": {"type": "json_object"}},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="downloads/ground_source_extracted_wide.csv")
    parser.add_argument("--output-jsonl", default="downloads/llm_batch_input.jsonl")
    parser.add_argument("--meta", default="downloads/llm_batch_meta.csv")
    parser.add_argument("--min-units", type=int, default=10)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=220)
    parser.add_argument("--max-chars", type=int, default=2000)
    parser.add_argument(
        "--only-missing-units",
        action="store_true",
        help="Only include rows where units_total_best is missing.",
    )
    parser.add_argument(
        "--authority-filter",
        default="",
        help="Comma-separated PlanningAuthority names to include.",
    )
    parser.add_argument(
        "--require-unit-keyword",
        action="store_true",
        help="Only include rows whose description mentions unit keywords.",
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output_jsonl)
    meta_path = Path(args.meta)

    df = pd.read_csv(in_path, low_memory=False)
    if "units_total_final" in df.columns and args.min_units is not None:
        df = df[df["units_total_final"].fillna(0) >= args.min_units]
    if args.only_missing_units and "units_total_best" in df.columns:
        df = df[df["units_total_best"].isna()]
    if args.authority_filter:
        allowed = {x.strip() for x in args.authority_filter.split(",") if x.strip()}
        if allowed:
            df = df[df["PlanningAuthority"].isin(allowed)]
    if args.require_unit_keyword:
        df = df[
            df["DevelopmentDescription"]
            .fillna("")
            .str.contains(
                r"\b(?:dwelling|dwellings|unit|units|apartment|apartments|house|houses|residential)\b",
                case=False,
                regex=True,
            )
        ]

    if args.max_rows:
        df = df.head(args.max_rows)

    df = df.reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f_out, meta_path.open("w", newline="", encoding="utf-8") as f_meta:
        meta_writer = csv.DictWriter(
            f_meta,
            fieldnames=[
                "row_index",
                "custom_id",
                "PlanningAuthority",
                "ApplicationNumber",
                "desc_chars",
            ],
        )
        meta_writer.writeheader()

        for i, row in df.iterrows():
            desc = str(row.get("DevelopmentDescription") or "").strip()
            if not desc:
                continue
            if args.max_chars and len(desc) > args.max_chars:
                desc = desc[: args.max_chars]

            pa = str(row.get("PlanningAuthority") or "").replace("|", "/")
            app = str(row.get("ApplicationNumber") or "").replace("|", "/")
            custom_id = f"{pa}|{app}|{i}"

            request = {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/v1/responses",
                "body": build_body(desc, args.max_output_tokens),
            }
            f_out.write(json.dumps(request, ensure_ascii=True) + "\n")

            meta_writer.writerow(
                {
                    "row_index": i,
                    "custom_id": custom_id,
                    "PlanningAuthority": pa,
                    "ApplicationNumber": app,
                    "desc_chars": len(desc),
                }
            )


if __name__ == "__main__":
    main()
