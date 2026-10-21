#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
import struct
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
import pyogrio
import requests
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = ROOT / "05_policy"
CURRENT_DIR = POLICY_ROOT / "current"
RAW_DIR = POLICY_ROOT / "documents" / "zoning" / "raw"
NORMALIZED_DIR = POLICY_ROOT / "documents" / "zoning" / "normalized"

GROUND_SOURCE = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_ge10_fixed.csv"

DUBLIN_AUTHORITIES = [
    "Dublin City Council",
    "Dun Laoghaire Rathdown County Council",
    "Fingal County Council",
    "South Dublin County Council",
]

MANUAL_LAYER_SPECS = [
    {
        "authority": "Dublin City Council",
        "plan_key": "dublin_city_council__2016_2022",
        "raw_dir": RAW_DIR / "dublin_city_council" / "2016_2022",
    },
    {
        "authority": "South Dublin County Council",
        "plan_key": "south_dublin_county_council__2016_2022",
        "raw_dir": RAW_DIR / "south_dublin_county_council" / "2016_2022",
    },
    {
        "authority": "South Dublin County Council",
        "plan_key": "south_dublin_county_council__2010_2016",
        "raw_dir": RAW_DIR / "south_dublin_county_council" / "2010_2016",
    },
    {
        "authority": "South Dublin County Council",
        "plan_key": "south_dublin_county_council__2004_2010",
        "raw_dir": RAW_DIR / "south_dublin_county_council" / "2004_2010",
    },
    {
        "authority": "Fingal County Council",
        "plan_key": "fingal_county_council__2011_2017",
        "raw_dir": RAW_DIR / "fingal_county_council" / "2011_2017",
    },
]


def ensure_dirs() -> None:
    for path in [CURRENT_DIR, RAW_DIR, NORMALIZED_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def fetch_json(url: str) -> dict:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.json()


def download_text(url: str, dest: Path) -> Path:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)
    return dest


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned or "dataset"


def decode_wkb_point(value: object) -> tuple[float, float] | None:
    if value is None or pd.isna(value):
        return None
    parsed = ast.literal_eval(str(value))
    if not isinstance(parsed, (bytes, bytearray)) or len(parsed) < 21 or parsed[0] != 1:
        return None
    geom_type = struct.unpack("<I", parsed[1:5])[0]
    if geom_type != 1:
        return None
    x = struct.unpack("<d", parsed[5:13])[0]
    y = struct.unpack("<d", parsed[13:21])[0]
    return x, y


def build_case_points() -> Path:
    transformer = Transformer.from_crs(3857, 2157, always_xy=True)
    df = pd.read_csv(
        GROUND_SOURCE,
        low_memory=False,
        usecols=[
            "PlanningAuthority",
            "ApplicationNumber",
            "DevelopmentAddress",
            "case_key",
            "geometry",
        ],
    )
    df = df[df["PlanningAuthority"].isin(DUBLIN_AUTHORITIES)].copy()
    coords = df["geometry"].map(decode_wkb_point)
    df["wm_x"] = coords.map(lambda item: item[0] if item else pd.NA)
    df["wm_y"] = coords.map(lambda item: item[1] if item else pd.NA)
    transformed = coords.map(lambda item: transformer.transform(item[0], item[1]) if item else (pd.NA, pd.NA))
    df["ITMEasting"] = transformed.map(lambda item: item[0])
    df["ITMNorthing"] = transformed.map(lambda item: item[1])
    out_path = CURRENT_DIR / "dublin_case_points_from_base.csv"
    df.drop(columns=["geometry"]).to_csv(out_path, index=False)
    return out_path


def dcc_2022_resources() -> list[dict[str, str]]:
    data = fetch_json("https://data.smartdublin.ie/api/3/action/package_show?id=development-plan-dcc-2022-2028")["result"]
    resources = []
    for item in data.get("resources", []):
        fmt = str(item.get("format", "")).upper()
        url = str(item.get("url", ""))
        if fmt != "GEOJSON" or "zone-z" not in url.lower():
            continue
        resources.append(
            {
                "authority": "Dublin City Council",
                "plan_key": "dublin_city_council__2022_2028",
                "source_name": item.get("name") or Path(url).name,
                "url": url,
            }
        )
    return resources


