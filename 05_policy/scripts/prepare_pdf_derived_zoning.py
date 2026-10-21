#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import fitz
import geopandas as gpd
import pandas as pd
from pypdf import PdfReader
from pyproj import Transformer
from shapely.geometry import Polygon


ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = ROOT / "05_policy"
CURRENT_DIR = POLICY_ROOT / "current"
RAW_DIR = POLICY_ROOT / "documents" / "zoning" / "raw"
PREVIEW_DIR = POLICY_ROOT / "documents" / "zoning" / "previews"

PDF_PLAN_SPECS = [
    ("Dublin City Council", "dublin_city_council__2016_2022", RAW_DIR / "dublin_city_council" / "2016_2022"),
    ("South Dublin County Council", "south_dublin_county_council__2016_2022", RAW_DIR / "south_dublin_county_council" / "2016_2022"),
    ("South Dublin County Council", "south_dublin_county_council__2010_2016", RAW_DIR / "south_dublin_county_council" / "2010_2016"),
    ("South Dublin County Council", "south_dublin_county_council__2004_2010", RAW_DIR / "south_dublin_county_council" / "2004_2010"),
    ("Fingal County Council", "fingal_county_council__2011_2017", RAW_DIR / "fingal_county_council" / "2011_2017"),
]


def ensure_dirs() -> None:
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def relative_to_root(path: Path) -> str:
    return str(path.relative_to(ROOT))


def pdfs_for_plan(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    return sorted(raw_dir.glob("*.pdf"))


def safe_metadata_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_primary_geo_viewport(page) -> dict | None:
    vp = page.get("/VP")
    if not vp:
        return None
    entries = vp if isinstance(vp, list) else [vp]
    for entry in entries:
        obj = entry.get_object()
        measure_ref = obj.get("/Measure")
        if measure_ref is None:
            continue
        measure = measure_ref.get_object()
        if str(measure.get("/Subtype")) != "/GEO":
            continue
        return {
            "viewport_name": safe_metadata_value(obj.get("/Name")),
            "bbox": [float(item) for item in obj.get("/BBox", [])],
            "gpts": [float(item) for item in measure.get("/GPTS", [])],
            "lpts": [float(item) for item in measure.get("/LPTS", [])],
            "bounds": [float(item) for item in measure.get("/Bounds", [])],
            "gcs_wkt": safe_metadata_value((measure.get("/GCS") or {}).get_object().get("/WKT")) if measure.get("/GCS") else None,
        }
    return None


def polygon_from_gpts(gpts: list[float]) -> Polygon | None:
    if len(gpts) != 8:
        return None
    coords = [
        (gpts[1], gpts[0]),
        (gpts[3], gpts[2]),
        (gpts[5], gpts[4]),
        (gpts[7], gpts[6]),
        (gpts[1], gpts[0]),
    ]
    return Polygon(coords)


def transform_polygon_to_itm(polygon: Polygon) -> Polygon:
    transformer = Transformer.from_crs(4326, 2157, always_xy=True)
    coords = [transformer.transform(x, y) for x, y in polygon.exterior.coords]
    return Polygon(coords)


def render_preview(pdf_path: Path, authority: str, plan_key: str) -> Path:
    preview_dir = PREVIEW_DIR / plan_key
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"{pdf_path.stem}.png"
    if preview_path.exists():
        return preview_path
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2), alpha=False)
    pix.save(preview_path)
    doc.close()
    return preview_path


