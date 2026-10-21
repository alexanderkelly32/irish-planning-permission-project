"""Runner: phase-pilot shortlist + phasing-evidence probe.

Selects 30-50 multi-phase estates: confirmed BCMS links with >1 phase
number, confirmed development-level sales, authority diversity. Then probes
their planner-report PDFs for phase-boundary evidence (text-level: phase
unit ranges, phasing-plan mentions) to test whether planning documents can
supply the phase maps required for ECAD-based phase attribution.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

REPORT_DIR = settings.ROOT / "02_development" / "source_data" / "planner_reports"
PHASE_TEXT_RE = re.compile(
    r"phase\s*(1|2|3|4|5|6|7|8|one|two|three|four)[^.]{0,160}?(\d{1,3})\s*(?:no\.?s?|dwelling|units?|houses?)",
    re.IGNORECASE,
)
RANGE_RE = re.compile(r"(?:nos?\.?\s*)?(\d{1,3})\s*(?:-|to|–)\s*(\d{1,3})\s*(?:inclusive)?", re.IGNORECASE)
PHASING_PLAN_RE = re.compile(r"phasing\s*(plan|schedule|proposal)|phase\s*(boundaries|areas)|site\s*layout", re.IGNORECASE)

if __name__ == "__main__":
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    sold_devs = set(exit_labels[exit_labels["sales_linked"] > 0]["scheme_id"].astype(str))

    multi = phases.groupby("development_id").agg(
        max_phase=("phase_number", "max"),
        n_phases=("phase_number", "nunique"),
        total_houses=("houses", "sum"),
        route=("route", "first"),
        authority_any=("development_id", "first"),
    ).reset_index()
    multi = multi[multi["n_phases"] >= 2]
    multi = multi[multi["development_id"].isin(sold_devs)]
    multi = multi[multi["total_houses"].between(10, 400)]

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "PlanningAuthority", "ApplicationNumber"]].drop_duplicates("case_key")
    multi = multi.merge(reg, left_on="development_id", right_on="case_key", how="left")
    multi["appno"] = multi["ApplicationNumber"].astype(str).str.strip()

    # PDF availability per estate.
    pdf_by_app: dict[str, list[Path]] = {}
    for pdf in REPORT_DIR.rglob("*_planner_report*.pdf"):
        match = re.match(r"^(\d+)_planner_report", pdf.name)
        if match:
            pdf_by_app.setdefault(match.group(1), []).append(pdf)
    multi["n_pdfs"] = multi["appno"].map(lambda a: len(pdf_by_app.get(a, [])))
    multi = multi[multi["n_pdfs"] > 0]

    # Diversity: keep up to 3 per authority, rank by n_phases then houses.
    multi = multi.sort_values(["n_phases", "total_houses"], ascending=False)
    shortlist_rows = []
    per_authority: dict[str, int] = {}
    for _, row in multi.iterrows():
        authority = str(row["PlanningAuthority"])
        if per_authority.get(authority, 0) >= 3:
            continue
        if len(shortlist_rows) >= 45:
            break
        shortlist_rows.append(row)
        per_authority[authority] = per_authority.get(authority, 0) + 1
    shortlist = pd.DataFrame(shortlist_rows)

    # Probe the shortlist PDFs for phase-boundary evidence.
    import fitz  # noqa: E402

    evidence_rows = []
    for _, row in shortlist.iterrows():
        pdfs = pdf_by_app.get(str(row["appno"]), [])
        text = ""
        for pdf in pdfs[:4]:
            try:
                with fitz.open(pdf) as doc:
                    text += " ".join(page.get_text() for page in doc[:20])
            except Exception:
                continue
        phase_hits = len(PHASE_TEXT_RE.findall(text))
        range_hits = len(RANGE_RE.findall(text))
        plan_hits = len(PHASING_PLAN_RE.findall(text))
        evidence_rows.append({
            "development_id": str(row["development_id"]),
            "authority": str(row["PlanningAuthority"]),
            "appno": str(row["appno"]),
            "n_phases": int(row["n_phases"]),
            "total_houses": float(row["total_houses"]),
            "n_pdfs": int(row["n_pdfs"]),
            "phase_unit_mentions": phase_hits,
            "number_range_mentions": range_hits,
            "phasing_plan_mentions": plan_hits,
            "text_chars": len(text),
        })
    evidence = pd.DataFrame(evidence_rows)
    evidence.to_csv(settings.SILVER_DIR / "phase_pilot_shortlist.csv", index=False)

    summary = {
        "multi_phase_estates_with_sales_and_pdfs": int(len(multi)),
        "shortlisted": int(len(evidence)),
        "authorities_covered": int(evidence["authority"].nunique()),
        "with_phase_unit_mentions": int((evidence["phase_unit_mentions"] > 0).sum()),
        "with_number_ranges": int((evidence["number_range_mentions"] > 0).sum()),
        "with_phasing_plan_mentions": int((evidence["phasing_plan_mentions"] > 0).sum()),
        "median_pdfs_per_estate": round(float(evidence["n_pdfs"].median()), 1),
        "out": str(settings.SILVER_DIR / "phase_pilot_shortlist.csv"),
    }
    (settings.SILVER_DIR / "phase_pilot_shortlist_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
