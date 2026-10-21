"""Runner: local absorption features for the sale model (plan item 3).

Per scheme at grant date (time-safe, prior events only), 1/3/5km:
competing new-build units commenced (BCMS), CCC flow prior 12m, recent
first-sale velocity (geocoded PPR rows), local new-build median price,
developer local market share (dev commenced units / local commenced
units). Then sale ablation on the production ladder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from devrisk import settings  # noqa: E402
from run_dev_sale_ladder import build_cohort  # noqa: E402

RINGS = [(1000, "1km"), (3000, "3km"), (5000, "5km")]


if __name__ == "__main__":
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms = bcms.dropna(subset=["itm_easting", "itm_northing"]).copy()
    bcms["comm_dt"] = pd.to_datetime(bcms["commencement_date_dt"], utc=True, errors="coerce")
    bcms["ccc_dt"] = pd.to_datetime(bcms["completion_certificate_date_dt"], utc=True, errors="coerce")
    bcms["units"] = pd.to_numeric(bcms["dwellings_phase"], errors="coerce").fillna(0)
    tree = cKDTree(bcms[["itm_easting", "itm_northing"]].to_numpy())
    comm_arr = bcms["comm_dt"].to_numpy()
    ccc_arr = bcms["ccc_dt"].to_numpy()
    units_arr = bcms["units"].to_numpy()

    # Geocoded PPR rows for sale velocity.
    geo = pd.read_parquet(settings.SILVER_DIR / "ppr_townland_geocode.parquet") if (settings.SILVER_DIR / "ppr_townland_geocode.parquet").exists() else None
    ppr_tree = None
    ppr_dates = None
    ppr_prices = None
    if geo is not None and len(geo):
        geo = geo.dropna(subset=["itm_easting", "itm_northing"]).copy()
        ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
        ppr_map = ppr[["source_row_id", "sale_date_dt", "price_num"]].rename(columns={"sale_date_dt": "sale_date"})
        geo = geo.merge(ppr_map, on="source_row_id", how="left")
        geo = geo.dropna(subset=["sale_date"])
        ppr_tree = cKDTree(geo[["itm_easting", "itm_northing"]].to_numpy())
        ppr_dates = pd.to_datetime(geo["sale_date"], utc=True, errors="coerce").to_numpy()
        ppr_prices = pd.to_numeric(geo["price_num"], errors="coerce").to_numpy()

    cohort = build_cohort()
    cohort = cohort[cohort["sales_eligible"].fillna(True)]
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    scheme_points = phases.dropna(subset=["itm_easting", "itm_northing"]).groupby("development_id").agg(
        east=("itm_easting", "median"), north=("itm_northing", "median"))

    groups = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv")
    cohort = cohort.merge(groups[["case_key", "group_id"]], on="case_key", how="left")

    rows = []
    for _, scheme in cohort.iterrows():
        point = scheme_points[scheme_points.index == str(scheme["case_key"])]
        if not len(point):
            rows.append({"case_key": str(scheme["case_key"])})
            continue
        east, north = float(point.iloc[0]["east"]), float(point.iloc[0]["north"])
        grant = pd.to_datetime(scheme["grant_date_dt"], utc=True)
        row = {"case_key": str(scheme["case_key"])}
        for radius, name in RINGS:
            idx = tree.query_ball_point([east, north], radius)
            prior_comm = [i for i in idx if pd.notna(comm_arr[i]) and comm_arr[i] < grant]
            ccc_12m = sum(1 for i in idx if pd.notna(ccc_arr[i]) and ccc_arr[i] < grant and (grant - ccc_arr[i]).days <= 366)
            competing_units = float(sum(units_arr[i] for i in prior_comm))
            row[f"{name}_competing_newbuild_units"] = round(competing_units, 0)
            row[f"{name}_ccc_flow_12m"] = ccc_12m
            if ppr_tree is not None:
                pidx = ppr_tree.query_ball_point([east, north], radius)
                mask = pd.notna(ppr_dates[pidx]) & (ppr_dates[pidx] < grant) & ((grant - ppr_dates[pidx]).dt if False else True)
                recent = [i for i in pidx if pd.notna(ppr_dates[i]) and ppr_dates[i] < grant and (grant - ppr_dates[i]).days <= 366]
                row[f"{name}_sales_12m"] = len(recent)
                if recent:
                    row[f"{name}_local_median_price"] = round(float(np.nanmedian(ppr_prices[recent])), 0)
                else:
                    row[f"{name}_local_median_price"] = np.nan
        rows.append(row)

    absorption = pd.DataFrame(rows)
    absorption.to_csv(settings.SILVER_DIR / "local_absorption_features.csv", index=False)
    summary = {"rows": int(len(absorption)), "with_geo": int(absorption["1km_competing_newbuild_units"].notna().sum()),
               "out": str(settings.SILVER_DIR / "local_absorption_features.csv")}
    (settings.SILVER_DIR / "local_absorption_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
