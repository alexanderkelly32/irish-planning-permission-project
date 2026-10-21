#!/usr/bin/env python3
"""Merge Batch output back into the wide CSV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import re

KEY_MAP = {
    "u": "llm_units_total",
    "uh": "llm_units_houses",
    "ua": "llm_units_apartments",
    "ud": "llm_units_duplex",
    "ut": "llm_units_townhouses",
    "ub": "llm_units_bungalows",
    "b1": "llm_bed_1",
    "b2": "llm_bed_2",
    "b3": "llm_bed_3",
    "b4": "llm_bed_4",
    "b5": "llm_bed_5",
    "p": "llm_parking_spaces",
    "cp": "llm_cycle_parking_spaces",
    "ha": "llm_site_area_ha",
    "sqm": "llm_site_area_sqm",
    "fa": "llm_floor_area_sqm",
    "os": "llm_open_space_sqm",
    "st": "llm_max_storeys",
    "ra": "llm_retail_area_sqm",
    "ca": "llm_commercial_area_sqm",
    "cr": "llm_creche_area_sqm",
    "ss": "llm_serviced_sites",
    "ph": "llm_phase",
    "hr": "llm_has_retail",
    "hc": "llm_has_commercial",
    "hm": "llm_has_mixed_use",
    "hcr": "llm_has_creche",
    "hco": "llm_has_community",
    "hh": "llm_has_hotel",
    "hi": "llm_has_industrial",
}


def _extract_response_text(obj: Dict[str, Any]) -> str | None:
    # Batch output often includes {custom_id, response:{...}, error}
    if "response" in obj and isinstance(obj["response"], dict):
        resp = obj["response"]
        if isinstance(resp, dict) and "body" in resp and isinstance(resp["body"], dict):
            resp = resp["body"]
    elif "body" in obj and isinstance(obj["body"], dict):
        resp = obj["body"]
    else:
        resp = obj

    # Responses API: resp["output"] -> list -> content -> text
    if isinstance(resp, dict) and "output" in resp:
        output = resp.get("output") or []
        if output:
            content = output[0].get("content") or []
            if content:
                return content[0].get("text")
    if isinstance(resp, dict) and "output_text" in resp:
        return resp.get("output_text")
    if isinstance(resp, dict) and "text" in resp:
        return resp.get("text")
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-jsonl", default="downloads/llm_batch_output.jsonl")
    parser.add_argument("--meta", default="downloads/llm_batch_meta.csv")
    parser.add_argument("--input-wide", default="downloads/ground_source_extracted_wide.csv")
    parser.add_argument("--output-wide", default="downloads/ground_source_extracted_wide_llm.csv")
    parser.add_argument("--include-raw", action="store_true")
    args = parser.parse_args()

    meta = pd.read_csv(args.meta)
    meta = meta[["row_index", "custom_id"]]

    rows = []
    with Path(args.output_jsonl).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            custom_id = obj.get("custom_id")
            err = obj.get("error")
            if err:
                rows.append({"custom_id": custom_id, "llm_error": json.dumps(err)})
                continue
            text = _extract_response_text(obj)
            if not text:
                rows.append({"custom_id": custom_id, "llm_error": "no_text"})
                continue
            try:
                data = json.loads(text)
            except Exception:
                # Fallback: extract any complete key/value pairs from a truncated JSON string.
                pairs = re.findall(r'"([a-z]{1,3})"\s*:\s*(null|-?\d+(?:\.\d+)?)', text)
                if not pairs:
                    rows.append({"custom_id": custom_id, "llm_error": "bad_json", "llm_raw": text if args.include_raw else None})
                    continue
                data = {k: (None if v == "null" else (float(v) if "." in v else int(v))) for k, v in pairs}
                data["_partial"] = 1

            out = {"custom_id": custom_id}
            for k, v in data.items():
                if k in KEY_MAP:
                    out[KEY_MAP[k]] = v
            if data.get("_partial") == 1:
                out["llm_error"] = "partial_json"
            if args.include_raw:
                out["llm_raw"] = text
            rows.append(out)

    llm_df = pd.DataFrame(rows)
    merged = meta.merge(llm_df, on="custom_id", how="left")

    wide = pd.read_csv(args.input_wide, low_memory=False)
    wide = wide.reset_index(drop=True)
    wide["row_index"] = wide.index

    final = wide.merge(merged, on="row_index", how="left")
    final.to_csv(args.output_wide, index=False)


if __name__ == "__main__":
    main()
