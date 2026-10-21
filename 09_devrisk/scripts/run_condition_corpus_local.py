"""Runner: grant-condition corpus from ALREADY-DOWNLOADED planner-report PDFs.

Scans 02_development/source_data/planner_reports/* and granted_arm_decisions/*,
maps the application number in the filename to mature-cohort case keys,
extracts native text (fitz), classifies condition families (regex v1) and
writes condition_family_labels_corpus.csv. No network needed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.reporting.condition_families import classify_document, families_to_record  # noqa: E402

REPORT_DIRS = [
    settings.ROOT / "02_development" / "source_data" / "planner_reports",
    settings.ROOT / "02_development" / "source_data" / "granted_arm_decisions",
]


def app_number_from_filename(name: str) -> str | None:
    stem = Path(name).stem
    match = re.match(r"^(\d+)_planner_report", stem)
    if not match:
        match = re.match(r"^(\d+)_decision", stem)
    if match:
        return match.group(1)
    return None


def run() -> dict:
    import fitz

    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    mature["app"] = mature["ApplicationNumber"].astype(str).str.strip()
    app_to_case = {str(row["app"]): str(row["case_key"]) for _, row in mature.iterrows()}

    records = []
    scanned = 0
    for report_dir in REPORT_DIRS:
        for pdf_path in sorted(report_dir.rglob("*.pdf")):
            scanned += 1
            app = app_number_from_filename(pdf_path.name)
            if app is None or app not in app_to_case:
                continue
            try:
                document = fitz.open(pdf_path)
                text = "\n".join(page.get_text() for page in document)
                document.close()
            except Exception:  # noqa: BLE001
                continue
            if len(text.strip()) < 400:
                continue
            result = classify_document(text)
            records.append(families_to_record(app_to_case[app], result, granted=True))

    labels = pd.DataFrame(records).drop_duplicates(subset=["case_key"], keep="first")
    out = settings.SILVER_DIR / "condition_family_labels_corpus.csv"
    labels.to_csv(out, index=False)

    summary = {
        "pdfs_scanned": scanned,
        "reports_labelled": int(len(labels)),
        "schemes_covered": int(labels["case_key"].nunique()),
        "family_prevalence": {
            column.replace("condition_", ""): int(labels[column].sum())
            for column in labels.columns if column.startswith("condition_") and column != "condition_family_count"
        },
        "out_path": str(out),
    }
    (settings.SILVER_DIR / "condition_corpus_local_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
