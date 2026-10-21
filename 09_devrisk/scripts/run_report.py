"""Runner: prototype research report for one scheme.

Usage:
  python 09_devrisk\\scripts\\run_report.py "<case_key>"          # markdown to stdout
  python 09_devrisk\\scripts\\run_report.py "<case_key>" --pdf    # also write PDF
"""
from __future__ import annotations

import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[2] / ".vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from devrisk.reporting.prototype_report import build_report, render_markdown  # noqa: E402

if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:]]
    case_key = args[0] if args and not args[0].startswith("--") else None
    case_key = case_key or "Carlow County Council__19263"
    payload = build_report(case_key)
    markdown = render_markdown(payload)
    print(markdown)
    if "--pdf" in args:
        from devrisk.reporting.analyst_review import render_pdf

        path = render_pdf(markdown, scheme_id=case_key)
        print(f"PDF -> {path}")
