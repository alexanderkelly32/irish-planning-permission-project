#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_ge10_fixed.csv"
DEFAULT_OUTPUT = ROOT / "02_development" / "current" / "development_review_gpt5_batch_requests.jsonl"

REVIEW_FIELDS = [
    "units_total_best",
    "units_houses_best",
    "units_apartments_best",
    "units_duplex_best",
    "units_townhouses_best",
    "units_bungalows_best",
    "bed_1_best",
    "bed_2_best",
    "bed_3_best",
    "bed_4_best",
    "bed_5_best",
    "parking_spaces_best",
    "cycle_parking_spaces_best",
    "site_area_ha_best",
    "site_area_sqm_best",
    "floor_area_sqm_best",
    "open_space_sqm_best",
    "max_storeys_best",
    "retail_area_sqm_best",
    "commercial_area_sqm_best",
    "creche_area_sqm_best",
    "serviced_sites_best",
    "phase_best",
    "has_retail_best",
    "has_commercial_best",
    "has_mixed_use_best",
    "has_creche_best",
    "has_community_best",
    "has_hotel_best",
    "has_industrial_best",
]

SYSTEM_PROMPT = """You are auditing structured feature extraction from Irish planning application development descriptions.

Rules:
- Use only the text provided in DevelopmentDescription plus the basic case metadata.
- Do not infer a value unless the text supports it explicitly.
- If a field is present in the extracted data but not clearly supported by the text, mark it unsupported.
- If the text clearly supports a different value, give the corrected value.
- If the text clearly supports an obvious missing field, include it in missing_obvious_fields.
- Be strict. Silence is not evidence.
- Keep notes short and factual.

Field meanings:
- units_* fields are counts of residential units by subtype.
- bed_* fields are counts of units by bedroom count.
- *_sqm and *_ha are areas.
- max_storeys_best is the maximum residential storey count clearly supported by the text.
- has_* fields are binary flags and should be 1 only if the use is explicitly present.
- serviced_sites_best is a count of serviced sites.
- phase_best is the phase number only if explicitly stated.
- Return exactly one compact JSON object and nothing else.
- Use this exact shape:
  {
    "status": "ok|issues|unclear",
    "unsupported_fields": ["field_name"],
    "corrected_fields": [{"field": "field_name", "value": 123}],
    "missing_obvious_fields": [{"field": "field_name", "value": 123}],
    "confidence": "high|medium|low",
    "note": "short factual note"
  }
- Only use field names from this list: """ + ", ".join(REVIEW_FIELDS)


def compact_value(value: str) -> str | None:
    text = (value or "").strip()
    return text or None


def extracted_fields_payload(row: Dict[str, str]) -> Dict[str, str]:
    return {field: value for field in REVIEW_FIELDS if (value := compact_value(row.get(field, ""))) is not None}


def iter_rows(path: Path, start_row: int | None, limit: int | None) -> Iterable[tuple[int, Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for idx, row in enumerate(reader, start=2):
            if start_row is not None and idx < start_row:
                continue
            yield idx, row
            if limit is not None:
                limit -= 1
                if limit <= 0:
                    return


def build_user_prompt(row_number: int, row: Dict[str, str]) -> str:
    payload = {
        "row_number": row_number,
        "PlanningAuthority": compact_value(row.get("PlanningAuthority", "")),
        "ApplicationNumber": compact_value(row.get("ApplicationNumber", "")),
        "ApplicationType": compact_value(row.get("ApplicationType", "")),
        "Decision": compact_value(row.get("Decision", "")),
        "case_key": compact_value(row.get("case_key", "")),
        "DevelopmentDescription": compact_value(row.get("DevelopmentDescription", "")),
        "existing_extracted_fields": extracted_fields_payload(row),
    }
    return json.dumps(payload, ensure_ascii=True)


def make_request(custom_id: str, user_prompt: str, model: str) -> Dict[str, object]:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "reasoning_effort": "minimal",
            "verbosity": "low",
            "max_completion_tokens": 320,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare an OpenAI Batch JSONL file for development extraction review.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--start-row", type=int, default=None, help="1-based CSV row number including header offset, matching spreadsheet display.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row_number, row in iter_rows(args.input, args.start_row, args.limit):
            custom_id = f"development-review-row-{row_number}"
            request = make_request(custom_id, build_user_prompt(row_number, row), args.model)
            handle.write(json.dumps(request, ensure_ascii=True) + "\n")
            count += 1

    print(f"Wrote {count} batch requests to {args.output}")


if __name__ == "__main__":
    main()
