#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
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


def join_single_layer(case_gdf: gpd.GeoDataFrame, zone_gdf: gpd.GeoDataFrame, prefix: str) -> pd.DataFrame:
    temp = case_gdf[case_gdf.geometry.notna()].copy()
    if temp.empty:
        return pd.DataFrame(columns=["case_key", f"{prefix}_zone_code", f"{prefix}_zone_description"])
    joined = gpd.sjoin(
        temp,
        zone_gdf[["zone_code", "zone_description", "geometry"]],
        how="left",
        predicate="intersects",
    ).drop(columns=["index_right"])
    joined = joined.rename(
        columns={
            "zone_code": f"{prefix}_zone_code",
            "zone_description": f"{prefix}_zone_description",
        }
    )
    return pd.DataFrame(joined.drop(columns="geometry"))


def aggregate_values(series: pd.Series) -> str | pd.NA:
    values = sorted({str(item).strip() for item in series.dropna().astype(str) if str(item).strip()})
    return ";".join(values) if values else pd.NA


def canonical_zone_code(value: object) -> str | pd.NA:
    if value is None or pd.isna(value):
        return pd.NA
    match = re.search(r"\b(Z\d+)\b", str(value))
    return match.group(1) if match else str(value).strip() or pd.NA


def collapse_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, group in df.groupby("case_key", dropna=False):
        base = group.iloc[0].copy()
        for column in [
            "zone_code",
            "zone_description",
            "reference_before_zone_code",
            "reference_before_zone_description",
            "reference_after_zone_code",
            "reference_after_zone_description",
        ]:
            if column in group.columns:
                base[column] = aggregate_values(group[column])
        statuses = set(group["zoning_status"].dropna().astype(str))
        zone_code_value = base.get("zone_code")
        has_multiple_codes = pd.notna(zone_code_value) and ";" in str(zone_code_value)
        if "official_multiple_polygon_matches" in statuses or ("official_matched" in statuses and has_multiple_codes):
            status = "official_multiple_polygon_matches"
        elif "official_matched" in statuses:
            status = "official_matched"
        elif "inferred_stable_between_reference_layers" in statuses:
            status = "inferred_stable_between_reference_layers"
        elif "no_polygon_match" in statuses:
            status = "no_polygon_match"
        elif "missing_case_geometry" in statuses:
            status = "missing_case_geometry"
        else:
            status = "no_layer_for_plan_key"
        base["zoning_status"] = status
        rows.append(base)
    return pd.DataFrame(rows)


def build_official_join(case_gdf: gpd.GeoDataFrame, layers: dict[str, gpd.GeoDataFrame]) -> pd.DataFrame:
    joined_frames = []
    for plan_key, subset in case_gdf.groupby("policy_plan_key", dropna=False):
        if plan_key not in layers:
            temp = subset.copy()
            temp["zoning_status"] = "no_layer_for_plan_key"
            temp["zone_code"] = pd.NA
            temp["zone_description"] = pd.NA
            temp["zoning_source_type"] = pd.NA
            temp["zoning_source_plan_keys"] = pd.NA
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
        joined["zoning_status"] = joined["zone_code"].notna().map({True: "official_matched", False: "no_polygon_match"})
        joined["zoning_source_type"] = joined["zone_code"].notna().map({True: "official", False: pd.NA})
        joined["zoning_source_plan_keys"] = joined["zone_code"].notna().map({True: plan_key, False: pd.NA})
        if not missing_geom.empty:
            missing_geom["zoning_status"] = "missing_case_geometry"
            missing_geom["zone_code"] = pd.NA
            missing_geom["zone_description"] = pd.NA
            missing_geom["zoning_source_type"] = pd.NA
            missing_geom["zoning_source_plan_keys"] = pd.NA
            joined_frames.append(pd.DataFrame(missing_geom.drop(columns="geometry")))
        joined_frames.append(pd.DataFrame(joined.drop(columns="geometry")))
    return pd.concat(joined_frames, ignore_index=True)


