#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict

from openai_batch_utils import make_client


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BATCH_JOB = ROOT / "02_development" / "current" / "development_review_gpt5_batch_job.json"
DEFAULT_OUTPUT_JSONL = ROOT / "02_development" / "current" / "development_review_gpt5_batch_output.jsonl"
DEFAULT_OUTPUT_CSV = ROOT / "02_development" / "current" / "development_review_gpt5_results.csv"

RESULT_FIELDS = [
    "row_number",
    "custom_id",
    "status",
    "confidence",
    "unsupported_fields",
    "corrected_fields",
    "missing_obvious_fields",
    "note",
    "api_error",
]


def extract_message_content(body: Dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("No choices in batch response body.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        if text_parts:
            return "".join(text_parts)
    raise ValueError("Unable to extract message content from batch response body.")


def parse_payload_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    body = ((item.get("response") or {}).get("body")) or {}
    raw_content = extract_message_content(body)
    if not raw_content or not raw_content.strip():
        raise ValueError("Empty message content.")
    return json.loads(raw_content)


def row_number_from_custom_id(custom_id: str) -> int | None:
    marker = "development-review-row-"
    if custom_id.startswith(marker):
        try:
            return int(custom_id[len(marker) :])
        except ValueError:
            return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and flatten development review batch results.")
    parser.add_argument("--batch-job", type=Path, default=DEFAULT_BATCH_JOB)
    parser.add_argument("--output-jsonl", type=Path, default=DEFAULT_OUTPUT_JSONL)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    args = parser.parse_args()

    batch_job = json.loads(args.batch_job.read_text(encoding="utf-8"))
    batch_id = batch_job["id"]

    client = make_client()
    batch = client.batches.retrieve(batch_id)

    if not batch.output_file_id:
        raise RuntimeError(f"Batch {batch.id} is not complete yet. Current status: {batch.status}")

    file_text = client.files.content(batch.output_file_id).text
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.output_jsonl.write_text(file_text, encoding="utf-8")

    rows = []
    for line in file_text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", "")
        row_number = row_number_from_custom_id(custom_id)
        error = item.get("error")

        if error:
            rows.append(
                {
                    "row_number": row_number,
                    "custom_id": custom_id,
                    "status": "",
                    "confidence": "",
                    "unsupported_fields": "",
                    "corrected_fields": "",
                    "missing_obvious_fields": "",
                    "note": "",
                    "api_error": json.dumps(error, ensure_ascii=True),
                }
            )
            continue

        try:
            payload = parse_payload_from_item(item)
            rows.append(
                {
                    "row_number": row_number,
                    "custom_id": custom_id,
                    "status": payload.get("status", ""),
                    "confidence": payload.get("confidence", ""),
                    "unsupported_fields": json.dumps(payload.get("unsupported_fields", []), ensure_ascii=True),
                    "corrected_fields": json.dumps(payload.get("corrected_fields", []), ensure_ascii=True),
                    "missing_obvious_fields": json.dumps(payload.get("missing_obvious_fields", []), ensure_ascii=True),
                    "note": payload.get("note", ""),
                    "api_error": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "row_number": row_number,
                    "custom_id": custom_id,
                    "status": "",
                    "confidence": "",
                    "unsupported_fields": "",
                    "corrected_fields": "",
                    "missing_obvious_fields": "",
                    "note": "",
                    "api_error": str(exc),
                }
            )

    rows.sort(key=lambda item: (item["row_number"] is None, item["row_number"]))
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "batch_id": batch.id,
        "status": batch.status,
        "output_file_id": batch.output_file_id,
        "jsonl_output": str(args.output_jsonl),
        "csv_output": str(args.output_csv),
        "rows": len(rows),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
