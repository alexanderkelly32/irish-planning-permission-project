"""Runner: PDF drawing-geometry probe on the local corpus (corrected plan #1).

For multi-phase estates with local planner-report PDFs: extract page-level
vector drawings (fitz get_drawings), flag pages dense in vector paths as
candidate site-layout/phasing drawings, and save page-level geometry
summaries. Tests whether the phase maps are recoverable from what we
already hold, before any scraping.
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

REPORT_DIR = settings.ROOT / "02_development" / "source_data" / "planner_reports"
MIN_PATHS = 50


if __name__ == "__main__":
    import fitz

    shortlist = pd.read_csv(settings.SILVER_DIR / "phase_pilot_shortlist.csv")
    multi = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    multi_devs = set(multi["development_id"].astype(str))

    pdf_by_app: dict[str, list[Path]] = {}
    for pdf in REPORT_DIR.rglob("*_planner_report*.pdf"):
        match = re.match(r"^(\d+)_planner_report", pdf.name)
        if match:
            pdf_by_app.setdefault(match.group(1), []).append(pdf)

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    app_to_case = dict(zip(register["ApplicationNumber"].astype(str), register["case_key"].astype(str)))

    rows = []
    scanned = 0
    for appno, pdfs in pdf_by_app.items():
        case_key = app_to_case.get(appno)
        if case_key is None or case_key not in multi_devs:
            continue
        for pdf in pdfs[:3]:
            try:
                with fitz.open(pdf) as doc:
                    for page_index, page in enumerate(doc):
                        if page_index >= 30:
                            break
                        drawings = page.get_drawings()
                        if len(drawings) < MIN_PATHS:
                            continue
                        page_rect = page.rect
                        rows.append({
                            "appno": appno,
                            "case_key": case_key,
                            "pdf": pdf.name,
                            "page": page_index,
                            "vector_path_count": len(drawings),
                            "page_width": round(page_rect.width, 1),
                            "page_height": round(page_rect.height, 1),
                        })
                scanned += 1
            except Exception:
                continue

    frame = pd.DataFrame(rows)
    frame.to_csv(settings.SILVER_DIR / "pdf_drawing_geometry_probe.csv", index=False)
    summary = {
        "pdfs_scanned": scanned,
        "multi_phase_estates_with_local_pdfs": int(frame["case_key"].nunique()) if len(frame) else 0,
        "pages_with_vector_drawings": int(len(frame)),
        "median_paths_per_page": round(float(frame["vector_path_count"].median()), 0) if len(frame) else None,
        "max_paths": int(frame["vector_path_count"].max()) if len(frame) else None,
        "out": str(settings.SILVER_DIR / "pdf_drawing_geometry_probe.csv"),
    }
    (settings.SILVER_DIR / "pdf_drawing_geometry_probe_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
