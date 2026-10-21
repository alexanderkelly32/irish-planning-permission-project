#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import pandas as pd
import requests


API_BASE = "https://api.openai.com/v1"
ACTIVE_STATUSES = {"submitted", "validating", "in_progress", "finalizing"}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _get_batch_status(batch_id: str, api_key: str) -> tuple[str, str | None]:
    headers = {"Authorization": f"Bearer {api_key}"}
    r = requests.get(f"{API_BASE}/batches/{batch_id}", headers=headers, timeout=60)
    r.raise_for_status()
    info = r.json()
    return str(info.get("status", "unknown")), info.get("output_file_id")


def _download_output(output_file_id: str, out_path: Path, api_key: str) -> None:
    headers = {"Authorization": f"Bearer {api_key}"}
    r = requests.get(f"{API_BASE}/files/{output_file_id}/content", headers=headers, timeout=120)
    r.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="extraction_of_site_data/_qa/units_only_200k_chunk_manifest.csv")
    parser.add_argument("--hours", type=float, default=2.0)
    parser.add_argument("--interval-seconds", type=int, default=120)
    parser.add_argument("--max-est-tokens", type=int, default=1_900_000)
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is required.")

    manifest_path = Path(args.manifest)
    start = time.time()
    end = start + int(args.hours * 3600)

    print(f"Watching batches for ~{args.hours}h (interval {args.interval_seconds}s)")
    while time.time() < end:
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        manifest = pd.read_csv(manifest_path)
        changed = False
        newly_completed = []

        submitted = manifest[manifest.get("submitted", False).fillna(False).astype(bool)].copy()
        for idx, row in submitted.iterrows():
            batch_id = str(row.get("batch_id", "")).strip()
            if not batch_id:
                continue
            current_status = str(row.get("status", "submitted")).strip().lower()
            if current_status in {"completed", "failed", "cancelled", "expired"}:
                continue
            try:
                status, output_file_id = _get_batch_status(batch_id, api_key)
            except Exception as exc:
                print(f"status check failed for {batch_id}: {exc}")
                continue
            status_l = status.lower()
            if current_status != status_l:
                manifest.loc[idx, "status"] = status_l
                changed = True
                print(f"batch {batch_id} status -> {status_l}")

            if status_l == "completed":
                chunk_id = int(row["chunk_id"])
                out_jsonl = Path(f"extraction_of_site_data/_llm_batch/units_only_200k_chunk_{chunk_id:03d}_output.jsonl")
                merged_csv = Path(
                    f"extraction_of_site_data/_qa/units_only_200k_chunks/units_only_200k_chunk_{chunk_id:03d}_output_merged.csv"
                )
                input_chunk = Path(
                    f"extraction_of_site_data/_qa/units_only_200k_chunks/units_only_200k_chunk_{chunk_id:03d}.csv"
                )
                meta_csv = Path(f"extraction_of_site_data/_llm_batch/units_only_200k_chunk_{chunk_id:03d}_meta.csv")
                if output_file_id and (not out_jsonl.exists() or out_jsonl.stat().st_size == 0):
                    try:
                        _download_output(output_file_id, out_jsonl, api_key)
                        print(f"downloaded chunk {chunk_id:03d} output")
                    except Exception as exc:
                        print(f"download failed for chunk {chunk_id:03d}: {exc}")
                        continue
                if out_jsonl.exists() and input_chunk.exists() and meta_csv.exists():
                    try:
                        _run(
                            [
                                "python",
                                "extraction_of_site_data/_scripts/llm_batch_merge.py",
                                "--output-jsonl",
                                str(out_jsonl),
                                "--meta",
                                str(meta_csv),
                                "--input-wide",
                                str(input_chunk),
                                "--output-wide",
                                str(merged_csv),
                            ]
                        )
                        manifest.loc[idx, "merged_csv"] = str(merged_csv)
                        manifest.loc[idx, "output_jsonl"] = str(out_jsonl)
                        manifest.loc[idx, "status"] = "completed"
                        changed = True
                        newly_completed.append(chunk_id)
                        print(f"merged chunk {chunk_id:03d}")
                    except Exception as exc:
                        print(f"merge failed for chunk {chunk_id:03d}: {exc}")

        if changed:
            manifest.to_csv(manifest_path, index=False)

        if newly_completed:
            try:
                _run(
                    [
                        "python",
                        "extraction_of_site_data/_scripts/apply_completed_units_chunks.py",
                        "--manifest",
                        str(manifest_path),
                        "--input-wide",
                        "extraction_of_site_data/ground_source_extracted_final_wide_fixed.csv",
                        "--output-wide",
                        "extraction_of_site_data/ground_source_extracted_final_wide_fixed.csv",
                    ]
                )
                _run(["python", "extraction_of_site_data/_scripts/rebuild_comprehensive_master.py"])
            except Exception as exc:
                print(f"apply/rebuild failed: {exc}")

        # Keep one active chunk at a time.
        manifest = pd.read_csv(manifest_path)
        active_count = int(manifest["status"].astype(str).str.lower().isin(ACTIVE_STATUSES).sum())
        if active_count == 0:
            try:
                _run(
                    [
                        "python",
                        "extraction_of_site_data/_scripts/submit_next_units_chunk.py",
                        "--manifest",
                        str(manifest_path),
                        "--max-est-tokens",
                        str(args.max_est_tokens),
                    ]
                )
            except Exception as exc:
                print(f"submit-next failed: {exc}")

        time.sleep(args.interval_seconds)

    print("Watcher finished.")


if __name__ == "__main__":
    main()
