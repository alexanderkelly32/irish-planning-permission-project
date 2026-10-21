#!/usr/bin/env python3
"""
Prepare a Batch API JSONL file for units-only extraction from DevelopmentDescription.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pandas as pd

SYSTEM_PROMPT = (
    "Extract ONLY the total number of residential units from a planning development description. "
    "Return STRICT JSON with only one key: u. "
    "u must be an integer if clear, otherwise null. "
    "Count only residential units/dwellings/houses/apartments. "
    "Do not count retail/commercial units, floors, years, or reference numbers. "
    "If the text is about extension/retention/alteration to an existing dwelling with no clear total, return null."
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
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=40)
    parser.add_argument("--max-chars", type=int, default=1400)
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