def download_arcgis_geojson_batches(service_url: str, out_path: Path, batch_size: int = 100) -> Path:
    meta = fetch_json(f"{service_url}?f=pjson")
    object_id_field = meta.get("objectIdField", "OBJECTID")
    ids_payload = fetch_json(f"{service_url}/query?where=1%3D1&returnIdsOnly=true&f=json")
    object_ids = ids_payload.get("objectIds", [])
    features: list[dict] = []
    for start in range(0, len(object_ids), batch_size):
        batch = object_ids[start : start + batch_size]
        payload = requests.post(
            f"{service_url}/query",
            data={
                "objectIds": ",".join(str(item) for item in batch),
                "outFields": "*",
                "returnGeometry": "true",
                "f": "geojson",
            },
            timeout=120,
        )
        payload.raise_for_status()
        geojson = payload.json()
        features.extend(geojson.get("features", []))
    collection = {"type": "FeatureCollection", "features": features, "objectIdFieldName": object_id_field}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(collection), encoding="utf-8")
    return out_path


def load_and_tag(path: Path, authority: str, plan_key: str, zone_code_col: str, zone_desc_col: str | None = None) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    return tag_gdf(gdf, authority, plan_key, zone_code_col, zone_desc_col)


def tag_gdf(gdf: gpd.GeoDataFrame, authority: str, plan_key: str, zone_code_col: str, zone_desc_col: str | None = None) -> gpd.GeoDataFrame:
    gdf["authority"] = authority
    gdf["plan_key"] = plan_key
    gdf["zone_code"] = gdf[zone_code_col].astype(str)
    if zone_desc_col and zone_desc_col in gdf.columns:
        gdf["zone_description"] = gdf[zone_desc_col].astype(str)
    else:
        gdf["zone_description"] = gdf["zone_code"]
    return gdf[["authority", "plan_key", "zone_code", "zone_description", "geometry"]].copy()


def read_zip_layer(path: Path) -> gpd.GeoDataFrame:
    zip_path = f"zip://{path}"
    try:
        return gpd.read_file(zip_path)
    except Exception:
        try:
            layers = pyogrio.list_layers(zip_path)
        except Exception:
            return gpd.GeoDataFrame()
        if layers is None or len(layers) == 0:
            return gpd.GeoDataFrame()
        for layer_name, _geom_type in layers:
            try:
                return gpd.read_file(zip_path, layer=layer_name)
            except Exception:
                continue
        return gpd.GeoDataFrame()


def read_vector_layer(path: Path) -> gpd.GeoDataFrame:
    if path.suffix.lower() == ".zip":
        return read_zip_layer(path)
    return gpd.read_file(path)


def infer_zone_columns(gdf: gpd.GeoDataFrame) -> tuple[str, str | None]:
    code_candidates = [
        "zone_code",
        "Zone",
        "ZONE_ORIG",
        "ZONE_GZT",
        "Obj_Code",
        "ZoningObje",
        "ZoningObj",
        "ZONING",
        "ZONE",
        "LAND_USE",
        "LANDUSE",
        "LandUse",
        "Objective",
        "ObjectiveCode",
        "ZONECODE",
    ]
    desc_candidates = [
        "zone_description",
        "ZONE_DESC",
        "Obj_Desc",
        "ObjectiveD",
        "ObjectiveDesc",
        "Description",
        "Descr",
        "ZONE_LINK",
        "ZONEDESC",
        "ZONEDESCR",
    ]
    for column in code_candidates:
        if column in gdf.columns:
            desc = next((item for item in desc_candidates if item in gdf.columns and item != column), None)
            return column, desc
    lowered = {column.lower(): column for column in gdf.columns}
    for candidate in ["zone", "zoning", "obj_code", "objective", "landuse", "land_use"]:
        for lowered_name, original in lowered.items():
            if candidate in lowered_name:
                desc = next((value for key, value in lowered.items() if any(term in key for term in ["desc", "descr", "objectived"])), None)
                return original, desc
    raise ValueError(f"Could not infer zoning code column from {list(gdf.columns)}")


