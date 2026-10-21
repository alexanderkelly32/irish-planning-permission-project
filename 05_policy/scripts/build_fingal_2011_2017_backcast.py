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
NORMALIZED_DIR = POLICY_ROOT / "documents" / "zoning" / "normalized"


def load_policy_module():
    path = POLICY_ROOT / "scripts" / "build_dublin_policy_pipeline.py"
    spec = importlib.util.spec_from_file_location("policy_pipeline", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def aggregate_values(series: pd.Series) -> str | pd.NA:
    values = sorted({str(item).strip() for item in series.dropna().astype(str) if str(item).strip()})
    return ";".join(values) if values else pd.NA


def build_case_gdf() -> gpd.GeoDataFrame:
    policy_module = load_policy_module()
    manifest_df = pd.read_csv(POLICY_ROOT / "source_data" / "dublin_policy_manifest.csv")
    cases = policy_module.load_dublin_cases()
    cases = policy_module.assign_policy_plan(cases, manifest_df)
    cases = cases[cases["policy_plan_key"] == "fingal_county_council__2011_2017"].copy()
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


def load_official_layer(plan_key: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(NORMALIZED_DIR / f"{plan_key}.geojson").to_crs(2157)
    gdf["zone_code_single"] = gdf["zone_code"].astype(str).str.strip()
    gdf["zone_description_single"] = gdf["zone_description"].astype(str).str.strip()
    return gdf


def build_sheet_candidates(case_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    footprints = gpd.read_file(CURRENT_DIR / "pdf_zoning_embedded_geo_footprints.geojson").to_crs(2157)
    footprints = footprints[footprints["plan_key"] == "fingal_county_council__2011_2017"].copy()
    footprints["footprint_area_sqm"] = footprints.geometry.area
    joined = gpd.sjoin(
        case_gdf[case_gdf.geometry.notna()][["case_key", "geometry"]],
        footprints[["pdf_path", "viewport_name", "footprint_area_sqm", "geometry"]],
        how="left",
        predicate="intersects",
    ).drop(columns=["index_right"])
    if joined.empty:
        return pd.DataFrame(columns=["case_key"])

    rows = []
    for case_key, group in joined.groupby("case_key", dropna=False):
        group = group[group["pdf_path"].notna()].copy()
        if group.empty:
            rows.append(
                {
                    "case_key": case_key,
                    "candidate_sheet_count": 0,
                    "candidate_sheet_paths": pd.NA,
                    "best_candidate_sheet_path": pd.NA,
                    "best_candidate_sheet_status": "no_embedded_sheet_match",
                }
            )
            continue
        group = group.sort_values(["footprint_area_sqm", "pdf_path"], ascending=[True, True])
        rows.append(
            {
                "case_key": case_key,
                "candidate_sheet_count": int(group["pdf_path"].nunique()),
                "candidate_sheet_paths": aggregate_values(group["pdf_path"]),
                "best_candidate_sheet_path": str(group.iloc[0]["pdf_path"]),
                "best_candidate_sheet_status": "unique_embedded_sheet_match" if group["pdf_path"].nunique() == 1 else "best_candidate_from_overlapping_embedded_sheets",
            }
        )
    return pd.DataFrame(rows)


def join_single_zone(case_gdf: gpd.GeoDataFrame, zone_gdf: gpd.GeoDataFrame, prefix: str) -> pd.DataFrame:
    joined = gpd.sjoin(
        case_gdf[case_gdf.geometry.notna()][["case_key", "geometry"]],
        zone_gdf[["zone_code_single", "zone_description_single", "geometry"]],
        how="left",
        predicate="intersects",
    ).drop(columns=["index_right"])
    joined = joined.rename(
        columns={
            "zone_code_single": f"{prefix}_zone_code",
            "zone_description_single": f"{prefix}_zone_description",
        }
    )
    grouped = joined.groupby("case_key", dropna=False).agg(
        {
            f"{prefix}_zone_code": aggregate_values,
            f"{prefix}_zone_description": aggregate_values,
        }
    ).reset_index()
    return grouped


def main() -> None:
    case_gdf = build_case_gdf()
    sheets_df = build_sheet_candidates(case_gdf)

    layer_2017 = load_official_layer("fingal_county_council__2017_2023")
    layer_2023 = load_official_layer("fingal_county_council__2023_2029")
    zones_2017 = join_single_zone(case_gdf, layer_2017, "official_2017_2023")
    zones_2023 = join_single_zone(case_gdf, layer_2023, "official_2023_2029")

    result = pd.DataFrame(case_gdf.drop(columns="geometry")).merge(sheets_df, on="case_key", how="left")
    result = result.merge(zones_2017, on="case_key", how="left")
    result = result.merge(zones_2023, on="case_key", how="left")
    result["later_layers_single_stable"] = (
        result["official_2017_2023_zone_code"].notna()
        & result["official_2023_2029_zone_code"].notna()
        & ~result["official_2017_2023_zone_code"].astype(str).str.contains(";", na=False)
        & ~result["official_2023_2029_zone_code"].astype(str).str.contains(";", na=False)
        & (result["official_2017_2023_zone_code"] == result["official_2023_2029_zone_code"])
    )
    result["backcast_zone_code"] = pd.NA
    result["backcast_zone_description"] = pd.NA
    result["backcast_status"] = "no_backcast"
    result["backcast_confidence"] = pd.NA
    stable_mask = result["later_layers_single_stable"]
    result.loc[stable_mask, "backcast_zone_code"] = result.loc[stable_mask, "official_2017_2023_zone_code"]
    result.loc[stable_mask, "backcast_zone_description"] = result.loc[stable_mask, "official_2017_2023_zone_description"]
    result.loc[stable_mask, "backcast_status"] = "later_official_layers_stable_backcast"
    result.loc[stable_mask, "backcast_confidence"] = "low"

    out_csv = CURRENT_DIR / "fingal_2011_2017_backcast.csv"
    result.to_csv(out_csv, index=False)

    summary = {
        "rows": int(len(result)),
        "cases_with_embedded_sheet_candidates": int(result["candidate_sheet_count"].fillna(0).gt(0).sum()),
        "cases_with_unique_embedded_sheet": int((result["best_candidate_sheet_status"] == "unique_embedded_sheet_match").sum()),
        "cases_with_overlapping_sheet_candidates": int((result["best_candidate_sheet_status"] == "best_candidate_from_overlapping_embedded_sheets").sum()),
        "cases_with_stable_later_official_layers": int(stable_mask.sum()),
        "backcast_status_counts": result["backcast_status"].value_counts(dropna=False).to_dict(),
        "backcast_zone_counts": result.loc[result["backcast_zone_code"].notna(), "backcast_zone_code"].value_counts().to_dict(),
        "output_path": str(out_csv.relative_to(ROOT)),
    }
    (CURRENT_DIR / "fingal_2011_2017_backcast_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
