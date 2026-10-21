#!/usr/bin/env python3
"""Build query-time constraint reference tables for site-context evidence.

Inputs (07_context/raw/, fetched by download_constraint_layers.py):
  niah_buildings.csv          NIAH national buildings dataset (ITM coords)
  natura/SPA_ITM_2026_02.*    NPWS SPA boundaries (EPSG:2157)
  natura/SAC_ITM_2026_01.*    NPWS SAC boundaries (EPSG:2157)
  wwtp_emission_points.json   EPA urban waste-water emission points (EPSG:29902)
  tmu_traffic_counters.geojson  TII/TMU traffic counters (WGS84)

Outputs (07_context/current/):
  constraint_niah.parquet     name / reg_no / town / county / rating / ITM
  constraint_natura.parquet   SPA + SAC polygons (GeoParquet, EPSG:2157)
  constraint_wwtp.parquet     EPA emission points converted to ITM
  constraint_traffic.parquet  traffic counters converted to ITM

After a successful build the bulky raw inputs (NIAH CSV and the extracted
shapefile components) are removed; they can be re-fetched with
download_constraint_layers.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "07_context" / "raw"
OUT = ROOT / "07_context" / "current"
OUT.mkdir(parents=True, exist_ok=True)

TO_ITM = Transformer.from_crs("EPSG:29902", "EPSG:2157", always_xy=True)
WGS84_TO_ITM = Transformer.from_crs("EPSG:4326", "EPSG:2157", always_xy=True)


def build_niah() -> None:
    csv_path = RAW / "niah_buildings.csv"
    if not csv_path.exists():
        print("niah csv missing - run download_constraint_layers.py first")
        return
    frame = pd.read_csv(
        csv_path,
        low_memory=False,
        encoding="latin-1",
        usecols=["REG_NO", "NAME", "TOWN", "COUNTY", "RATING", "ITM_E", "ITM_N"],
    )
    frame = frame.rename(columns={"REG_NO": "reg_no", "NAME": "name", "TOWN": "town",
                                  "COUNTY": "county", "RATING": "rating",
                                  "ITM_E": "itm_easting", "ITM_N": "itm_northing"})
    for col in ("itm_easting", "itm_northing"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["itm_easting", "itm_northing"])
    frame.to_parquet(OUT / "constraint_niah.parquet", index=False)
    print(f"niah: {len(frame)} buildings -> constraint_niah.parquet")
    csv_path.unlink(missing_ok=True)
    print("removed bulky niah_buildings.csv")


def build_natura() -> None:
    frames = []
    for shp, kind in (("SPA_ITM_2026_02.shp", "SPA"), ("SAC_ITM_2026_01.shp", "SAC")):
        path = RAW / "natura" / shp
        if not path.exists():
            continue
        gdf = gpd.read_file(path)
        gdf = gdf[["SITECODE", "SITE_NAME", "geometry"]].rename(
            columns={"SITECODE": "sitecode", "SITE_NAME": "sitename"})
        gdf["type"] = kind
        frames.append(gdf)
    if not frames:
        print("natura shapefiles missing")
        return
    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:2157")
    combined.to_parquet(OUT / "constraint_natura.parquet", index=False)
    print(f"natura: {len(combined)} sites ({combined['type'].value_counts().to_dict()}) -> constraint_natura.parquet")
    for pattern in ("SPA_ITM_2026_02*", "SAC_ITM_2026_01*", "SAC_Offshore*"):
        for path in (RAW / "natura").glob(pattern):
            path.unlink(missing_ok=True)
    for zip_name in ("SPA_ITM_2026_02.zip", "SAC_ITM_2026_01.zip"):
        (RAW / zip_name).unlink(missing_ok=True)
    print("removed extracted shapefile components and zips")


def build_wwtp() -> None:
    path = RAW / "wwtp_emission_points.json"
    if not path.exists():
        print("wwtp json missing - run download_constraint_layers.py first")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if not coords or not coords[0]:
            continue
        easting, northing = TO_ITM.transform(float(coords[0][0]), float(coords[0][1]))
        rows.append({
            "name": str(props.get("Name") or ""),
            "emission_id": str(props.get("EmissionID") or ""),
            "reg_no": str(props.get("RegNo") or ""),
            "itm_easting": easting,
            "itm_northing": northing,
        })
    frame = pd.DataFrame(rows)
    frame = frame.replace([float("inf"), float("-inf")], float("nan"))
    frame = frame.dropna(subset=["itm_easting", "itm_northing"])
    frame.to_parquet(OUT / "constraint_wwtp.parquet", index=False)
    print(f"wwtp: {len(frame)} emission points -> constraint_wwtp.parquet")


def build_traffic() -> None:
    path = RAW / "tmu_traffic_counters.geojson"
    if not path.exists():
        print("traffic geojson missing")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        lon, lat = (geometry.get("coordinates") or [None, None])[:2]
        if lon is None or lat is None:
            continue
        easting, northing = WGS84_TO_ITM.transform(float(lon), float(lat))
        rows.append({
            "name": str(props.get("field_1") or ""),
            "counter_id": str(props.get("field_5") or ""),
            "itm_easting": easting,
            "itm_northing": northing,
        })
    frame = pd.DataFrame(rows)
    frame.to_parquet(OUT / "constraint_traffic.parquet", index=False)
    print(f"traffic: {len(frame)} counters -> constraint_traffic.parquet")


def main() -> None:
    build_niah()
    build_natura()
    build_wwtp()
    build_traffic()
    print("done")


if __name__ == "__main__":
    main()
