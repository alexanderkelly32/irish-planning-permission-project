#!/usr/bin/env python3
"""Prepare the height/storeys extraction batch for the GE10 cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from height_storeys_extraction import build_batch_requests, select_rows

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "height_storeys_extraction_2026-09-04"
DEFAULT_INPUT = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_ge10_fixed.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--parts", type=int, default=4, help="split requests into N part files to stay under the enqueued-token limit")
    args = parser.parse_args()

    ground = pd.read_csv(args.input, low_memory=False)
    selected = select_rows(ground)
    requests = build_batch_requests(selected, model=args.model)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    parts = max(1, args.parts)
    part_size = (len(requests) + parts - 1) // parts
    manifest_parts = []
    for part_index in range(parts):
        chunk = requests[part_index * part_size : (part_index + 1) * part_size]
        part_name = f"batch_requests_part{part_index + 1:02d}.jsonl"
        (OUT_DIR / part_name).write_text(
            "\n".join(json.dumps(request, ensure_ascii=True) for request in chunk) + ("\n" if chunk else ""),
            encoding="utf-8",
        )
        manifest_parts.append({"part": part_index + 1, "file": part_name, "requests": len(chunk)})

    meta = selected[["case_key", "PlanningAuthority", "ApplicationNumber", "DevelopmentDescription", "_selected_by_storey", "_selected_by_height"]].copy()
    meta["row_number"] = selected.index
    meta.to_csv(OUT_DIR / "batch_meta.csv", index=False)

    summary = {
        "input_rows": int(len(ground)),
        "selected_rows": int(len(selected)),
        "selected_by_storey_keyword": int(selected["_selected_by_storey"].sum()),
        "selected_by_height_keyword": int(selected["_selected_by_height"].sum()),
        "requests_written": len(requests),
        "parts": manifest_parts,
        "model": args.model,
        "meta_path": str(OUT_DIR / "batch_meta.csv"),
        "next_step": "Run run_height_storeys_extraction.py to submit the parts sequentially, wait and parse.",
    }
    (OUT_DIR / "preparation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
