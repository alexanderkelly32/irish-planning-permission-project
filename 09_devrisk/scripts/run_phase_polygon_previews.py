"""Runner: render phase-polygon previews for visual verification.

Draws the extracted polygon candidates over each source page as PNG
previews, one per page, for the user to confirm whether they are phase
blocks / site layouts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import fitz  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

REPORT_DIR = settings.ROOT / "02_development" / "source_data" / "planner_reports"
PREVIEW_DIR = settings.ROOT / "09_devrisk" / "data" / "silver" / "phase_polygon_previews"

if __name__ == "__main__":
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    name_to_path = {p.name: p for p in REPORT_DIR.rglob("*_planner_report*.pdf")}
    geojson = json.loads((settings.SILVER_DIR / "phase_polygon_candidates.geojson").read_text(encoding="utf-8"))

    pages: dict[tuple[str, int], list] = {}
    for feature in geojson["features"]:
        props = feature["properties"]
        pages.setdefault((props["pdf"], props["page"]), []).append(feature)

    rendered = 0
    for (pdf_name, page_index), features in pages.items():
        pdf_path = name_to_path.get(pdf_name)
        if pdf_path is None:
            continue
        with fitz.open(pdf_path) as doc:
            page = doc.load_page(page_index)
            page_height = page.rect.height
            for feature in features:
                coords = feature["geometry"]["coordinates"][0]
                points = [fitz.Point(x, page_height - y) for x, y in coords]
                color = (0, 0.8, 0) if feature["properties"]["kind"] == "rect" else (0, 0, 0.9)
                try:
                    page.draw_polyline(points + [points[0]], color=color, width=0.8, overlay=True)
                except Exception:
                    continue
            pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False)
            out = PREVIEW_DIR / f"{Path(pdf_name).stem}_p{page_index}.png"
            pix.save(out)
            rendered += 1

    summary = {"previews_rendered": rendered, "out_dir": str(PREVIEW_DIR)}
    (settings.SILVER_DIR / "phase_polygon_previews_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
