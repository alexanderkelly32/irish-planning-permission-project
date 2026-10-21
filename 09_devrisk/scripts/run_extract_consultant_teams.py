"""Runner: E1 - professional team extraction from planner-report PDFs.

Scans the 5,308 planner-report PDFs, extracts role->firm name pairs from
the first pages (agent/architect/engineer/consultant/contractor/solicitor
sections), writes consultant_mentions.csv. Background-friendly,
resume-safe per PDF directory listing.
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
OUT_PATH = settings.SILVER_DIR / "consultant_mentions.csv"
STATE_PATH = settings.SILVER_DIR / "consultant_extract_state.json"

ROLE_RE = re.compile(
    r"(planning\s+consultant|planning\s+agent|agent|architect|architects|"
    r"civil\s+engineer|structural\s+engineer|engineer|engineering|"
    r"transport\s+consultant|traffic\s+consultant|landscape\s+architect|"
    r"ecologist|environmental\s+consultant|contractor|builder|solicitor|"
    r"assigned\s+certifier|fire\s+consultant|mechanical\s+engineer|"
    r"electrical\s+engineer|quantity\s+surveyor)",
    re.IGNORECASE,
)
NAME_RE = re.compile(
    r"((?:[A-Z][A-Za-z0-9&.'\-]+(?:\s+(?:&|and)\s+[A-Z][A-Za-z0-9&.'\-]+)?)"
    r"(?:\s+(?:Ltd|Limited|LLP|Architects|Engineering|Consultants|Consulting|"
    r"Engineers|Partnership|Associates|Planning|Group|Developments))?)",
)


def extract_from_text(text: str) -> list[dict]:
    mentions = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 200:
            continue
        match = ROLE_RE.search(line)
        if not match:
            continue
        role = match.group(1).lower()
        remainder = line[match.end():]
        name_match = NAME_RE.search(remainder)
        if not name_match:
            name_match = NAME_RE.search(line[:match.start()])
        if not name_match:
            continue
        name = name_match.group(1).strip(" ,:;")
        if len(name) < 3 or name.lower() in ("the", "and", "for", "applicant", "site"):
            continue
        mentions.append({"role": role, "name": name})
    return mentions


if __name__ == "__main__":
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"done": []}
    pdfs = sorted(REPORT_DIR.rglob("*_planner_report*.pdf"))
    done = set(state["done"])
    rows = []
    app_re = re.compile(r"^(\d+)_planner_report")
    for i, pdf in enumerate(pdfs):
        if str(pdf) in done:
            continue
        appno_match = app_re.match(pdf.name)
        appno = appno_match.group(1) if appno_match else pdf.stem[:20]
        try:
            with fitz.open(pdf) as doc:
                text = " ".join(page.get_text() for page in doc[:4])
            mentions = extract_from_text(text)
            for mention in mentions:
                rows.append({"appno": appno, "pdf": pdf.name, **mention})
        except Exception:
            pass
        state["done"].append(str(pdf))
        if i % 500 == 0:
            STATE_PATH.write_text(json.dumps(state))
            print(f"processed {i}", flush=True)
    STATE_PATH.write_text(json.dumps(state))
    import pandas as pd

    frame = pd.DataFrame(rows)
    frame.to_csv(OUT_PATH, index=False)
    print(json.dumps({"pdfs": len(pdfs), "mentions": len(rows),
                      "pdfs_with_mentions": int(frame["pdf"].nunique()) if len(frame) else 0,
                      "out": str(OUT_PATH)}, indent=2))