def build_manifest() -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    manifest_rows: list[dict] = []
    footprint_rows: list[dict] = []
    for authority, plan_key, raw_dir in PDF_PLAN_SPECS:
        for pdf_path in pdfs_for_plan(raw_dir):
            reader = PdfReader(str(pdf_path))
            page = reader.pages[0]
            preview_path = render_preview(pdf_path, authority, plan_key)
            geo = extract_primary_geo_viewport(page)
            row = {
                "authority": authority,
                "plan_key": plan_key,
                "pdf_path": relative_to_root(pdf_path),
                "preview_path": relative_to_root(preview_path),
                "page_count": len(reader.pages),
                "page_width_pts": float(page.mediabox.width),
                "page_height_pts": float(page.mediabox.height),
                "title": safe_metadata_value(reader.metadata.get("/Title")) if reader.metadata else None,
                "creator": safe_metadata_value(reader.metadata.get("/Creator")) if reader.metadata else None,
                "producer": safe_metadata_value(reader.metadata.get("/Producer")) if reader.metadata else None,
                "creation_date": safe_metadata_value(reader.metadata.get("/CreationDate")) if reader.metadata else None,
                "has_embedded_geo": bool(geo),
                "embedded_geo_method": "viewport_measure_gpts" if geo else None,
                "viewport_name": geo.get("viewport_name") if geo else None,
                "bbox_json": json.dumps(geo.get("bbox")) if geo else None,
                "gpts_json": json.dumps(geo.get("gpts")) if geo else None,
                "gcs_wkt": geo.get("gcs_wkt") if geo else None,
                "derivation_status": "embedded_geo_ready" if geo else "manual_georef_needed",
            }
            manifest_rows.append(row)
            if geo and geo.get("gpts"):
                polygon = polygon_from_gpts(geo["gpts"])
                if polygon is not None:
                    polygon_itm = transform_polygon_to_itm(polygon)
                    footprint_rows.append(
                        {
                            "authority": authority,
                            "plan_key": plan_key,
                            "pdf_path": relative_to_root(pdf_path),
                            "viewport_name": geo.get("viewport_name"),
                            "gcs_wkt": geo.get("gcs_wkt"),
                            "geometry": polygon,
                            "itm_bbox_min_x": polygon_itm.bounds[0],
                            "itm_bbox_min_y": polygon_itm.bounds[1],
                            "itm_bbox_max_x": polygon_itm.bounds[2],
                            "itm_bbox_max_y": polygon_itm.bounds[3],
                        }
                    )
    manifest_df = pd.DataFrame(manifest_rows).sort_values(["authority", "plan_key", "pdf_path"]).reset_index(drop=True)
    footprint_gdf = gpd.GeoDataFrame(footprint_rows, geometry="geometry", crs=4326)
    return manifest_df, footprint_gdf


def build_manual_queue(manifest_df: pd.DataFrame) -> pd.DataFrame:
    queue = manifest_df[manifest_df["has_embedded_geo"] == False].copy()
    queue["manual_georef_status"] = "pending"
    queue["manual_control_points_collected"] = 0
    queue["manual_output_geojson_path"] = pd.NA
    queue["notes"] = pd.NA
    return queue[
        [
            "authority",
            "plan_key",
            "pdf_path",
            "preview_path",
            "title",
            "creator",
            "manual_georef_status",
            "manual_control_points_collected",
            "manual_output_geojson_path",
            "notes",
        ]
    ].reset_index(drop=True)


def main() -> None:
    ensure_dirs()
    manifest_df, footprint_gdf = build_manifest()
    manifest_path = CURRENT_DIR / "pdf_zoning_sources_manifest.csv"
    manifest_df.to_csv(manifest_path, index=False)

    manual_queue = build_manual_queue(manifest_df)
    manual_queue_path = CURRENT_DIR / "pdf_zoning_manual_georef_queue.csv"
    manual_queue.to_csv(manual_queue_path, index=False)

    footprints_path = CURRENT_DIR / "pdf_zoning_embedded_geo_footprints.geojson"
    if footprint_gdf.empty:
        footprints_path.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
    else:
        footprint_gdf.to_file(footprints_path, driver="GeoJSON")

    summary = {
        "total_pdf_sources": int(len(manifest_df)),
        "embedded_geo_ready": int(manifest_df["has_embedded_geo"].sum()),
        "manual_georef_needed": int((~manifest_df["has_embedded_geo"]).sum()),
        "authorities": manifest_df["authority"].value_counts().to_dict(),
        "plan_keys": manifest_df["plan_key"].value_counts().to_dict(),
        "manifest_path": relative_to_root(manifest_path),
        "manual_georef_queue_path": relative_to_root(manual_queue_path),
        "embedded_geo_footprints_path": relative_to_root(footprints_path),
    }
    (CURRENT_DIR / "pdf_zoning_prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
