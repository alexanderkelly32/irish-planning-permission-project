"""Runner: pilot-authority grant-condition corpus (engine c).

Orchestrates the existing ePlan/iDocs downloader (02_development) for the
pilot authorities, extracts native text from planner reports, applies the
condition-family classifier, and exports an audit pack. Resumable and polite
(1s delay, skip-if-present). Pilot scope: granted pool schemes with eplanning
detail URLs for the chosen authorities (default Carlow + Meath).

Usage:
  python 09_devrisk\\scripts\\run_condition_corpus.py --limit 3          # smoke
  python 09_devrisk\\scripts\\run_condition_corpus.py --authorities Carlow Meath --limit 50
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "02_development" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.reporting.condition_families import classify_document, families_to_record  # noqa: E402
from planner_report_downloader import PLANNER_REPORT_TITLES, REPORT_NEGATIVE_TITLES, PlannerReportClient  # noqa: E402

CORPUS_DIR = settings.SILVER_DIR / "condition_corpus"
STATE_PATH = CORPUS_DIR / "state.json"

AUTHORITY_TO_IDOCS_PREFIX = {"carlow": "CarlowCC", "meath": "MeathCoCo"}


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"downloaded": {}, "failures": {}, "extracted": []}


def save_state(state: dict) -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def candidates(authorities: list[str]) -> pd.DataFrame:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    pool = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_pool.parquet")
    frame = register[register["case_key"].isin(pool["case_key"])].drop_duplicates("case_key").copy()
    frame = frame[frame["Decision"].astype(str).str.upper().str.contains("REFUS").eq(False)]
    frame["auth_lower"] = frame["PlanningAuthority"].str.lower()
    frame = frame[frame["auth_lower"].apply(lambda a: any(name in a for name in authorities))]
    frame["details_url"] = frame["LinkAppDetails"].fillna("").astype(str)
    frame = frame[frame["details_url"].str.contains("eplanning|AppFileRefDetails", case=False, regex=True)]
    return frame.sort_values("GrantDate", ascending=False).reset_index(drop=True)


def run(limit: int, authorities: list[str]) -> dict:
    client = PlannerReportClient(delay_seconds=1.0)
    state = load_state()
    queue = candidates(authorities)
    print(f"candidates: {len(queue)} granted schemes with eplanning URLs", flush=True)

    processed = 0
    for _, row in queue.iterrows():
        if processed >= limit:
            break
        case_key = row["case_key"]
        details_url = row["details_url"]
        scheme_dir = CORPUS_DIR / "reports" / _safe(case_key)
        if state["downloaded"].get(case_key) and any(scheme_dir.glob("*.pdf")):
            processed += 1
            continue
        try:
            import requests

            session = requests.Session()
            client.session = session
            details_html = client._get(details_url.replace("http://", "https://"))
            documents = client.fetch_document_list(details_html)
            picked = [
                doc for doc in documents
                if PLANNER_REPORT_TITLES.search(doc.get("title", "")) and not REPORT_NEGATIVE_TITLES.search(doc.get("title", ""))
            ]
            saved = []
            for doc in picked[:2]:
                output = scheme_dir / f"{doc.get('docid', 'doc')}.pdf"
                if client.download(doc["pdf_url"], output):
                    saved.append(str(output))
            state["downloaded"][case_key] = saved
            if not saved:
                state["failures"][case_key] = "no planner report PDF obtained"
        except Exception as error:  # noqa: BLE001
            state["failures"][case_key] = f"{type(error).__name__}: {str(error)[:200]}"
        save_state(state)
        processed += 1
        print(f"{processed}/{limit} {case_key}: {len(state['downloaded'].get(case_key, []))} pdfs", flush=True)

    rows = []
    for case_key, pdfs in state["downloaded"].items():
        for pdf_path in pdfs:
            try:
                import fitz

                document = fitz.open(pdf_path)
                text = "\n".join(page.get_text() for page in document)
                document.close()
            except Exception:  # noqa: BLE001
                continue
            if len(text.strip()) < 200:
                continue
            result = classify_document(text)
            rows.append(families_to_record(case_key, result, granted=True))
    labels = pd.DataFrame(rows)
    if not labels.empty:
        labels.to_csv(CORPUS_DIR / "condition_family_labels_pilot.csv", index=False)

    summary = {
        "attempted": processed,
        "downloaded": len(state["downloaded"]),
        "failed": len(state["failures"]),
        "labelled_reports": int(len(labels)),
        "failures": dict(list(state["failures"].items())[:20]),
    }
    (CORPUS_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--authorities", nargs="+", default=["carlow", "meath"])
    args = parser.parse_args()
    run(args.limit, [name.lower() for name in args.authorities])
