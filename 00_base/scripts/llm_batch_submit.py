#!/usr/bin/env python3
"""Submit a Batch job to OpenAI for LLM extraction."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except Exception as exc:  # pragma: no cover
    print("requests is required:", exc)
    sys.exit(1)

API_BASE = "https://api.openai.com/v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-jsonl", default="downloads/llm_batch_input.jsonl")
    parser.add_argument("--job-file", default="downloads/llm_batch_job.json")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set.")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {api_key}"}

    input_path = Path(args.input_jsonl)
    if not input_path.exists():
        print(f"Input JSONL not found: {input_path}")
        sys.exit(1)

    with input_path.open("rb") as f:
        files = {"file": (input_path.name, f, "application/jsonl")}
        data = {"purpose": "batch"}
        resp = requests.post(f"{API_BASE}/files", headers=headers, files=files, data=data, timeout=120)
    if resp.status_code >= 400:
        print(resp.status_code, resp.text)
        sys.exit(1)
    file_info = resp.json()
    file_id = file_info.get("id")
    if not file_id:
        print("No file id returned.")
        sys.exit(1)

    batch_payload = {
        "input_file_id": file_id,
        "endpoint": "/v1/responses",
        "completion_window": "24h",
        "metadata": {"job": "planning-llm-extraction"},
    }
    resp = requests.post(f"{API_BASE}/batches", headers={**headers, "Content-Type": "application/json"}, json=batch_payload, timeout=120)
    if resp.status_code >= 400:
        print(resp.status_code, resp.text)
        sys.exit(1)

    job = resp.json()
    Path(args.job_file).write_text(json.dumps(job, indent=2), encoding="utf-8")
    print("Batch submitted. ID:", job.get("id"))
    print("Job file:", args.job_file)


if __name__ == "__main__":
    main()
