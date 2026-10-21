#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="extraction_of_site_data/_qa/units_only_200k_chunk_manifest.csv",
    )
    parser.add_argument(
        "--max-est-tokens",
        type=int,
        default=1_900_000,
    )
    parser.add_argument(
        "--prepare-script",
        default="extraction_of_site_data/_scripts/llm_units_batch_prepare.py",
    )
    parser.add_argument(
        "--submit-script",
        default="extraction_of_site_data/_scripts/llm_batch_submit.py",
    )
    parser.add_argument(
        "--chunks-dir",
        default="extraction_of_site_data/_qa/units_only_200k_chunks",
    )
    parser.add_argument(
        "--llm-batch-dir",
        default="extraction_of_site_data/_llm_batch",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=50,
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    manifest = pd.read_csv(manifest_path)
    for c in ["submitted", "status", "batch_id", "job_file"]:
        if c not in manifest.columns:
            manifest[c] = "" if c in {"status", "batch_id", "job_file"} else False

    # Pick first pending safe chunk.
    pending = manifest[
        (~manifest["submitted"].astype(bool))
        & (manifest["est_tokens_total"] <= args.max_est_tokens)
    ].sort_values("chunk_id")
    if pending.empty:
        print("No pending chunk under token safety threshold.")
        return

    row = pending.iloc[0]
    chunk_id = int(row["chunk_id"])
    chunk_file = Path(args.chunks_dir) / f"units_only_200k_chunk_{chunk_id:03d}.csv"
    if not chunk_file.exists():
        raise FileNotFoundError(f"Chunk file missing: {chunk_file}")

    out_jsonl = Path(args.llm_batch_dir) / f"units_only_200k_chunk_{chunk_id:03d}_input.jsonl"
    out_meta = Path(args.llm_batch_dir) / f"units_only_200k_chunk_{chunk_id:03d}_meta.csv"
    out_job = Path(args.llm_batch_dir) / f"units_only_200k_chunk_{chunk_id:03d}_job.json"

    prep_cmd = [
        "python",
        args.prepare_script,
        "--input",
        str(chunk_file),
        "--output-jsonl",
        str(out_jsonl),
        "--meta",
        str(out_meta),
        "--max-rows",
        str(int(row["rows"])),
        "--max-output-tokens",
        str(args.max_output_tokens),
    ]
    subprocess.run(prep_cmd, check=True)

    submit_cmd = [
        "python",
        args.submit_script,
        "--input-jsonl",
        str(out_jsonl),
        "--job-file",
        str(out_job),
    ]
    subprocess.run(submit_cmd, check=True)

    job = json.loads(out_job.read_text(encoding="utf-8"))
    batch_id = str(job.get("id", ""))
    idx = manifest.index[manifest["chunk_id"] == chunk_id][0]
    manifest.loc[idx, "submitted"] = True
    manifest.loc[idx, "status"] = "submitted"
    manifest.loc[idx, "batch_id"] = batch_id
    manifest.loc[idx, "job_file"] = str(out_job)
    manifest.to_csv(manifest_path, index=False)

    print(f"Submitted chunk {chunk_id:03d} with batch_id={batch_id}")
    print(f"Updated manifest: {manifest_path}")


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        raise EnvironmentError("OPENAI_API_KEY is required in environment.")
    main()
