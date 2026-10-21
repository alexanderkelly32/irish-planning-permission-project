#!/usr/bin/env python3
"""Check Batch job status and optionally download output."""
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
    parser.add_argument("--job-file", default="downloads/llm_batch_job.json")
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output-jsonl", default="downloads/llm_batch_output.jsonl")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set.")
        sys.exit(1)

    batch_id = args.batch_id
    if not batch_id:
        job_path = Path(args.job_file)
        if not job_path.exists():
            print("Provide --batch-id or a valid --job-file.")
            sys.exit(1)
        batch_id = json.loads(job_path.read_text(encoding="utf-8")).get("id")

    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(f"{API_BASE}/batches/{batch_id}", headers=headers, timeout=60)
    if resp.status_code >= 400:
        print(resp.status_code, resp.text)
        sys.exit(1)
    info = resp.json()
    print("status:", info.get("status"))

    if args.download:
        output_file_id = info.get("output_file_id")
        if not output_file_id:
            print("No output_file_id yet.")
            return
        resp = requests.get(f"{API_BASE}/files/{output_file_id}/content", headers=headers, timeout=120)
        if resp.status_code >= 400:
            print(resp.status_code, resp.text)
            sys.exit(1)
        Path(args.output_jsonl).write_bytes(resp.content)
        print("Downloaded:", args.output_jsonl)


if __name__ == "__main__":
    main()
