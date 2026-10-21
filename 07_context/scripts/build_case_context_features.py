#!/usr/bin/env python3
"""Build per-application small-area context features (CSO SAPS 2022 + TII counters).

Inputs: 07_context/raw (SAPS cubes, OSI SA geojson, TII counters geojson)
Output: 07_context/current/case_context_features.parquet (keyed by case_key)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "07_context" / "raw"
OUT = ROOT / "07_context" / "current"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_prospective_calibration_backtest import prepare  # noqa: E402

SA_CODE_COL = "C04172V04943"
SA_ID_COL = "CSO Small Areas 2022"


def aggregate_saps(path: Path, value_col_maps: dict[str, list[str]]) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df["sa_id"] = pd.to_numeric(df[SA_ID_COL], errors="coerce")
    df["value"] = pd.to_numeric(df["VALUE"], errors="coerce").fillna(0)
    out = df.groupby("sa_id")["value"].sum().rename("total").to_frame()
    dim_col = [c for c in df.columns if c not in {SA_CODE_COL, SA_ID_COL, "STATISTIC", "Statistic Label", "TLIST(A1)", "Census Year", "UNIT", "VALUE"}][0]
    for stat_col, members in value_col_maps.items():
        sel = df[df[dim_col].isin(members)].groupby("sa_id")["value"].sum()
        out[stat_col] = sel
    return out


def main() -> None:
    print("parsing SAPS cubes...", flush=True)
    pop = pd.read_csv(RAW / "saps2022_t9t1sa_population.csv", low_memory=False)
    pop["sa_id"] = pd.to_numeric(pop[SA_ID_COL], errors="coerce")
    pop["value"] = pd.to_numeric(pop["VALUE"], errors="coerce").fillna(0)
    sa_pop = pop.groupby("sa_id")["value"].sum().rename("pop_total").to_frame()

    t63 = aggregate_saps(RAW / "saps2022_t6t3sa_accommodation.csv", {})
    t63_full = pd.read_csv(RAW / "saps2022_t6t3sa_accommodation.csv", low_memory=False)
    t63_full["sa_id"] = pd.to_numeric(t63_full[SA_ID_COL], errors="coerce")
    t63_full["value"] = pd.to_numeric(t63_full["VALUE"], errors="coerce").fillna(0)
    occ_col = [c for c in t63_full.columns if c not in {SA_CODE_COL, SA_ID_COL, "STATISTIC", "Statistic Label", "TLIST(A1)", "Census Year", "UNIT", "VALUE"}][0]
    tenure = t63_full.groupby(["sa_id", occ_col])["value"].sum().unstack(fill_value=0)
    tenure["hh_total"] = tenure.sum(axis=1)
    tenure["owner_share"] = tenure[["OML", "OO"]].sum(axis=1) / tenure["hh_total"].replace(0, np.nan)
    tenure["private_rent_share"] = tenure["RPL"] / tenure["hh_total"].replace(0, np.nan)
    tenure["la_rent_share"] = tenure["RLA"] / tenure["hh_total"].replace(0, np.nan)

    t67 = pd.read_csv(RAW / "saps2022_t6t7sa_households.csv", low_memory=False)
    t67["sa_id"] = pd.to_numeric(t67[SA_ID_COL], errors="coerce")
    t67["value"] = pd.to_numeric(t67["VALUE"], errors="coerce").fillna(0)
    sew_col = [c for c in t67.columns if c not in {SA_CODE_COL, SA_ID_COL, "STATISTIC", "Statistic Label", "TLIST(A1)", "Census Year", "UNIT", "VALUE"}][0]
    sewerage = t67.groupby(["sa_id", sew_col])["value"].sum().unstack(fill_value=0)
    sewerage["sew_total"] = sewerage.sum(axis=1)
    sewerage["septic_share"] = sewerage[["IST", "OIT"]].sum(axis=1) / sewerage["sew_total"].replace(0, np.nan)

    t15 = pd.read_csv(RAW / "saps2022_t15t1sa_cars.csv", low_memory=False)
    t15["sa_id"] = pd.to_numeric(t15[SA_ID_COL], errors="coerce")
    t15["value"] = pd.to_numeric(t15["VALUE"], errors="coerce").fillna(0)
    cars_col = [c for c in t15.columns if c not in {SA_CODE_COL, SA_ID_COL, "STATISTIC", "Statistic Label", "TLIST(A1)", "Census Year", "UNIT", "VALUE"}][0]
    cars = t15.groupby(["sa_id", cars_col])["value"].sum().unstack(fill_value=0)
    cars["cars_total"] = cars.sum(axis=1)
    cars["cars_per_hh"] = (cars.get("1C", 0) + 2 * cars.get("2C", 0) + 3 * cars.get("3C", 0) + 4 * cars.get("GE4C", 0)) / cars["cars_total"].replace(0, np.nan)
    cars["no_car_share"] = cars["NC"] / cars["cars_total"].replace(0, np.nan)

    sa_stats = sa_pop.join(tenure[["owner_share", "private_rent_share", "la_rent_share", "hh_total"]], how="left")
    sa_stats = sa_stats.join(sewerage[["septic_share"]], how="left")
    sa_stats = sa_stats.join(cars[["cars_per_hh", "no_car_share"]], how="left")
    print("sa stats rows:", len(sa_stats), flush=True)

    print("loading small-area geometries...", flush=True)
    import geopandas as gpd  # noqa: E402

    sa_gdf = gpd.read_file(RAW / "cso_small_areas_2022.geojson", ignore_geometry=False)
    print("sa geojson cols:", sa_gdf.columns.tolist(), flush=True)
    code_col = "SA_PUB2022"
    print("SA code column:", code_col, flush=True)
    sa_gdf["sa_id"] = pd.to_numeric(sa_gdf[code_col], errors="coerce")
    sa_gdf["area_sqkm"] = sa_gdf.geometry.area / 1_000_000
    sa_gdf["is_urban"] = sa_gdf.get("SA_URBAN_AREA_FLAG").astype(str).str.upper().isin({"Y", "1", "TRUE"}).astype(int) if "SA_URBAN_AREA_FLAG" in sa_gdf.columns else 0
    sa_gdf["urban_area_name"] = sa_gdf.get("SA_URBAN_AREA_NAME") if "SA_URBAN_AREA_NAME" in sa_gdf.columns else ""
    sa_gdf["nuts3_name"] = sa_gdf.get("SA_NUTS3_NAME") if "SA_NUTS3_NAME" in sa_gdf.columns else ""
    sa_gdf = sa_gdf.dropna(subset=["sa_id"])
    sa_gdf = sa_gdf.drop_duplicates("sa_id", keep="first")
    sa_gdf = sa_gdf.merge(sa_stats, on="sa_id", how="left")
    sa_gdf["pop_density_per_sqkm"] = sa_gdf["pop_total"] / sa_gdf["area_sqkm"].replace(0, np.nan)
    sa_gdf["centroid"] = sa_gdf.geometry.centroid

    print("loading applications...", flush=True)
    data = prepare()
    apps = data[["case_key", "ITMEasting", "ITMNorthing"]].dropna().copy()
    pts = gpd.GeoDataFrame(apps, geometry=gpd.points_from_xy(apps["ITMEasting"], apps["ITMNorthing"]), crs="EPSG:2157")
    print("sjoin...", flush=True)
    joined = gpd.sjoin(pts, sa_gdf[["sa_id", "geometry"]], how="left", predicate="within")
    joined = joined.drop(columns=["index_right"]).drop_duplicates("case_key", keep="first")
    print("rows after sjoin dedupe:", len(joined), flush=True)

    centroids_xy = np.column_stack([sa_gdf["centroid"].x.to_numpy(), sa_gdf["centroid"].y.to_numpy()])
    from scipy.spatial import cKDTree  # noqa: E402

    tree = cKDTree(centroids_xy)
    missing = joined["sa_id"].isna()
    if missing.any():
        _, idx = tree.query(joined.loc[missing, ["ITMEasting", "ITMNorthing"]].to_numpy())
        joined.loc[missing, "sa_id"] = sa_gdf["sa_id"].iloc[idx].to_numpy()
    joined = joined.merge(sa_gdf[["sa_id", "pop_total", "owner_share", "private_rent_share", "la_rent_share", "septic_share", "cars_per_hh", "no_car_share", "pop_density_per_sqkm", "area_sqkm", "is_urban", "urban_area_name", "nuts3_name"]], on="sa_id", how="left")
    print("sa join coverage:", round(float(joined["pop_total"].notna().mean()), 4), flush=True)

    print("national-road counters...", flush=True)
    with open(RAW / "tmu_traffic_counters.geojson", encoding="utf-8") as handle:
        counters = json.load(handle)
    from pyproj import Transformer  # noqa: E402

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:2157", always_xy=True)
    counter_rows = []
    for feat in counters["features"]:
        props = feat["properties"]
        lat = props.get("field_6")
        lon = props.get("field_7")
        if lat is None or lon is None:
            continue
        counter_rows.append({"road": str(props.get("field_1") or "")[:80], "lat": lat, "lon": lon})
    counter_df = pd.DataFrame(counter_rows)
    eastings, northings = transformer.transform(counter_df["lon"].to_numpy(), counter_df["lat"].to_numpy())
    counter_xy = np.column_stack([eastings, northings])
    counter_tree = cKDTree(counter_xy)
    app_xy = joined[["ITMEasting", "ITMNorthing"]].to_numpy()
    dist, _ = counter_tree.query(app_xy, k=1)
    joined["national_road_dist_m"] = dist
    joined["log_national_road_dist"] = np.log1p(dist)
    within_1km = counter_tree.query_ball_point(app_xy, 1000.0, return_length=True)
    joined["national_roads_within_1km"] = within_1km
    print("counters used:", len(counter_df), flush=True)

    keep = [
        "case_key", "sa_id", "pop_total", "owner_share", "private_rent_share", "la_rent_share",
        "septic_share", "cars_per_hh", "no_car_share", "pop_density_per_sqkm", "area_sqkm",
        "is_urban", "urban_area_name", "nuts3_name",
        "national_road_dist_m", "log_national_road_dist", "national_roads_within_1km",
    ]
    out = joined[keep].copy()
    for col in keep[1:]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out.to_parquet(OUT / "case_context_features.parquet", index=False)
    print("saved", len(out), "rows -> case_context_features.parquet", flush=True)
    print(out[["pop_total", "pop_density_per_sqkm", "septic_share", "national_road_dist_m"]].describe().round(2).to_string(), flush=True)


if __name__ == "__main__":
    main()
