#!/usr/bin/env python3
"""Phase B: batch-download planner reports for an ePlan/iDocs council."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from planner_report_downloader import (
    PlannerReportClient,
    application_ref_from_url,
    build_cohort,
    classify_planner_report,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = ROOT / "04_fi" / "current" / "greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv"
OUT_ROOT = ROOT / "02_development" / "source_data" / "planner_reports"

COUNCIL_PATH = {
    "Meath County Council": "MeathCC",
    "Kildare County Council": "KildareCC",
    "Louth County Council": "LouthCC",
    "Wicklow County Council": "WicklowCC",
    "Limerick County Council": "LimerickCC",
    "Waterford City and County Council": "WaterfordCCC",
    "Tipperary County Council": "TipperaryCC",
    "Donegal County Council": "DonegalCC",
    "Galway County Council": "GalwayCC",
    "Laois County Council": "LaoisCC",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--council", default="Meath County Council")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--refusals-only", action="store_true", help="target refused cases first")
    parser.add_argument("--seed", type=int, default=20260905, help="cohort sampling seed; vary it to reach new rows")
    parser.add_argument("--received-year-min", type=int, default=None, help="only cases received in this year or later")
    parser.add_argument("--received-year-max", type=int, default=None, help="only cases received in this year or earlier")
    args = parser.parse_args()

    cases = pd.read_csv(DEFAULT_CSV, low_memory=False)
    cohort = build_cohort(
        cases, args.council, limit=args.limit, refusals_only=args.refusals_only, seed=args.seed,
        received_year_min=args.received_year_min, received_year_max=args.received_year_max,
    )
    council_path = COUNCIL_PATH.get(args.council, args.council.replace(" ", ""))
    out_dir = args.out_dir or OUT_ROOT / council_path
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "download_log.csv"

    existing = pd.read_csv(log_path, low_memory=False) if log_path.exists() else pd.DataFrame(columns=["ref"])
    done_refs = set(existing[existing["status"] == "ok"]["ref"].astype(str)) if not existing.empty and "status" in existing.columns else set()
    client = PlannerReportClient(delay_seconds=args.delay)
    log_rows = []
    for _, row in cohort.iterrows():
        ref = str(row["_ref"])
        if ref in done_refs:
            continue
        url = str(row["fi_resolved_url"] or row.get("LinkAppDetails") or "")
        if not url:
            continue
        record = {"ref": ref, "authority": args.council, "details_url": url}
        try:
            details_html = client._get(url)
            documents = client.fetch_document_list(details_html)
            planner_docs = [doc for doc in documents if classify_planner_report(doc["type"])]
            record["documents_found"] = len(documents)
            record["planner_reports_found"] = len(planner_docs)
            downloaded = []
            for index, doc in enumerate(planner_docs, start=1):
                suffix = "" if len(planner_docs) == 1 else f"_{index}"
                output = out_dir / f"{ref}_planner_report{suffix}.pdf"
                ok = False
                for attempt in range(3):
                    if client.download(doc["pdf_url"], output):
                        ok = True
                        break
                    time.sleep(2 * (attempt + 1))
                downloaded.append({"type": doc["type"], "docid": doc["docid"], "ok": ok, "file": output.name})
            record["downloaded"] = json.dumps(downloaded)
            record["status"] = "ok"
        except Exception as exc:
            record["documents_found"] = 0
            record["planner_reports_found"] = 0
            record["downloaded"] = "[]"
            record["status"] = f"error: {exc}"
        log_rows.append(record)
        print(json.dumps(record), flush=True)

    if log_rows:
        pd.DataFrame(log_rows).to_csv(log_path, mode="a", header=not log_path.exists(), index=False)
    print(json.dumps({"processed": len(log_rows), "out_dir": str(out_dir)}, indent=2))


if __name__ == "__main__":
    main()
