"""Analyst override store and PDF rendering (engine n).

Overrides: append-only JSON records per scheme - original value, replacement,
reason, evidence, reviewer, timestamp (product brief 9). The model value is
never overwritten in the payload; overrides are applied at render time and
always displayed as overrides.

PDF: renders the markdown report via fpdf2 (vendored in .vendor), branded,
with the research-prototype banner on the first page and module availability.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import settings
from ..provenance import utc_now_iso

OVERRIDES_DIR = settings.SILVER_DIR / "overrides"


def record_override(
    scheme_id: str,
    target: str,
    original_value: Any,
    replacement_value: Any,
    reason: str,
    evidence: str,
    reviewer: str,
    overrides_dir: Path | None = None,
) -> dict[str, Any]:
    overrides_dir = overrides_dir or OVERRIDES_DIR
    overrides_dir.mkdir(parents=True, exist_ok=True)
    path = overrides_dir / f"{_safe(scheme_id)}.json"
    records: list[dict[str, Any]] = []
    if path.exists():
        records = json.loads(path.read_text(encoding="utf-8"))
    record = {
        "target": target,
        "original_value": original_value,
        "replacement_value": replacement_value,
        "reason": reason,
        "evidence": evidence,
        "reviewer": reviewer,
        "recorded_at": utc_now_iso(),
    }
    records.append(record)
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return record


def load_overrides(scheme_id: str, overrides_dir: Path | None = None) -> list[dict[str, Any]]:
    overrides_dir = overrides_dir or OVERRIDES_DIR
    path = overrides_dir / f"{_safe(scheme_id)}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def apply_overrides(payload: dict[str, Any], overrides: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply recorded overrides to render targets (never mutates model values)."""
    applied = dict(payload)
    for override in overrides:
        target = override["target"]
        if target == "refusal_probability" and "planning_outcome" in applied:
            applied["planning_outcome"]["refusal_probability_override"] = override["replacement_value"]
            applied["planning_outcome"]["grant_probability_override"] = round(1.0 - float(override["replacement_value"]), 4)
        elif target == "fi_probability" and "friction" in applied:
            applied["friction"]["fi_probability_override"] = override["replacement_value"]
    applied["overrides"] = overrides
    return applied


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def render_pdf(markdown_text: str, *, scheme_id: str, out_path: Path | None = None) -> Path:
    """Minimal fpdf2 renderer: banner + section headings + body lines."""
    import sys
    import textwrap

    vendor = settings.ROOT / ".vendor"
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    from fpdf import FPDF

    out_path = out_path or (settings.SILVER_DIR / "reports" / f"{_safe(scheme_id)}_report.pdf")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    pdf.add_page()
    pdf.set_font("helvetica", "B", 10)
    pdf.multi_cell(0, 5, "RESEARCH PROTOTYPE - NOT FOR LENDING, INVESTMENT OR PLANNING DECISIONS.")
    pdf.set_font("helvetica", "", 8)
    pdf.ln(2)

    width = 180
    in_code = False
    for line in markdown_text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            pdf.set_font("courier", "", 7)
            for chunk in textwrap.wrap(stripped, width=120, break_long_words=True):
                pdf.multi_cell(width, 4, chunk)
            pdf.set_font("helvetica", "", 8)
            continue
        if stripped.startswith("# "):
            pdf.set_font("helvetica", "B", 13)
            for chunk in textwrap.wrap(stripped[2:], width=95, break_long_words=True):
                pdf.multi_cell(width, 7, chunk)
            pdf.set_font("helvetica", "", 8)
        elif stripped.startswith("## "):
            pdf.set_font("helvetica", "B", 10)
            for chunk in textwrap.wrap(stripped[3:], width=115, break_long_words=True):
                pdf.multi_cell(width, 6, chunk)
            pdf.set_font("helvetica", "", 8)
        elif stripped.startswith("- "):
            for chunk in textwrap.wrap(stripped[2:], width=130, break_long_words=True):
                pdf.multi_cell(width, 4.5, "  " + chunk)
        elif stripped.startswith("> "):
            pdf.set_font("helvetica", "I", 8)
            for chunk in textwrap.wrap(stripped[2:], width=130, break_long_words=True):
                pdf.multi_cell(width, 4.5, chunk)
            pdf.set_font("helvetica", "", 8)
        elif stripped.strip():
            for chunk in textwrap.wrap(stripped, width=130, break_long_words=True):
                pdf.multi_cell(width, 4.5, chunk)

    pdf.output(str(out_path))
    return out_path