def first_local_vector_file(raw_dir: Path) -> Path | None:
    patterns = ["*.geojson", "*.json", "*.gpkg", "*.shp", "*.zip"]
    for pattern in patterns:
        matches = sorted(raw_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def normalize_local_layer(authority: str, plan_key: str, raw_dir: Path) -> Path | None:
    source_path = first_local_vector_file(raw_dir)
    if source_path is None:
        return None
    gdf = read_vector_layer(source_path)
    if gdf.empty or "geometry" not in gdf.columns:
        raise ValueError(f"Manual zoning file for {plan_key} had no usable geometry: {source_path}")
    zone_code_col, zone_desc_col = infer_zone_columns(gdf)
    normalized = tag_gdf(gdf, authority, plan_key, zone_code_col, zone_desc_col)
    out_path = NORMALIZED_DIR / f"{plan_key}.geojson"
    normalized.to_file(out_path, driver="GeoJSON")
    return out_path


def normalize_dcc_2022(resource_rows: Iterable[dict[str, str]]) -> Path:
    layers = []
    for item in resource_rows:
        filename = slugify(item["source_name"]) + ".geojson"
        raw_path = download_text(item["url"], RAW_DIR / "dublin_city_council" / "2022_2028" / filename)
        gdf = load_and_tag(raw_path, item["authority"], item["plan_key"], "Zone")
        layers.append(gdf)
    merged = pd.concat(layers, ignore_index=True)
    out_path = NORMALIZED_DIR / "dublin_city_council__2022_2028.geojson"
    gpd.GeoDataFrame(merged, geometry="geometry", crs=layers[0].crs).to_file(out_path, driver="GeoJSON")
    return out_path


def normalize_dcc_2011_reference() -> Path:
    base_dir = RAW_DIR / "dublin_city_council" / "2011_2017_reference"
    stems = {
        "shp": "https://data.smartdublin.ie/dataset/4c460226-be30-4d4d-93bb-89a8d4a63006/resource/ff5908ee-5a03-4f3d-a3da-b68dfcc20f1c/download/dccdevelopmentplanp20141002-1159.shp",
        "dbf": "https://data.smartdublin.ie/dataset/4c460226-be30-4d4d-93bb-89a8d4a63006/resource/1bf04eb6-638d-4b9b-8167-15c0816fe96e/download/dccdevelopmentplanp20141002-1159.dbf",
        "shx": "https://data.smartdublin.ie/dataset/4c460226-be30-4d4d-93bb-89a8d4a63006/resource/652ed215-ac28-4f2f-b8ec-8b335372a28c/download/dccdevelopmentplanp20141002-1159.shx",
        "prj": "https://data.smartdublin.ie/dataset/4c460226-be30-4d4d-93bb-89a8d4a63006/resource/f15dbaa8-584d-4063-981f-909e4770a2a0/download/dccdevelopmentplanp20141002-1159.prj",
    }
    for ext, url in stems.items():
        download_text(url, base_dir / f"dccdevelopmentplanp20141002-1159.{ext}")
    shp_path = base_dir / "dccdevelopmentplanp20141002-1159.shp"
    gdf = gpd.read_file(shp_path)
    gdf = tag_gdf(gdf, "Dublin City Council", "dublin_city_council__2011_2017_reference", "ZONE_ORIG", "ZONE_DESC")
    gdf["zone_code"] = gdf["zone_code"].astype(str).str.extract(r"(Z\d+)", expand=False).fillna(gdf["zone_code"])
    out_path = NORMALIZED_DIR / "dublin_city_council__2011_2017_reference.geojson"
    gdf.to_file(out_path, driver="GeoJSON")
    return out_path


def normalize_dlr_2022() -> Path:
    url = (
        "https://data.smartdublin.ie/dataset/1300a7ab-07c9-46c9-b7a7-282c4197c57d/"
        "resource/c971c974-3a1d-4752-b1f3-8e4334a95912/download/devplan2022_2028_landusezoning.geojson"
    )
    raw_path = download_text(url, RAW_DIR / "dun_laoghaire_rathdown_county_council" / "2022_2028" / "landusezoning.geojson")
    gdf = load_and_tag(raw_path, "Dun Laoghaire Rathdown County Council", "dun_laoghaire_rathdown_county_council__2022_2028", "ZoningObje", "ObjectiveD")
    out_path = NORMALIZED_DIR / "dun_laoghaire_rathdown_county_council__2022_2028.geojson"
    gdf.to_file(out_path, driver="GeoJSON")
    return out_path


def normalize_dlr_2016() -> Path:
    url = (
        "https://data.smartdublin.ie/dataset/3d615362-c8fc-48d0-b753-7400cc4ef7f7/"
        "resource/7f6d372c-1bd7-471e-9367-a96487e9c156/download/dlr_development_plan_2016_2022_zoning_objectives.geojson"
    )
    raw_path = download_text(url, RAW_DIR / "dun_laoghaire_rathdown_county_council" / "2016_2022" / "zoning_objectives.geojson")
    gdf = load_and_tag(raw_path, "Dun Laoghaire Rathdown County Council", "dun_laoghaire_rathdown_county_council__2016_2022", "ZONE_ORIG", "ZONE_DESC")
    gdf["zone_code"] = gdf["zone_code"].astype(str).str.replace("OBJECTIVE ", "", regex=False).str.strip()
    out_path = NORMALIZED_DIR / "dun_laoghaire_rathdown_county_council__2016_2022.geojson"
    gdf.to_file(out_path, driver="GeoJSON")
    return out_path


def dlr_historic_objective_resources() -> tuple[list[dict], list[dict]]:
    package_id = "57d57040-7647-40c3-980a-26558d15cd46"
    data = fetch_json(f"https://data.smartdublin.ie/api/3/action/package_show?id={package_id}")["result"]
    resources_2010 = []
    resources_2004 = []
    skip_terms = ("road", "motorway", "protected", "conservation", "surface water", "luas", "generalzones", "srr")
    for item in data.get("resources", []):
        name = str(item.get("name", ""))
        name_low = name.lower()
        fmt = str(item.get("format", "")).upper()
        url = str(item.get("url", ""))
        if fmt != "ZIP":
            continue
        if "objective" not in name_low:
            continue
        if any(term in name_low for term in skip_terms):
            continue
        if "2010 - 2016" in name or "2010-2016" in name:
            resources_2010.append(item)
        elif "2004 - 2010" in name or "2004-2010" in name:
            resources_2004.append(item)
    return resources_2010, resources_2004


def normalize_dlr_historic(plan_label: str, plan_key: str, resources: list[dict]) -> Path:
    layers = []
    year_dir = plan_label.replace("-", "_")
    for item in resources:
        name = str(item.get("name", ""))
        url = str(item.get("url", ""))
        raw_path = download_text(url, RAW_DIR / "dun_laoghaire_rathdown_county_council" / year_dir / f"{slugify(name)}.zip")
        gdf = read_zip_layer(raw_path)
        if gdf.empty:
            continue
        if "geometry" not in gdf.columns:
            continue
        zone_code = name.split("Objective", 1)[-1].strip()
        if zone_code.startswith("A ") or zone_code.startswith("A1 ") or zone_code.startswith("A2 "):
            zone_code = zone_code.split()[0]
        elif zone_code:
            zone_code = zone_code.split()[0]
        gdf["authority"] = "Dun Laoghaire Rathdown County Council"
        gdf["plan_key"] = plan_key
        gdf["zone_code"] = zone_code
        gdf["zone_description"] = name
        layers.append(gdf[["authority", "plan_key", "zone_code", "zone_description", "geometry"]].copy())
    if not layers:
        raise ValueError(f"No valid DLR historic zoning layers could be normalized for {plan_key}")
    merged = pd.concat(layers, ignore_index=True)
    out_path = NORMALIZED_DIR / f"{plan_key}.geojson"
    gpd.GeoDataFrame(merged, geometry="geometry", crs=layers[0].crs).to_file(out_path, driver="GeoJSON")
    return out_path


def normalize_sdcc_2022() -> Path:
    service_url = "https://services1.arcgis.com/PxbTDTskGHCe4sv6/arcgis/rest/services/Use_Zoning_Objectives_SDCC/FeatureServer/10"
    meta = fetch_json(f"{service_url}?f=pjson")
    subtype_map = {
        str(item["code"]): str(item["name"]).replace("Objective ", "")
        for item in meta.get("subtypes", [])
        if "code" in item and "name" in item
    }
    raw_path = download_arcgis_geojson_batches(service_url, RAW_DIR / "south_dublin_county_council" / "2022_2028" / "sdcc_use_zoning_objectives.geojson")
    gdf = gpd.read_file(raw_path)
    gdf["authority"] = "South Dublin County Council"
    gdf["plan_key"] = "south_dublin_county_council__2022_2028"
    gdf["zone_code"] = gdf["ObjectiveID"].astype(str).map(subtype_map).fillna(gdf["ObjectiveID"].astype(str))
    gdf["zone_description"] = gdf["zone_code"]
    out_path = NORMALIZED_DIR / "south_dublin_county_council__2022_2028.geojson"
    gdf[["authority", "plan_key", "zone_code", "zone_description", "geometry"]].to_file(out_path, driver="GeoJSON")
    return out_path


def normalize_fingal_2023() -> Path:
    url = "https://data.fingal.ie/api/download/v1/items/37d82053e2d24cb699f494a54560f5eb/geojson?layers=0"
    raw_path = download_text(url, RAW_DIR / "fingal_county_council" / "2023_2029" / "fingal_specific_objective_zoning.geojson")
    gdf = load_and_tag(raw_path, "Fingal County Council", "fingal_county_council__2023_2029", "Obj_Code", "Obj_Desc")
    out_path = NORMALIZED_DIR / "fingal_county_council__2023_2029.geojson"
    gdf.to_file(out_path, driver="GeoJSON")
    return out_path


def normalize_fingal_2017() -> Path:
    url = "https://data.fingal.ie/api/download/v1/items/52fc44847325448f85da04e1452b66ff/geojson?layers=0"
    raw_path = download_text(url, RAW_DIR / "fingal_county_council" / "2017_2023" / "fingal_adopted_development_plan_zoning.geojson")
    gdf = load_and_tag(raw_path, "Fingal County Council", "fingal_county_council__2017_2023", "Obj_Code", "Obj_Desc")
    out_path = NORMALIZED_DIR / "fingal_county_council__2017_2023.geojson"
    gdf.to_file(out_path, driver="GeoJSON")
    return out_path


def write_manifest(paths: list[Path]) -> Path:
    rows = []
    for path in paths:
        gdf = gpd.read_file(path, rows=5)
        rows.append(
            {
                "normalized_path": str(path.relative_to(ROOT)),
                "feature_count_preview_rows": len(gdf),
                "authority": gdf.iloc[0]["authority"],
                "plan_key": gdf.iloc[0]["plan_key"],
                "crs": str(gdf.crs),
            }
        )
    manifest_path = CURRENT_DIR / "dublin_zoning_layers_manifest.csv"
    pd.DataFrame(rows).to_csv(manifest_path, index=False)
    return manifest_path


def main() -> None:
    ensure_dirs()
    case_points_path = build_case_points()
    dlr_2010_resources, dlr_2004_resources = dlr_historic_objective_resources()
    outputs = [
        normalize_dcc_2022(dcc_2022_resources()),
        normalize_dcc_2011_reference(),
        normalize_dlr_2022(),
        normalize_dlr_2016(),
        normalize_dlr_historic("2010-2016", "dun_laoghaire_rathdown_county_council__2010_2016", dlr_2010_resources),
        normalize_dlr_historic("2004-2010", "dun_laoghaire_rathdown_county_council__2004_2010", dlr_2004_resources),
        normalize_sdcc_2022(),
        normalize_fingal_2017(),
        normalize_fingal_2023(),
    ]
    manual_outputs = []
    for spec in MANUAL_LAYER_SPECS:
        out_path = normalize_local_layer(spec["authority"], spec["plan_key"], spec["raw_dir"])
        if out_path is not None:
            manual_outputs.append(out_path)
    outputs.extend(manual_outputs)
    manifest_path = write_manifest(outputs)
    summary = {
        "case_points_path": str(case_points_path.relative_to(ROOT)),
        "zoning_layers": [str(path.relative_to(ROOT)) for path in outputs],
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "manual_layer_dirs": [str(spec["raw_dir"].relative_to(ROOT)) for spec in MANUAL_LAYER_SPECS],
    }
    (CURRENT_DIR / "dublin_zoning_prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
