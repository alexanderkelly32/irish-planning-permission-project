#!/usr/bin/env python3
"""Build query-time reference tables for the v4-full feature builder.

Outputs (all under 07_context/current/):
  sa_reference.parquet     small-area stats + centroids (for nearest-SA lookup)
  flood_points.parquet     case coordinates + flood features (for nearest-point flood)
  applicant_history.parquet  applicant_id -> prior counts/refusals (all historical rows)
  plan_summary.parquet     plan-in-force summaries per (council, start, end)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "07_context" / "current"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_prospective_calibration_backtest import prepare  # noqa: E402
from build_v3_policy_features_challenger import THEME_ORDER, theme_of  # noqa: E402

SA_CODE_COL = "C04172V04943"
SA_ID_COL = "CSO Small Areas 2022"


def main() -> None:
    print("building SA reference...", flush=True)
    import geopandas as gpd  # noqa: E402

    sa_gdf = gpd.read_file(ROOT / "07_context" / "raw" / "cso_small_areas_2022.geojson", ignore_geometry=False)
    sa_gdf["sa_id"] = pd.to_numeric(sa_gdf["SA_PUB2022"], errors="coerce")
    sa_gdf["is_urban"] = sa_gdf.get("SA_URBAN_AREA_FLAG").astype(str).str.upper().isin({"Y", "1", "TRUE"}).astype(int)
    sa_gdf = sa_gdf.dropna(subset=["sa_id"]).drop_duplicates("sa_id", keep="first")
    sa_gdf["centroid_x"] = sa_gdf.geometry.centroid.x
    sa_gdf["centroid_y"] = sa_gdf.geometry.centroid.y
    sa_gdf["area_sqkm"] = sa_gdf.geometry.area / 1_000_000

    pop = pd.read_csv(ROOT / "07_context" / "raw" / "saps2022_t9t1sa_population.csv", low_memory=False)
    pop["sa_id"] = pd.to_numeric(pop[SA_ID_COL], errors="coerce")
    pop["value"] = pd.to_numeric(pop["VALUE"], errors="coerce").fillna(0)
    sa_pop = pop.groupby("sa_id")["value"].sum().rename("pop_total")

    def agg_saps(path: str) -> pd.DataFrame:
        frame = pd.read_csv(path, low_memory=False)
        frame["sa_id"] = pd.to_numeric(frame[SA_ID_COL], errors="coerce")
        frame["value"] = pd.to_numeric(frame["VALUE"], errors="coerce").fillna(0)
        dim = [c for c in frame.columns if c not in {SA_CODE_COL, SA_ID_COL, "STATISTIC", "Statistic Label", "TLIST(A1)", "Census Year", "UNIT", "VALUE"}][0]
        return frame.groupby(["sa_id", dim])["value"].sum().unstack(fill_value=0)

    tenure = agg_saps(str(ROOT / "07_context" / "raw" / "saps2022_t6t3sa_accommodation.csv"))
    tenure["hh_total"] = tenure.sum(axis=1)
    tenure["owner_share"] = tenure[["OML", "OO"]].sum(axis=1) / tenure["hh_total"].replace(0, np.nan)
    tenure["private_rent_share"] = tenure["RPL"] / tenure["hh_total"].replace(0, np.nan)
    tenure["la_rent_share"] = tenure["RLA"] / tenure["hh_total"].replace(0, np.nan)

    sewerage = agg_saps(str(ROOT / "07_context" / "raw" / "saps2022_t6t7sa_households.csv"))
    sewerage["sew_total"] = sewerage.sum(axis=1)
    sewerage["septic_share"] = sewerage[["IST", "OIT"]].sum(axis=1) / sewerage["sew_total"].replace(0, np.nan)

    cars = agg_saps(str(ROOT / "07_context" / "raw" / "saps2022_t15t1sa_cars.csv"))
    cars["cars_total"] = cars.sum(axis=1)
    cars["cars_per_hh"] = (cars.get("1C", 0) + 2 * cars.get("2C", 0) + 3 * cars.get("3C", 0) + 4 * cars.get("GE4C", 0)) / cars["cars_total"].replace(0, np.nan)
    cars["no_car_share"] = cars["NC"] / cars["cars_total"].replace(0, np.nan)

    sa_ref = sa_gdf[["sa_id", "centroid_x", "centroid_y", "area_sqkm", "is_urban", "SA_URBAN_AREA_NAME", "SA_NUTS3_NAME"]].merge(sa_pop, on="sa_id", how="left")
    sa_ref = sa_ref.merge(tenure[["owner_share", "private_rent_share", "la_rent_share", "hh_total"]], on="sa_id", how="left")
    sa_ref = sa_ref.merge(sewerage[["septic_share"]], on="sa_id", how="left")
    sa_ref = sa_ref.merge(cars[["cars_per_hh", "no_car_share"]], on="sa_id", how="left")
    sa_ref["pop_density_per_sqkm"] = sa_ref["pop_total"] / sa_ref["area_sqkm"].replace(0, np.nan)
    sa_ref.to_parquet(OUT / "sa_reference.parquet", index=False)
    print("sa_reference rows:", len(sa_ref), flush=True)

    print("building flood points...", flush=True)
    data = prepare()[["case_key", "ITMEasting", "ITMNorthing"]].dropna()
    flood = pd.read_parquet(ROOT / "01_flood" / "current" / "all_cases_with_flooding.parquet")
    flood_points = flood.merge(data, on="case_key", how="inner")
    flood_points.to_parquet(OUT / "flood_points.parquet", index=False)
    print("flood_points rows:", len(flood_points), flush=True)

    print("building applicant history...", flush=True)
    reg = prepare()
    reg["applicant_id"] = reg["ApplicantForename"].fillna("").astype(str).str.lower() + "|" + reg["ApplicantSurname"].fillna("").astype(str).str.lower()
    reg["applicant_id"] = reg["applicant_id"].replace({"|": "", "||": ""}, regex=False).replace("", np.nan)
    reg["is_company"] = reg["ApplicantSurname"].fillna("").astype(str).str.contains(r"\b(ltd|limited|holdings|developments|properties|group|construction|builders|homes|company|clg|co\.|investments|estates)\b", case=False, regex=True)
    applicant = reg[reg["applicant_id"].notna()].groupby("applicant_id").agg(
        prior_count=("case_key", "size"),
        prior_refusals=("target_refused", lambda s: s.fillna(0).sum()),
        any_company=("is_company", "any"),
    ).reset_index()
    applicant["prior_refusal_rate"] = applicant["prior_refusals"] / applicant["prior_count"].replace(0, np.nan)
    applicant.to_parquet(OUT / "applicant_history.parquet", index=False)
    print("applicant_history rows:", len(applicant), flush=True)

    print("building plan summary...", flush=True)
    layer = pd.read_csv(ROOT / "05_policy" / "current" / "objective_code_layer.csv", low_memory=False)
    layer["council"] = layer["council"].replace("Limerick City and County Council", "Limerick County Council")
    layer["start"] = pd.to_numeric(layer["plan_period"].str.split("-").str[0], errors="coerce")
    layer["end"] = pd.to_numeric(layer["plan_period"].str.split("-").str[1], errors="coerce")
    layer = layer.dropna(subset=["start", "end"])
    layer["theme"] = layer["objective_code"].map(theme_of)
    rows = []
    for (council, period), group in layer.groupby(["council", "plan_period"]):
        row = {"council": council, "start": int(group["start"].iloc[0]), "end": int(group["end"].iloc[0]),
               "plan_unique_codes": int(group["objective_code"].nunique()), "plan_mentions": int(group["mentions"].sum()),
               **{f"plan_theme_{t}": int(group.loc[group["theme"] == t, "objective_code"].nunique()) for t in THEME_ORDER},
               "plan_theme_other": int(group.loc[group["theme"] == "other", "objective_code"].nunique())}
        rows.append(row)
    plans = pd.DataFrame(rows).sort_values(["council", "start"])
    plans.to_parquet(OUT / "plan_summary.parquet", index=False)
    print("plan_summary rows:", len(plans), flush=True)


if __name__ == "__main__":
    main()
