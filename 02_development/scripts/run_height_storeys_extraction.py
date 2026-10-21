#!/usr/bin/env python3
"""Submit the height/storeys extraction parts sequentially, wait, and merge."""
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


def submit_part(client, part_file: Path, part_index: int) -> str:
    with part_file.open("rb") as handle:
        uploaded = client.files.create(file=handle, purpose="batch")
    batch = client.batches.create(input_file_id=uploaded.id, endpoint="/v1/chat/completions", completion_window="24h")
    (OUT_DIR / f"batch_job_part{part_index:02d}.json").write_text(
        json.dumps({"id": batch.id, "input_file_id": uploaded.id}), encoding="utf-8"
    )
    print(f"part {part_index}: submitted batch {batch.id} ({batch.status})", flush=True)
    return batch.id


def wait_for_completion(client, batch_id: str, poll_seconds: int, timeout_hours: float) -> object:
    deadline = time.monotonic() + timeout_hours * 3600
    while True:
        batch = client.batches.retrieve(batch_id)
        if batch.status in {"completed", "failed", "expired", "cancelled"}:
            return batch
        if time.monotonic() > deadline:
            raise TimeoutError(f"Batch {batch_id} still {batch.status} after {timeout_hours}h.")
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--timeout-hours", type=float, default=5.0)
    parser.add_argument("--skip-submitted", action="store_true", help="reuse existing batch_job_partNN.json files")
    args = parser.parse_args()

    manifest = json.loads((OUT_DIR / "preparation_summary.json").read_text(encoding="utf-8"))
    client = make_client()
    result_frames: list[pd.DataFrame] = []
    for part in manifest["parts"]:
        part_file = OUT_DIR / part["file"]
        job_file = OUT_DIR / f"batch_job_part{int(part['part']):02d}.json"
        if args.skip_submitted and job_file.exists():
            batch_id = json.loads(job_file.read_text(encoding="utf-8"))["id"]
        else:
            batch_id = submit_part(client, part_file, int(part["part"]))
        batch = wait_for_completion(client, batch_id, args.poll_seconds, args.timeout_hours)
        if batch.status != "completed":
            raise RuntimeError(f"part {part['part']} batch {batch.id} ended with status {batch.status}.")
        file_text = client.files.content(batch.output_file_id).text
        (OUT_DIR / f"batch_output_part{int(part['part']):02d}.jsonl").write_text(file_text, encoding="utf-8")
        result_frames.append(flatten_batch_output(file_text))
        print(f"part {part['part']}: {len(result_frames[-1])} responses collected", flush=True)

    results = pd.concat(result_frames, ignore_index=True)
    results.to_csv(OUT_DIR / "batch_results.csv", index=False)
    ground = pd.read_csv(args.input, low_memory=False)
    merged = merge_results(ground, results, model_version=manifest.get("model", "gpt-5"))
    merged.to_csv(OUT_DIR / "ground_source_height_storeys_extracted.csv", index=False)
    sample = build_verification_sample(merged, sample_size=args.sample_size)
    sample.to_csv(OUT_DIR / "height_storeys_verification_sample.csv", index=False)

    summary = extraction_summary(merged)
    summary.update({
        "parts_submitted": len(manifest["parts"]),
        "merged_output": str(OUT_DIR / "ground_source_height_storeys_extracted.csv"),
        "verification_sample_rows": int(len(sample)),
        "verification_sample_path": str(OUT_DIR / "height_storeys_verification_sample.csv"),
    })
    (OUT_DIR / "extraction_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
