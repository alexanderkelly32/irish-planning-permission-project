"""Runner: phase-polygon extraction from local planner-report drawings.

For the 74 vector-drawing pages found by the probe: extract closed polygons
from fitz path geometry (rects + closed line chains via endpoint matching),
check page-level embedded georeference (GPTS viewport, zoning precedent),
and export footprint candidates. Phase maps typically appear as many
similar-sized closed shapes on one page.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "05_policy" / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

from devrisk import settings  # noqa: E402
from prepare_pdf_derived_zoning import extract_primary_geo_viewport  # noqa: E402

REPORT_DIR = settings.ROOT / "02_development" / "source_data" / "planner_reports"
OUT_PATH = settings.SILVER_DIR / "phase_polygon_candidates.geojson"
MIN_AREA = 40.0


def closed_polygons(drawings: list, page_height: float) -> list[dict]:
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    rects: list[tuple[float, float, float, float]] = []
    for drawing in drawings:
        for item in drawing.get("items", []):
            kind = item[0]
            if kind == "re":
                rects.append(item[1])
            elif kind == "l":
                p1, p2 = (item[1].x, item[1].y), (item[2].x, item[2].y)
                if np.hypot(p2[0] - p1[0], p2[1] - p1[1]) > 0.5:
                    segments.append((p1, p2))
            elif kind == "c":
                segments.append(((item[1].x, item[1].y), (item[4].x, item[4].y)))

    polygons: list[dict] = []
    for rect in rects:
        x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
        area = abs(x1 - x0) * abs(y1 - y0)
        if area >= MIN_AREA:
            polygons.append({"coords": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], "area": area, "kind": "rect"})

    # Closed chains from line segments (endpoint union).
    adjacency: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for (p1, p2) in segments:
        key1 = (round(p1[0], 2), round(p1[1], 2))
        key2 = (round(p2[0], 2), round(p2[1], 2))
        adjacency.setdefault(key1, []).append(key2)
        adjacency.setdefault(key2, []).append(key1)
    seen: set[tuple] = set()
    for start in list(adjacency):
        for nxt in adjacency[start]:
            path = [start, nxt]
            while path[-1] in adjacency and len(path) < 40:
                candidates = [n for n in adjacency[path[-1]] if n not in path]
                if not candidates:
                    break
                path.append(candidates[0])
                if path[-1] == start:
                    break
            if len(path) >= 4 and path[-1] == start:
                poly = Polygon(path[:-1])
                if poly.is_valid and poly.area >= MIN_AREA and not poly.exterior.is_ccw:
                    key = tuple(sorted(round(p[0], 2) for p in path[:-1]))
                    if key not in seen:
                        seen.add(key)
                        polygons.append({"coords": [[p[0], page_height - p[1]] for p in path[:-1]],
                                         "area": float(poly.area), "kind": "chain"})
            break
    return polygons


if __name__ == "__main__":
    import fitz
    from pypdf import PdfReader

    name_to_path = {p.name: p for p in REPORT_DIR.rglob("*_planner_report*.pdf")}
    probe = pd.read_csv(settings.SILVER_DIR / "pdf_drawing_geometry_probe.csv")
    pages_by_pdf = probe.groupby(["pdf", "appno", "case_key"])["page"].agg(list).reset_index()

    features = []
    polygons_total = 0
    geo_pages = 0
    for _, row in pages_by_pdf.iterrows():
        pdf_path = name_to_path.get(str(row["pdf"]))
        if pdf_path is None:
            continue
        pages = [int(p) for p in row["page"]]
        try:
            with fitz.open(pdf_path) as doc:
                for page_index in pages[:6]:
                    page = doc.load_page(page_index)
                    drawings = page.get_drawings()
                    polygons = closed_polygons(drawings, page.rect.height)
                    if not polygons:
                        continue
                    polygons_total += len(polygons)
                    # page-level georef via pypdf
                    reader = PdfReader(str(pdf_path))
                    geo = None
                    try:
                        geo = extract_primary_geo_viewport(reader.pages[page_index])
                    except Exception:
                        geo = None
                    if geo:
                        geo_pages += 1
                    for i, poly in enumerate(polygons):
                        features.append({
                            "type": "Feature",
                            "properties": {
                                "appno": str(row["appno"]),
                                "case_key": str(row["case_key"]),
                                "pdf": str(row["pdf"]),
                                "page": page_index,
                                "polygon_index": i,
                                "area_pts": round(poly["area"], 1),
                                "kind": poly["kind"],
                                "has_page_georef": bool(geo),
                                "gpts": geo.get("gpts") if geo else None,
                            },
                            "geometry": {"type": "Polygon", "coordinates": [poly["coords"]]},
                        })
        except Exception:
            continue

    geojson = {"type": "FeatureCollection", "features": features}
    OUT_PATH.write_text(json.dumps(geojson), encoding="utf-8")

    frame = pd.DataFrame([f["properties"] for f in features])
    summary = {
        "polygons_extracted": polygons_total,
        "features_written": int(len(features)),
        "pages_with_georef": geo_pages,
        "estates": int(frame["case_key"].nunique()) if len(frame) else 0,
        "pages": int(frame.groupby(["pdf", "page"]).ngroups) if len(frame) else 0,
        "out": str(OUT_PATH),
    }
    if len(frame):
        summary["median_polygons_per_page"] = round(float(frame.groupby(["pdf", "page"])["polygon_index"].max().median()), 0)
    (settings.SILVER_DIR / "phase_polygon_extract_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