def apply_dcc_stability_inference(result: pd.DataFrame, case_gdf: gpd.GeoDataFrame, layers: dict[str, gpd.GeoDataFrame]) -> pd.DataFrame:
    before_key = "dublin_city_council__2011_2017_reference"
    after_key = "dublin_city_council__2022_2028"
    target_key = "dublin_city_council__2016_2022"
    if before_key not in layers or after_key not in layers:
        return result

    mask = (
        (result["policy_plan_key"] == target_key)
        & (result["zoning_status"] == "no_layer_for_plan_key")
        & result["case_key"].notna()
    )
    target_case_keys = set(result.loc[mask, "case_key"].astype(str))
    if not target_case_keys:
        return result

    target_cases = case_gdf[case_gdf["case_key"].astype(str).isin(target_case_keys)].copy()
    target_cases = target_cases[target_cases.geometry.notna()].copy()
    if target_cases.empty:
        return result

    before_join = join_single_layer(target_cases, layers[before_key], "reference_before")
    after_join = join_single_layer(target_cases, layers[after_key], "reference_after")
    compare = target_cases.drop(columns="geometry").merge(before_join, on="case_key", how="left").merge(after_join, on="case_key", how="left")
    compare = compare.groupby("case_key", dropna=False).agg(
        {
            "reference_before_zone_code": aggregate_values,
            "reference_before_zone_description": aggregate_values,
            "reference_after_zone_code": aggregate_values,
            "reference_after_zone_description": aggregate_values,
        }
    ).reset_index()
    compare["reference_before_zone_code_canonical"] = compare["reference_before_zone_code"].map(canonical_zone_code)
    compare["reference_after_zone_code_canonical"] = compare["reference_after_zone_code"].map(canonical_zone_code)
    compare["stable_same_single_zone"] = (
        compare["reference_before_zone_code_canonical"].notna()
        & compare["reference_after_zone_code_canonical"].notna()
        & ~compare["reference_before_zone_code"].astype(str).str.contains(";", na=False)
        & ~compare["reference_after_zone_code"].astype(str).str.contains(";", na=False)
        & (compare["reference_before_zone_code_canonical"] == compare["reference_after_zone_code_canonical"])
    )
    stable = compare[compare["stable_same_single_zone"]].copy()
    if stable.empty:
        return result

    stable["zone_code"] = stable["reference_after_zone_code_canonical"]
    stable["zone_description"] = stable["reference_after_zone_description"].combine_first(stable["reference_before_zone_description"])
    stable["zoning_status"] = "inferred_stable_between_reference_layers"
    stable["zoning_source_type"] = "inferred_stable"
    stable["zoning_source_plan_keys"] = f"{before_key};{after_key}"

    stable_columns = [
        "case_key",
        "zone_code",
        "zone_description",
        "zoning_status",
        "zoning_source_type",
        "zoning_source_plan_keys",
        "reference_before_zone_code",
        "reference_before_zone_description",
        "reference_after_zone_code",
        "reference_after_zone_description",
    ]
    result = result.merge(stable[stable_columns], on="case_key", how="left", suffixes=("", "_inferred"))
    apply_mask = result["zoning_status_inferred"].notna()
    for column in [
        "zone_code",
        "zone_description",
        "zoning_status",
        "zoning_source_type",
        "zoning_source_plan_keys",
        "reference_before_zone_code",
        "reference_before_zone_description",
        "reference_after_zone_code",
        "reference_after_zone_description",
    ]:
        inferred_column = f"{column}_inferred"
        if inferred_column in result.columns:
            result.loc[apply_mask, column] = result.loc[apply_mask, inferred_column]
            result = result.drop(columns=[inferred_column])
    return result


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

    result = build_official_join(case_gdf, layers)
    result = apply_dcc_stability_inference(result, case_gdf, layers)
    result = collapse_rows(result)

    out_csv = CURRENT_DIR / "dublin_case_zoning_with_inference.csv"
    result.to_csv(out_csv, index=False)

    summary = {
        "rows": int(len(result)),
        "official_matched": int((result["zoning_status"] == "official_matched").sum()),
        "official_multiple_polygon_matches": int((result["zoning_status"] == "official_multiple_polygon_matches").sum()),
        "inferred_stable_between_reference_layers": int((result["zoning_status"] == "inferred_stable_between_reference_layers").sum()),
        "no_layer_for_plan_key": int((result["zoning_status"] == "no_layer_for_plan_key").sum()),
        "no_polygon_match": int((result["zoning_status"] == "no_polygon_match").sum()),
        "missing_case_geometry": int((result["zoning_status"] == "missing_case_geometry").sum()),
        "resolved_by_plan_key": result.loc[
            result["zoning_status"].isin(["official_matched", "inferred_stable_between_reference_layers"]),
            "policy_plan_key",
        ].value_counts().to_dict(),
    }
    (CURRENT_DIR / "dublin_case_zoning_with_inference_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
