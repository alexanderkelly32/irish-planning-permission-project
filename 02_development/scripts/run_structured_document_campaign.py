#!/usr/bin/env python3
"""Run the scaled structured document-extraction campaign end to end."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from height_storeys_extraction import flatten_batch_output  # noqa: F401  (kept for reference symmetry)
from openai_batch_utils import make_client
from structured_document_extraction import (
    build_document_cohort,
    build_verification_sample,
    campaign_coverage_report,
    flatten_doc_batch_output,
    merge_campaign_results,
    prepare_campaign,
)

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "document_extraction_campaign_2026-09-04"
OCR_DIR = ROOT / "03_refusal" / "documents" / "ocr"
FI_DIR = ROOT / "04_fi" / "source_data" / "fi_case_text"


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
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--timeout-hours", type=float, default=5.0)
    parser.add_argument("--requests-per-part", type=int, default=300)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cohort = build_document_cohort(OCR_DIR, FI_DIR)
    parts, manifest = prepare_campaign(cohort, requests_per_part=args.requests_per_part)
    cohort.to_csv(OUT_DIR / "campaign_cohort.csv", index=False)
    manifest.to_csv(OUT_DIR / "campaign_manifest.csv", index=False)
    for index, part in enumerate(parts, start=1):
        (OUT_DIR / f"batch_requests_part{index:02d}.jsonl").write_text(
            "\n".join(json.dumps(request, ensure_ascii=True) for request in part) + "\n",
            encoding="utf-8",
        )
    summary = {
        "document_rows": int(len(cohort)),
        "request_parts": len(parts),
        "requests_total": sum(len(part) for part in parts),
        "manifest_rows": int(len(manifest)),
        "model": "gpt-5",
    }
    (OUT_DIR / "campaign_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("PREPARATION:", json.dumps(summary, indent=2))

    if args.prepare_only:
        return

    client = make_client()
    result_frames = []
    for part_index in range(1, len(parts) + 1):
        part_file = OUT_DIR / f"batch_requests_part{part_index:02d}.jsonl"
        job_file = OUT_DIR / f"batch_job_part{part_index:02d}.json"
        if job_file.exists():
            batch_id = json.loads(job_file.read_text(encoding="utf-8"))["id"]
        else:
            with part_file.open("rb") as handle:
                uploaded = client.files.create(file=handle, purpose="batch")
            batch = client.batches.create(input_file_id=uploaded.id, endpoint="/v1/chat/completions", completion_window="24h")
            job_file.write_text(json.dumps({"id": batch.id, "input_file_id": uploaded.id}), encoding="utf-8")
            batch_id = batch.id
            print(f"part {part_index}: submitted batch {batch_id}", flush=True)
        batch = wait_for_completion(client, batch_id, args.poll_seconds, args.timeout_hours)
        if batch.status != "completed":
            raise RuntimeError(f"part {part_index} batch {batch_id} ended with status {batch.status}.")
        file_text = client.files.content(batch.output_file_id).text
        (OUT_DIR / f"batch_output_part{part_index:02d}.jsonl").write_text(file_text, encoding="utf-8")
        result_frames.append(flatten_doc_batch_output(file_text))
        print(f"part {part_index}: {len(result_frames[-1])} responses", flush=True)

    results = pd.concat(result_frames, ignore_index=True)
    results.to_csv(OUT_DIR / "campaign_results.csv", index=False)
    merged = merge_campaign_results(cohort, results, model_version="gpt-5")
    merged.to_csv(OUT_DIR / "ground_source_document_extracted.csv", index=False)
    sample = build_verification_sample(merged)
    sample.to_csv(OUT_DIR / "document_extraction_verification_sample.csv", index=False)
    report = campaign_coverage_report(merged)
    report["verification_sample_rows"] = int(len(sample))
    (OUT_DIR / "campaign_coverage_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("COVERAGE:", json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
