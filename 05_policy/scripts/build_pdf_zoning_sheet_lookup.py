#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = ROOT / "05_policy"
CURRENT_DIR = POLICY_ROOT / "current"


def load_policy_module():
    path = POLICY_ROOT / "scripts" / "build_dublin_policy_pipeline.py"
    spec = importlib.util.spec_from_file_location("policy_pipeline", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_case_gdf() -> gpd.GeoDataFrame:
    policy_module = load_policy_module()
    manifest_df = pd.read_csv(POLICY_ROOT / "source_data" / "dublin_policy_manifest.csv")
    cases = policy_module.load_dublin_cases()
    cases = policy_module.assign_policy_plan(cases, manifest_df)
    points = pd.read_csv(CURRENT_DIR / "dublin_case_points_from_base.csv", low_memory=False)[["case_key", "ITMEasting", "ITMNorthing"]]
    cases = cases.merge(points, on="case_key", how="left", suffixes=("", "_base"))
    if "ITMEasting_base" in cases.columns:
        cases["ITMEasting"] = cases["ITMEasting_base"].combine_first(cases.get("ITMEasting"))
        cases["ITMNorthing"] = cases["ITMNorthing_base"].combine_first(cases.get("ITMNorthing"))
    geometry = [
        Point(x, y) if pd.notna(x) and pd.notna(y) else None
        for x, y in zip(cases["ITMEasting"], cases["ITMNorthing"])
    ]
    return gpd.GeoDataFrame(cases, geometry=geometry, crs=2157)


def aggregate_values(series: pd.Series) -> str | pd.NA:
    values = sorted({str(item).strip() for item in series.dropna().astype(str) if str(item).strip()})
    return ";".join(values) if values else pd.NA


def collapse_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, group in df.groupby("case_key", dropna=False):
        base = group.iloc[0].copy()
        for column in ["pdf_path", "viewport_name"]:
            base[column] = aggregate_values(group[column])
        if pd.notna(base["pdf_path"]) and ";" in str(base["pdf_path"]):
            base["sheet_lookup_status"] = "multiple_candidate_sheets"
        elif pd.notna(base["pdf_path"]):
            base["sheet_lookup_status"] = "matched_sheet"
        elif pd.isna(base["geometry"]):
            base["sheet_lookup_status"] = "missing_case_geometry"
        else:
            base["sheet_lookup_status"] = "no_embedded_georef_sheet"
        rows.append(base)
    result = pd.DataFrame(rows)
    return result.drop(columns=["geometry"])


def main() -> None:
    footprint_path = CURRENT_DIR / "pdf_zoning_embedded_geo_footprints.geojson"
    if not footprint_path.exists():
        raise FileNotFoundError(f"Missing embedded GeoPDF footprint file: {footprint_path}")
    footprints = gpd.read_file(footprint_path)
    if footprints.empty:
        raise ValueError("Embedded GeoPDF footprint file is empty")
    footprints = footprints.to_crs(2157)

    cases = build_case_gdf()
    joined_frames = []
    for plan_key, subset in cases.groupby("policy_plan_key", dropna=False):
        candidate_footprints = footprints[footprints["plan_key"] == plan_key]
        if candidate_footprints.empty:
            temp = subset.copy()
            temp["pdf_path"] = pd.NA
            temp["viewport_name"] = pd.NA
            joined_frames.append(temp)
            continue
        temp = subset[subset.geometry.notna()].copy()
        missing_geom = subset[subset.geometry.isna()].copy()
        joined = gpd.sjoin(
            temp,
            candidate_footprints[["pdf_path", "viewport_name", "geometry"]],
            how="left",
            predicate="intersects",
        ).drop(columns=["index_right"])
        joined_frames.append(joined)
        if not missing_geom.empty:
            missing_geom["pdf_path"] = pd.NA
            missing_geom["viewport_name"] = pd.NA
            joined_frames.append(missing_geom)
    result = gpd.GeoDataFrame(pd.concat(joined_frames, ignore_index=True), geometry="geometry", crs=2157)
    collapsed = collapse_rows(result)
    out_csv = CURRENT_DIR / "pdf_zoning_case_sheet_lookup.csv"
    collapsed.to_csv(out_csv, index=False)
    summary = {
        "rows": int(len(collapsed)),
        "matched_sheet": int((collapsed["sheet_lookup_status"] == "matched_sheet").sum()),
        "multiple_candidate_sheets": int((collapsed["sheet_lookup_status"] == "multiple_candidate_sheets").sum()),
        "no_embedded_georef_sheet": int((collapsed["sheet_lookup_status"] == "no_embedded_georef_sheet").sum()),
        "missing_case_geometry": int((collapsed["sheet_lookup_status"] == "missing_case_geometry").sum()),
        "matched_by_plan_key": collapsed.loc[collapsed["sheet_lookup_status"].isin(["matched_sheet", "multiple_candidate_sheets"]), "policy_plan_key"].value_counts().to_dict(),
    }
    (CURRENT_DIR / "pdf_zoning_case_sheet_lookup_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
