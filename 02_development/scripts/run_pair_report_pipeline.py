#!/usr/bin/env python3
"""Both-sides planner-report campaign for audited revision pairs.

For every accepted refused->granted pair whose side uses an ePlan/iDocs portal,
download the planner report for each side that lacks an extraction, OCR it,
extract structured fields, and compute report-sourced pair deltas.

The download/OCR/extraction steps reuse the resumable pipeline machinery and
the billing floor; the delta merge feeds the canonical records via
revision_pair_report_extractions.csv (read by build_canonical_revision_schemes
as a second pair-extraction source).

Usage: python run_pair_report_pipeline.py  (long-running; detached in practice)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
QUEUE = CURRENT / "full_revision_candidate_queue.csv"
REPORTS = ROOT / "02_development" / "source_data" / "planner_reports"
PAIR_DIR = CURRENT / "revision_pair_report_extraction_2026-09-13"
DELTA_FIELDS = [
    "max_storeys", "max_height_m", "parking_spaces", "cycle_parking_spaces",
    "vehicular_access_points", "nearest_dwelling_separation_m",
    "opposing_window_separation_m", "communal_open_space_sqm",
]
DEFAULT_BALANCE_FLOOR = 0.20
REFUSED_DECISIONS = ROOT / "02_development" / "source_data" / "refused_arm_decisions"


def download_decision_docs(sides: pd.DataFrame, delay: float = 1.5, source: str = "refused_arm") -> int:
    """Download the ORIGINAL refusal decision notices for audited pairs.

    Refused-arm decisions go to refused_arm_decisions/<council>/<ref>_decision.pdf;
    granted-arm decisions go to granted_arm_decisions/<council>/... so the report
    extraction directories stay unpolluted. Resume-safe JSONL log.
    """
    if sides.empty:
        return 0
    originals = sides[sides["side"] == "original"].copy()
    decision_root = ROOT / "02_development" / "source_data" / (
        "refused_arm_decisions" if source == "refused_arm" else "granted_arm_decisions"
    )
    decision_root.mkdir(parents=True, exist_ok=True)
    log_path = decision_root / "decision_download_log.jsonl"
    done = set()
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("status") in {"ok", "no_decision_doc"}:
                    done.add(item.get("ref", ""))
    client = PlannerReportClient(delay_seconds=delay)
    processed = 0
    for _, side in originals.iterrows():
        ref = side["ref"]
        if ref in done:
            continue
        out_dir = decision_root / side["council_path"]
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{ref}_decision.pdf"
        if target.exists() and target.stat().st_size > 0:
            continue
        record = {"ref": ref, "council": side["council"], "url": side["url"]}
        try:
            details_html = client._get(side["url"])
            documents = client.fetch_document_list(details_html)
            decision_docs = [doc for doc in documents if "decision" in doc.get("type", "").lower()]
            record["decision_docs_found"] = len(decision_docs)
            ok = False
            if decision_docs:
                ok = client.download(decision_docs[0]["pdf_url"], target)
            record["downloaded"] = ok
            record["status"] = "ok" if ok else "no_decision_doc"
        except Exception as exc:
            record["status"] = f"error: {exc}"
            record["downloaded"] = False
        with log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        processed += 1
        if processed % 25 == 0:
            print(json.dumps({"decision_downloads_processed": processed}), flush=True)
    return processed

import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "02_development" / "scripts"))
from run_planner_report_download import COUNCIL_PATH  # noqa: E402
from planner_report_downloader import PlannerReportClient, application_ref_from_url  # noqa: E402

EPLAN_HOSTS = ("eplanning.ie",)


def accepted_pairs(source: str | None = None) -> pd.DataFrame:
    if source == "refused_arm":
        merged = CURRENT / "refused_refused_audit_merged.csv"
        fixed = merged if merged.exists() else (CURRENT / "refused_refused_review_rows_fixed.csv")
        frame = pd.read_csv(fixed, low_memory=False)
        accepted = frame[frame["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")].copy()
        accepted["planning_authority"] = accepted.get("planning_authority")
        return accepted
    queue = pd.read_csv(QUEUE, low_memory=False)
    accepted = queue[queue["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")].copy()
    return accepted


def side_rows(pairs: pd.DataFrame) -> pd.DataFrame:
    """One row per pair side with an ePlan URL and a supported council."""
    rows = []
    for _, pair in pairs.iterrows():
        council = str(pair.get("planning_authority") or "")
        if council not in COUNCIL_PATH:
            continue
        for prefix, url_column, key_column in [
            ("original", "original_source_url", "original_case_key"),
            ("revised", "revised_source_url", "revised_case_key"),
        ]:
            url = str(pair.get(url_column) or "")
            if not url or not any(host in url for host in EPLAN_HOSTS):
                continue
            ref = application_ref_from_url(url)
            if not ref:
                continue
            rows.append({
                "side": prefix,
                "case_key": str(pair.get(key_column) or ""),
                "council": council,
                "council_path": COUNCIL_PATH[council],
                "ref": ref,
                "url": url,
            })
    return pd.DataFrame(rows)


def already_extracted(side: pd.Series) -> bool:
    extraction_csv = REPORTS / side["council_path"] / "report_ocr_extractions.csv"
    if not extraction_csv.exists():
        return False
    frame = pd.read_csv(extraction_csv, low_memory=False)
    keys = frame["case_key"].astype(str).str.strip()
    return side["ref"] in set(keys)


def _completed_refs() -> set[str]:
    done: set[str] = set()
    jsonl_path = PAIR_DIR / "pair_side_download_log.jsonl"
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                done.add(json.loads(line).get("ref", ""))
            except json.JSONDecodeError:
                continue
    legacy_csv = PAIR_DIR / "pair_side_download_log.csv"
    if legacy_csv.exists():
        try:
            old = pd.read_csv(legacy_csv, on_bad_lines="skip")
            if not old.empty and "ref" in old.columns:
                done |= set(old["ref"].astype(str))
        except Exception:
            pass
    return done


def download_missing_sides(sides: pd.DataFrame, delay: float = 1.5) -> int:
    jsonl_path = PAIR_DIR / "pair_side_download_log.jsonl"
    done = _completed_refs()
    client = PlannerReportClient(delay_seconds=delay)
    processed = 0
    for _, side in sides.iterrows():
        if side["ref"] in done or already_extracted(side):
            continue
        out_dir = REPORTS / side["council_path"]
        out_dir.mkdir(parents=True, exist_ok=True)
        record = {"ref": side["ref"], "council": side["council"], "side": side["side"], "url": side["url"]}
        try:
            details_html = client._get(side["url"])
            documents = client.fetch_document_list(details_html)
            planner_docs = [doc for doc in documents if "planner" in doc.get("type", "").lower() or "report" in doc.get("type", "").lower()]
            record["planner_reports_found"] = len(planner_docs)
            downloaded = []
            for index, doc in enumerate(planner_docs, start=1):
                suffix = "" if len(planner_docs) == 1 else f"_{index}"
                output = out_dir / f"{side['ref']}_planner_report{suffix}.pdf"
                ok = client.download(doc["pdf_url"], output)
                downloaded.append({"type": doc["type"], "ok": ok, "file": output.name})
            record["downloaded"] = json.dumps(downloaded)
            record["status"] = "ok"
        except Exception as exc:
            record["planner_reports_found"] = 0
            record["downloaded"] = "[]"
            record["status"] = f"error: {exc}"
        with jsonl_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        processed += 1
        print(json.dumps(record), flush=True)
    return processed


def extract_new_texts(balance_floor: float, source: str = "granted_arm") -> list[dict]:
    from run_planner_report_pipeline import prep_and_extract

    results = []
    councils = {side["council_path"] for _, side in side_rows(accepted_pairs(source)).iterrows()}
    for council_path in sorted(councils):
        if not (REPORTS / council_path).exists():
            continue
        results.append(prep_and_extract(council_path, balance_floor=balance_floor))
    return results


def report_lookup() -> dict[tuple[str, str], dict[str, float]]:
    """(council_path, ref) -> extracted structured values."""
    lookup: dict[tuple[str, str], dict[str, float]] = {}
    for csv_path in REPORTS.rglob("report_ocr_extractions.csv"):
        frame = pd.read_csv(csv_path, low_memory=False)
        for _, row in frame.iterrows():
            key = (csv_path.parent.name, str(row.get("case_key")).strip())
            values = {}
            for field in DELTA_FIELDS:
                column = f"doc_{field}"
                if column in frame.columns and pd.notna(row.get(column)):
                    values[field] = float(row[column])
            if values:
                lookup.setdefault(key, {}).update(values)
    return lookup


def merge_pair_report_deltas(source: str = "granted_arm") -> pd.DataFrame:
    pairs = accepted_pairs(source)
    lookup = report_lookup()
    rows = []
    for _, pair in pairs.iterrows():
        council = str(pair.get("planning_authority") or "")
        council_path = COUNCIL_PATH.get(council)
        if council_path is None:
            continue
        record = {
            "original_case_key": str(pair.get("original_case_key") or ""),
            "revised_case_key": str(pair.get("revised_case_key") or ""),
        }
        original = {}
        revised = {}
        for side_key, url_column in [("original", "original_source_url"), ("revised", "revised_source_url")]:
            url = str(pair.get(url_column) or "")
            if not url or not any(host in url for host in EPLAN_HOSTS):
                continue
            ref = application_ref_from_url(url)
            if not ref:
                continue
            if side_key == "original":
                original = lookup.get((council_path, ref), {})
            else:
                revised = lookup.get((council_path, ref), {})
        for field in DELTA_FIELDS:
            before = original.get(field)
            after = revised.get(field)
            record[f"original_{field}"] = before
            record[f"revised_{field}"] = after
            record[f"{field}_delta"] = round(after - before, 6) if before is not None and after is not None else None
        rows.append(record)
    frame = pd.DataFrame(rows)
    out_path = PAIR_DIR / (
        "revision_pair_report_extractions_refused_arm.csv" if source == "refused_arm"
        else "revision_pair_report_extractions.csv"
    )
    frame.to_csv(out_path, index=False)
    non_zero = frame[[f"{f}_delta" for f in DELTA_FIELDS]].fillna(0).ne(0).any(axis=1)
    summary = {
        "source": source,
        "pairs": int(len(frame)),
        "pairs_with_any_nonzero_delta": int(non_zero.sum()),
        "per_field_nonzero_delta_counts": {
            field: int(frame[f"{field}_delta"].fillna(0).ne(0).sum()) for field in DELTA_FIELDS
        },
        "output": str(out_path),
    }
    (PAIR_DIR / f"merge_summary_{source}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return frame


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--balance-floor", type=float, default=DEFAULT_BALANCE_FLOOR)
    parser.add_argument("--source", type=str, default="granted_arm", choices=["granted_arm", "refused_arm"])
    args = parser.parse_args()

    PAIR_DIR.mkdir(parents=True, exist_ok=True)
    pairs = accepted_pairs(args.source)
    sides = side_rows(pairs)
    print(json.dumps({
        "source": args.source,
        "accepted_pairs": int(len(pairs)),
        "eplan_sides": int(len(sides)),
        "councils": sorted(sides["council_path"].unique().tolist()),
    }, indent=2), flush=True)

    downloaded = download_missing_sides(sides)
    print(json.dumps({"sides_processed": downloaded}, indent=2), flush=True)
    decisions = download_decision_docs(sides, source=args.source)
    print(json.dumps({"decision_sides_processed": decisions, "source": args.source}, indent=2), flush=True)

    for council_path in sorted(sides["council_path"].unique()):
        import subprocess
        command = [
            sys.executable, str(ROOT / "02_development" / "scripts" / "ocr_planner_reports.py"),
            "--input-dir", str(REPORTS / council_path),
        ]
        print(f"RUN: {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")

    extract_new_texts(args.balance_floor, args.source)
    merge_pair_report_deltas(args.source)


if __name__ == "__main__":
    main()
