"""Runner: extract FI evidence from the local planner-report corpus.

Scans the 5,512 planner-report PDFs (granted decisions), extracts text, and
finds further-information mentions with dates. The register's FI dates are
statutory artefacts; the reports are the real evidence. Outputs
fi_doc_evidence.csv: scheme -> FI mentioned, count, first date if present.
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

REPORT_DIRS = [
    settings.ROOT / "02_development" / "source_data" / "planner_reports",
    settings.ROOT / "02_development" / "source_data" / "granted_arm_decisions",
]

FI_RE = re.compile(
    r"\b(further information|additional information|further clarification)\b.{0,80}?(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
    re.IGNORECASE,
)
FI_MENTION = re.compile(r"\b(further information|additional information)\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b")

STATE_PATH = settings.SILVER_DIR / "fi_docs" / "state.json"


def app_number_from_filename(name: str) -> str | None:
    stem = Path(name).stem
    for pattern in (r"^(\d+)_planner_report", r"^(\d+)_decision"):
        match = re.match(pattern, stem)
        if match:
            return match.group(1)
    return None


if __name__ == "__main__":
    import fitz

    out_dir = settings.SILVER_DIR / "fi_docs"
    out_dir.mkdir(parents=True, exist_ok=True)
    state = {"done": {}, "errors": {}}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    app_to_case = {str(row["ApplicationNumber"]).strip(): str(row["case_key"]) for _, row in mature.iterrows()}

    records = []
    scanned = 0
    for report_dir in REPORT_DIRS:
        for pdf_path in sorted(report_dir.rglob("*.pdf")):
            app = app_number_from_filename(pdf_path.name)
            if app is None or app not in app_to_case:
                continue
            case_key = app_to_case[app]
            if case_key in state["done"]:
                continue
            scanned += 1
            try:
                document = fitz.open(pdf_path)
                text = "\n".join(page.get_text() for page in document)
                document.close()
            except Exception:  # noqa: BLE001
                state["errors"][case_key] = "pdf open failed"
                continue
            mentions = len(FI_MENTION.findall(text))
            dated = FI_RE.findall(text)
            first_date = None
            if dated:
                first_date = dated[0][1] if isinstance(dated[0], tuple) else None
            state["done"][case_key] = {"mentions": mentions, "dated": len(dated), "chars": len(text)}
            records.append({
                "case_key": case_key,
                "fi_mentioned": int(mentions > 0),
                "fi_mention_count": mentions,
                "fi_dated_count": len(dated),
                "fi_first_date": first_date,
                "text_chars": len(text),
            })
            if scanned % 200 == 0:
                STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
                print(f"scanned {scanned}", flush=True)

    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    frame = pd.DataFrame(records)
    frame.to_csv(settings.SILVER_DIR / "fi_doc_evidence.csv", index=False)
    summary = {
        "reports_scanned": scanned,
        "schemes_with_report_text": int(len(frame)),
        "schemes_with_fi_mention": int(frame["fi_mentioned"].sum()) if len(frame) else 0,
        "schemes_with_dated_fi": int((frame["fi_dated_count"] > 0).sum()) if len(frame) else 0,
        "out_path": str(settings.SILVER_DIR / "fi_doc_evidence.csv"),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
