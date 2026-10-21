#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from openai_batch_utils import make_client


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "02_development" / "current" / "development_review_gpt5_batch_requests.jsonl"
DEFAULT_OUTPUT = ROOT / "02_development" / "current" / "development_review_gpt5_batch_job.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a batch request file and create an OpenAI Batch job.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--endpoint", default="/v1/chat/completions")
    parser.add_argument("--completion-window", default="24h")
    args = parser.parse_args()

    client = make_client()

    with args.input.open("rb") as handle:
        uploaded = client.files.create(file=handle, purpose="batch")

    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint=args.endpoint,
        completion_window=args.completion_window,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(batch.model_dump_json(indent=2), encoding="utf-8")

    summary = {
        "request_file": str(args.input),
        "uploaded_file_id": uploaded.id,
        "batch_id": batch.id,
        "status": batch.status,
        "output_manifest": str(args.output),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
