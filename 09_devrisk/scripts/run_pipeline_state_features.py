"""Runner: E3 - local pipeline-state features (1/3/5/10 km, time-safe).

At each pool scheme's grant date, from strictly earlier events only:
granted-not-commenced units, commenced-not-completed units, CCCs in prior
3/6/12 months, competing same-type schemes, active developers, local
supply concentration, progression rates. Uses BCMS + register, KDTree
spatial joins. Writes pipeline_state_features.csv.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from devrisk import settings  # noqa: E402

RINGS = [(1000, "1km"), (3000, "3km"), (5000, "5km"), (10000, "10km")]


if __name__ == "__main__":
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms = bcms.dropna(subset=["itm_easting", "itm_northing"]).copy()
    bcms["comm_dt"] = pd.to_datetime(bcms["commencement_date_dt"], utc=True, errors="coerce")
    bcms["ccc_dt"] = pd.to_datetime(bcms["completion_certificate_date_dt"], utc=True, errors="coerce")
    bcms["units"] = pd.to_numeric(bcms["dwellings_phase"], errors="coerce").fillna(0)

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    units_reg = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    reg = register[units_reg.ge(10)].copy()
    reg["east"] = pd.to_numeric(reg["ITMEasting"], errors="coerce")
    reg["north"] = pd.to_numeric(reg["ITMNorthing"], errors="coerce")
    reg["grant_dt"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce")
    reg["received_dt"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce")
    reg = reg.dropna(subset=["east", "north"])

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    pool = reg[reg["case_key"].astype(str).isin(set(labels["case_key"].astype(str)))].copy()

    tree_bcms = cKDTree(bcms[["itm_easting", "itm_northing"]].to_numpy())
    tree_reg = cKDTree(reg[["east", "north"]].to_numpy())
    bcms_arrays = {c: bcms[c].to_numpy() for c in ("comm_dt", "ccc_dt", "units")}
    reg_arrays = {c: reg[c].to_numpy() for c in ("grant_dt", "received_dt")}
    reg_units_arr = units_reg[units_reg.ge(10)].to_numpy()
    reg_desc = reg["DevelopmentDescription"].fillna("").str.contains(
        r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).to_numpy()

    rows = []
    for _, scheme in pool.iterrows():
        east, north = scheme["east"], scheme["north"]
        grant = scheme["grant_dt"]
        idx_bcms = tree_bcms.query_ball_point([east, north], 10000)
        idx_reg = tree_reg.query_ball_point([east, north], 10000)
        row = {"case_key": str(scheme["case_key"])}
        scheme_apt_i = bool(re.search(r"\b(?:apartment|apartments|duplex)\b", str(scheme.get("DevelopmentDescription") or ""), re.IGNORECASE))
        for radius, name in RINGS:
            b = [i for i in idx_bcms if np.hypot(bcms.iloc[i]["itm_easting"] - east, bcms.iloc[i]["itm_northing"] - north) <= radius]
            r = [i for i in idx_reg if np.hypot(reg.iloc[i]["east"] - east, reg.iloc[i]["north"] - north) <= radius]
            prior_b = [i for i in b if pd.notna(bcms_arrays["comm_dt"][i]) and bcms_arrays["comm_dt"][i] < grant]
            prior_r = [i for i in r if pd.notna(reg_arrays["grant_dt"][i]) and reg_arrays["grant_dt"][i] < grant]
            ccc_3m = sum(1 for i in b if pd.notna(bcms_arrays["ccc_dt"][i]) and bcms_arrays["ccc_dt"][i] < grant and (grant - bcms_arrays["ccc_dt"][i]).days <= 92)
            ccc_6m = sum(1 for i in b if pd.notna(bcms_arrays["ccc_dt"][i]) and bcms_arrays["ccc_dt"][i] < grant and (grant - bcms_arrays["ccc_dt"][i]).days <= 184)
            ccc_12m = sum(1 for i in b if pd.notna(bcms_arrays["ccc_dt"][i]) and bcms_arrays["ccc_dt"][i] < grant and (grant - bcms_arrays["ccc_dt"][i]).days <= 366)
            granted_units = float(sum(reg_units_arr[i] for i in prior_r))
            commenced_units = float(sum(bcms_arrays["units"][i] for i in prior_b))
            uncommenced_units = max(granted_units - commenced_units, 0.0)
            progression = commenced_units / granted_units if granted_units > 0 else np.nan
            same_type = sum(1 for i in prior_r if reg_desc[i] == scheme_apt_i)
            row[f"{name}_granted_not_commenced_units"] = round(uncommenced_units, 0)
            row[f"{name}_commenced_units"] = round(commenced_units, 0)
            row[f"{name}_ccc_3m"] = ccc_3m
            row[f"{name}_ccc_6m"] = ccc_6m
            row[f"{name}_ccc_12m"] = ccc_12m
            row[f"{name}_progression_ratio"] = round(float(progression), 3) if pd.notna(progression) else np.nan
            row[f"{name}_same_type_competing"] = same_type
            row[f"{name}_prior_apps"] = len(prior_r)
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame.to_csv(settings.SILVER_DIR / "pipeline_state_features.csv", index=False)
    coverage = frame.notna().mean().round(2).to_dict()
    summary = {"rows": int(len(frame)), "out": str(settings.SILVER_DIR / "pipeline_state_features.csv"),
               "coverage_sample": {k: v for k, v in list(coverage.items())[:8]}}
    (settings.SILVER_DIR / "pipeline_state_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
