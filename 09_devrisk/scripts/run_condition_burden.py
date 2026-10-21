"""Runner: B. Planning-condition burden extraction from planner PDFs.

Per PDF: total conditions (numbered list in the decision section),
pre-commencement conditions ("prior to commencement/before commencement"),
bond/security, development contribution, Uisce connection, drainage,
roads, archaeology, ecology, Part V, phasing mentions. Writes
condition_burden_features.csv. Background-safe, resume per file.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import fitz  # noqa: E402

from devrisk import settings  # noqa: E402

REPORT_DIR = settings.ROOT / "02_development" / "source_data" / "planner_reports"
STATE_PATH = settings.SILVER_DIR / "condition_burden_state.json"
OUT_PATH = settings.SILVER_DIR / "condition_burden_features.csv"

CONDITION_HEADER_RE = re.compile(
    r"subject to the following (\d{1,3}) conditions|following (\d{1,3}) conditions|(\d{1,3})\s+conditions attached",
    re.I)
NUMBERED_RE = re.compile(r"^\s*(\d{1,3})[\.\)]\s+[A-Z]", re.M)
PRE_COMM_RE = re.compile(r"prior to (the )?commencement|before (the )?commencement|prior to any development|before any development", re.I)
FEATURE_RE = {
    "bond": r"bond|security",
    "contribution": r"development contribution|financial contribution",
    "uisce": r"uisce|irish water|connection agreement|water supply|wastewater",
    "drainage": r"drainage|suds|attenuation",
    "roads": r"road|access|footpath|cycle",
    "archaeology": r"archaeolog",
    "ecology": r"ecolog|bat|bird|habitat|tree",
    "partv": r"part v|social housing|affordable",
    "phasing": r"phas",
    "levels": r"levels|ground levels|site levels",
    "retaining": r"retaining",
}


if __name__ == "__main__":
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"done": []}
    done = set(state["done"])
    pdfs = sorted(REPORT_DIR.rglob("*_planner_report*.pdf"))
    rows = []
    app_re = re.compile(r"^(\d+)_planner_report")
    for i, pdf in enumerate(pdfs):
        if str(pdf) in done:
            continue
        appno_match = app_re.match(pdf.name)
        appno = appno_match.group(1) if appno_match else pdf.stem[:20]
        try:
            with fitz.open(pdf) as doc:
                text = " ".join(page.get_text() for page in doc)
            header = CONDITION_HEADER_RE.search(text)
            n_conditions = int(next(g for g in header.groups() if g)) if header else None
            if n_conditions is None:
                numbers = NUMBERED_RE.findall(text)
                n_conditions = max((int(n) for n in numbers), default=None)
            row = {"appno": appno, "n_conditions": n_conditions,
                   "n_precommencement": len(PRE_COMM_RE.findall(text))}
            for name, pattern in FEATURE_RE.items():
                row[f"has_{name}"] = int(bool(re.search(pattern, text, re.I)))
            row["text_chars"] = len(text)
            rows.append(row)
        except Exception:
            pass
        state["done"].append(str(pdf))
        if i % 400 == 0:
            STATE_PATH.write_text(json.dumps(state))
            print(f"processed {i}", flush=True)
    STATE_PATH.write_text(json.dumps(state))
    import pandas as pd

    frame = pd.DataFrame(rows)
    frame.to_csv(OUT_PATH, index=False)
    report = {
        "pdfs": len(pdfs),
        "with_condition_count": int(frame["n_conditions"].notna().sum()),
        "median_conditions": round(float(frame["n_conditions"].median()), 1) if frame["n_conditions"].notna().any() else None,
        "median_precommencement": round(float(frame["n_precommencement"].median()), 1),
        "out": str(OUT_PATH),
    }
    (settings.SILVER_DIR / "condition_burden_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
