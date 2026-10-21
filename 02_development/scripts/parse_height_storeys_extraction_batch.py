#!/usr/bin/env python3
"""Download, flatten and merge the height/storeys extraction batch."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from height_storeys_extraction import (
    build_verification_sample,
    extraction_summary,
    flatten_batch_output,
    merge_results,
)
from openai_batch_utils import make_client

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "height_storeys_extraction_2026-09-04"
DEFAULT_INPUT = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_ge10_fixed.csv"
DEFAULT_BATCH_JOB = OUT_DIR / "batch_job.json"


def wait_for_completion(client, batch_id: str, poll_seconds: int, timeout_hours: float) -> object:
    deadline = time.monotonic() + timeout_hours * 3600
    while True:
        batch = client.batches.retrieve(batch_id)
        if batch.status in {"completed", "failed", "expired", "cancelled"}:
            return batch
        if time.monotonic() > deadline:
            raise TimeoutError(f"Batch {batch_id} still {batch.status} after {timeout_hours}h; rerun with --wait.")
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--batch-job", type=Path, default=DEFAULT_BATCH_JOB)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--wait", action="store_true", help="poll until the batch completes")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--timeout-hours", type=float, default=6.0)
    args = parser.parse_args()

    batch_job = json.loads(args.batch_job.read_text(encoding="utf-8"))
    client = make_client()
    batch = wait_for_completion(client, batch_job["id"], args.poll_seconds, args.timeout_hours) if args.wait else client.batches.retrieve(batch_job["id"])
    if batch.status == "failed":
        raise RuntimeError(f"Batch {batch.id} failed.")
    if not batch.output_file_id:
        raise RuntimeError(f"Batch {batch.id} is not complete yet. Current status: {batch.status}")

    file_text = client.files.content(batch.output_file_id).text
    (OUT_DIR / "batch_output.jsonl").write_text(file_text, encoding="utf-8")
    results = flatten_batch_output(file_text)
    results.to_csv(OUT_DIR / "batch_results.csv", index=False)

    ground = pd.read_csv(args.input, low_memory=False)
    merged = merge_results(ground, results, model_version=batch_job.get("body", {}).get("model", "gpt-5"))
    merged.to_csv(OUT_DIR / "ground_source_height_storeys_extracted.csv", index=False)

    sample = build_verification_sample(merged, sample_size=args.sample_size)
    sample.to_csv(OUT_DIR / "height_storeys_verification_sample.csv", index=False)

    summary = extraction_summary(merged)
    summary.update({
        "batch_id": batch.id,
        "batch_status": batch.status,
        "merged_output": str(OUT_DIR / "ground_source_height_storeys_extracted.csv"),
        "verification_sample_rows": int(len(sample)),
        "verification_sample_path": str(OUT_DIR / "height_storeys_verification_sample.csv"),
    })
    (OUT_DIR / "extraction_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
