#!/usr/bin/env python3
"""Overnight planner-report pipeline: download -> OCR -> extract -> merge, per council."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "02_development" / "scripts"
REPORTS = ROOT / "02_development" / "source_data" / "planner_reports"

from run_planner_report_download import COUNCIL_PATH  # noqa: E402


def run_python(script: str, *args: str) -> None:
    command = [sys.executable, str(SCRIPTS / script), *args]
    print(f"RUN: {' '.join(command)}", flush=True)
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout:
        tail = result.stdout.strip().splitlines()[-6:]
        print("\n".join(tail), flush=True)
    if result.stderr.strip():
        print("STDERR:", result.stderr.strip()[-600:], flush=True)


def check_balance_floor(client, floor: float) -> tuple[bool, float]:
    """Return (enough_budget, balance). Extraction is skipped when the balance is
    at or below the floor so the pipeline keeps gathering free data."""
    from run_deepseek_extraction import check_balance

    try:
        payload = check_balance(client)
    except Exception as exc:
        print(f"balance check failed ({exc}); assuming enough budget", flush=True)
        return True, -1.0
    balances = payload.get("balance_infos") or []
    total = sum(float(info.get("total_balance") or 0.0) for info in balances)
    if not payload.get("is_available", True):
        return False, total
    return total > floor, total


def prep_and_extract(council_path: str, balance_floor: float = 0.20) -> dict:
    import pandas as pd

    from structured_document_extraction import (
        campaign_coverage_report,
        flatten_doc_batch_output,
        merge_campaign_results,
        prepare_campaign,
    )

    base = REPORTS / council_path
    existing_files = set()
    existing_csv = base / "report_ocr_extractions.csv"
    if existing_csv.exists():
        existing = pd.read_csv(existing_csv, low_memory=False)
        existing_files = set(existing["text_path"].map(lambda value: Path(str(value)).name))
    rows = []
    for text_path in sorted((base / "ocr_text").glob("*_ocr.txt")):
        if text_path.name in existing_files:
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        rows.append({
            "case_key": text_path.stem.split("_planner_report")[0],
            "authority": council_path,
            "document_type": "planner_report",
            "text_path": str(text_path),
            "doc_chars": len(text),
        })
    if not rows:
        return {"council": council_path, "new_reports": 0}
    from run_deepseek_extraction import make_deepseek_client, run_part

    client = make_deepseek_client()
    enough, balance = check_balance_floor(client, balance_floor)
    if not enough:
        print(f"SKIP extraction for {council_path}: balance {balance:.2f} at/below floor {balance_floor} (downloads/OCR continue free)", flush=True)
        return {"council": council_path, "new_reports": len(rows), "extraction": "skipped_no_budget", "balance": round(balance, 2)}
    print(f"extract {council_path}: {len(rows)} new reports; balance {balance:.2f}", flush=True)
    cohort = pd.DataFrame(rows).drop_duplicates("text_path").reset_index(drop=True)
    cohort["row_number"] = cohort.index
    cohort.to_csv(base / "ocr_report_cohort_new.csv", index=False)
    parts, manifest = prepare_campaign(cohort, requests_per_part=300)
    for index, part in enumerate(parts, start=1):
        (base / f"batch_requests_part{index:02d}.jsonl").write_text(
            "\n".join(json.dumps(request, ensure_ascii=True) for request in part) + "\n",
            encoding="utf-8",
        )
    for index in range(1, len(parts) + 1):
        part_file = base / f"batch_requests_part{index:02d}.jsonl"
        output_file = base / f"batch_output_part{index:02d}.jsonl"
        run_part(client, part_file, output_file, "deepseek-v4-pro", max_workers=8)
    frames = [flatten_doc_batch_output((base / f"batch_output_part{i:02d}.jsonl").read_text(encoding="utf-8")) for i in range(1, len(parts) + 1)]
    import pandas as pd

    results = pd.concat(frames, ignore_index=True)
    merged = merge_campaign_results(cohort, results, model_version="deepseek-v4-pro")
    if existing_csv.exists():
        merged = pd.concat([pd.read_csv(existing_csv, low_memory=False), merged], ignore_index=True)
    merged.to_csv(existing_csv, index=False)
    report = campaign_coverage_report(merged)
    report["council"] = council_path
    with open(base / "report_coverage.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    return {"council": council_path, "new_reports": int(len(rows)), "coverage": report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=None, help="JSON file with [{council, limit, seed, refusals_only}]")
    parser.add_argument("--balance-floor", type=float, default=0.20, help="skip paid extraction when the DeepSeek balance is at/below this USD amount (downloads/OCR continue)")
    args = parser.parse_args()

    if args.plan:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    else:
        plan = [
            {"council": "Meath County Council", "limit": 200, "seed": 20260906, "refusals": True},
            {"council": "Kildare County Council", "limit": 150, "seed": 20260906, "refusals": True},
            {"council": "Louth County Council", "limit": 100, "seed": 20260906, "refusals": True},
            {"council": "Meath County Council", "limit": 200, "seed": 20260907, "refusals": True},
            {"council": "Kildare County Council", "limit": 150, "seed": 20260907, "refusals": True},
            {"council": "Louth County Council", "limit": 100, "seed": 20260907, "refusals": True},
        ]

    summary = []
    for entry in plan:
        council = entry["council"]
        council_path = COUNCIL_PATH[council]
        refusals = "--refusals-only" if entry.get("refusals") else ""
        year_min = ["--received-year-min", str(entry["received_year_min"])] if entry.get("received_year_min") else []
        year_max = ["--received-year-max", str(entry["received_year_max"])] if entry.get("received_year_max") else []
        run_python(
            "run_planner_report_download.py",
            "--council", council,
            "--limit", str(entry["limit"]),
            "--seed", str(entry["seed"]),
            "--delay", "1.5",
            *([refusals] if refusals else []),
            *year_min,
            *year_max,
        )
        run_python("ocr_planner_reports.py", "--input-dir", str(REPORTS / council_path))
        outcome = prep_and_extract(council_path, balance_floor=args.balance_floor)
        summary.append({"council": council, "seed": entry["seed"], **outcome})
        print(json.dumps(summary[-1], indent=2), flush=True)
        time.sleep(2)

    with open(REPORTS / "overnight_pipeline_summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
