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


def load_case_points() -> pd.DataFrame:
    path = CURRENT_DIR / "dublin_case_points_from_base.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing case points file: {path}")
    return pd.read_csv(path, low_memory=False)


def load_zoning_layers() -> dict[str, gpd.GeoDataFrame]:
    layers: dict[str, gpd.GeoDataFrame] = {}
    for path in NORMALIZED_DIR.glob("*.geojson"):
        gdf = gpd.read_file(path)
        if gdf.empty:
            continue
        gdf = gdf.to_crs(2157)
        plan_key = str(gdf.iloc[0]["plan_key"])
        layers[plan_key] = gdf
    return layers


def build_case_geodataframe(cases: pd.DataFrame) -> gpd.GeoDataFrame:
    geometry = [
        Point(x, y) if pd.notna(x) and pd.notna(y) else None
        for x, y in zip(cases["ITMEasting"], cases["ITMNorthing"])
    ]
    return gpd.GeoDataFrame(cases.copy(), geometry=geometry, crs=2157)


def collapse_case_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, group in df.groupby("case_key", dropna=False):
        base = group.iloc[0].copy()
        statuses = set(group["zoning_join_status"].dropna().astype(str))
        zone_codes = sorted({str(item) for item in group["zone_code"].dropna().astype(str) if str(item).strip()})
        zone_descs = sorted({str(item) for item in group["zone_description"].dropna().astype(str) if str(item).strip()})
        if "matched" in statuses:
            status = "matched" if len(zone_codes) <= 1 else "multiple_polygon_matches"
        elif "no_polygon_match" in statuses:
            status = "no_polygon_match"
        elif "missing_case_geometry" in statuses:
            status = "missing_case_geometry"
        else:
            status = "no_layer_for_plan_key"
        base["zoning_join_status"] = status
        base["zone_code"] = ";".join(zone_codes) if zone_codes else pd.NA
        base["zone_description"] = "; ".join(zone_descs) if zone_descs else pd.NA
        rows.append(base)
    return pd.DataFrame(rows)


def main() -> None:
    policy_module = load_policy_module()
    manifest_df = pd.read_csv(POLICY_ROOT / "source_data" / "dublin_policy_manifest.csv")
    cases = policy_module.load_dublin_cases()
    cases = policy_module.assign_policy_plan(cases, manifest_df)
    points = load_case_points()[["case_key", "ITMEasting", "ITMNorthing"]]
    cases = cases.merge(points, on="case_key", how="left", suffixes=("", "_base"))
    if "ITMEasting_base" in cases.columns:
        cases["ITMEasting"] = cases["ITMEasting_base"].combine_first(cases.get("ITMEasting"))
        cases["ITMNorthing"] = cases["ITMNorthing_base"].combine_first(cases.get("ITMNorthing"))
    case_gdf = build_case_geodataframe(cases)
    layers = load_zoning_layers()

    joined_frames = []
    for plan_key, subset in case_gdf.groupby("policy_plan_key", dropna=False):
        if plan_key not in layers:
            temp = subset.copy()
            temp["zoning_join_status"] = "no_layer_for_plan_key"
            temp["zone_code"] = pd.NA
            temp["zone_description"] = pd.NA
            joined_frames.append(pd.DataFrame(temp.drop(columns="geometry")))
            continue
        temp = subset[subset.geometry.notna()].copy()
        missing_geom = subset[subset.geometry.isna()].copy()
        zone_gdf = layers[plan_key]
        joined = gpd.sjoin(
            temp,
            zone_gdf[["zone_code", "zone_description", "geometry"]],
            how="left",
            predicate="intersects",
        ).drop(columns=["index_right"])
        joined["zoning_join_status"] = joined["zone_code"].notna().map({True: "matched", False: "no_polygon_match"})
        if not missing_geom.empty:
            missing_geom["zoning_join_status"] = "missing_case_geometry"
            missing_geom["zone_code"] = pd.NA
            missing_geom["zone_description"] = pd.NA
            joined_frames.append(pd.DataFrame(missing_geom.drop(columns="geometry")))
        joined_frames.append(pd.DataFrame(joined.drop(columns="geometry")))

    result = pd.concat(joined_frames, ignore_index=True)
    result = collapse_case_rows(result)
    out_csv = CURRENT_DIR / "dublin_case_zoning_join_available_layers.csv"
    result.to_csv(out_csv, index=False)

    summary = {
        "rows": int(len(result)),
        "matched": int((result["zoning_join_status"] == "matched").sum()),
        "multiple_polygon_matches": int((result["zoning_join_status"] == "multiple_polygon_matches").sum()),
        "no_layer_for_plan_key": int((result["zoning_join_status"] == "no_layer_for_plan_key").sum()),
        "no_polygon_match": int((result["zoning_join_status"] == "no_polygon_match").sum()),
        "missing_case_geometry": int((result["zoning_join_status"] == "missing_case_geometry").sum()),
        "matched_by_plan_key": result.loc[result["zoning_join_status"] == "matched", "policy_plan_key"].value_counts().to_dict(),
    }
    (CURRENT_DIR / "dublin_case_zoning_join_available_layers_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
