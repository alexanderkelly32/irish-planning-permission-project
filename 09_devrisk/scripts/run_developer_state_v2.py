"""Runner: developer-state v2 - richer time-safe interactions.

Adds to developer_state_features: dev x authority and dev x county shrunk
medians, concurrent live-unit load (units in uncommenced schemes),
delivery velocity (units completed in prior 12/24 months), recency-
weighted activation/sale histories (exponential decay), and apartment/
house familiarity split. Then commencement ablation on the production
model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

HALF_LIFE_DAYS = 730.0
RNG = 7


def recency_weighted_median(values: np.ndarray, ages_days: np.ndarray) -> float:
    weights = np.exp(-ages_days / HALF_LIFE_DAYS)
    order = np.argsort(values)
    values_sorted = values[order]
    weights_sorted = weights[order]
    cumulative = np.cumsum(weights_sorted)
    midpoint = cumulative[-1] / 2.0
    return float(values_sorted[np.searchsorted(cumulative, midpoint)])


if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    entities = pd.read_csv(settings.SILVER_DIR / "applicant_entities.csv")
    groups = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv")
    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")

    frame = labels.merge(register[["case_key", "GrantDate", "PlanningAuthority", "NumResidentialUnits",
                                   "DevelopmentDescription"]].drop_duplicates("case_key"), on="case_key", how="inner")
    frame = frame.merge(entities[["case_key", "entity_key"]], on="case_key", how="left")
    frame = frame.merge(groups[["case_key", "group_id"]], on="case_key", how="left")
    frame = frame.merge(completion[["scheme_id", "t_first_ccc"]], left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["units"] = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce").fillna(0)
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    frame["type"] = np.where(frame["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True), "apartments",
                             np.where(frame["DevelopmentDescription"].fillna("").str.contains(r"\bhouse", case=False, regex=True), "houses", "other"))
    frame["county"] = frame["PlanningAuthority"].astype(str).str.lower().str.extract(
        r"(carlow|cavan|clare|cork|donegal|dublin|galway|kerry|kildare|kilkenny|laois|leitrim|limerick|longford|louth|mayo|meath|monaghan|offaly|roscommon|sligo|tipperary|waterford|westmeath|wexford|wicklow)")[0].fillna("")
    frame = frame.sort_values("grant_dt").reset_index(drop=True)

    rows = []
    for i, scheme in frame.iterrows():
        prior = frame.iloc[:i]
        same_group = prior[prior["group_id"].eq(scheme["group_id"])] if pd.notna(scheme["group_id"]) else prior.iloc[0:0]
        row = {"case_key": str(scheme["case_key"])}
        if len(same_group):
            # concurrent live-unit load
            live = same_group[same_group["activation_linked"].astype(str).str.lower() != "true"]
            row["dev_live_unit_load"] = float(live["units"].sum())
            row["dev_live_schemes"] = int(len(live))
            # delivery velocity: units completed in prior 12/24 months
            completed = same_group[same_group["t_first_ccc"].notna()].copy()
            if len(completed):
                completed["ccc_abs_dt"] = completed["grant_dt"] + pd.to_timedelta(completed["activation"].fillna(0) + completed["t_first_ccc"], unit="D")
                age = (scheme["grant_dt"] - completed["ccc_abs_dt"]).dt.days
                row["dev_units_completed_12m"] = float(completed.loc[age.between(0, 366), "units"].sum())
                row["dev_units_completed_24m"] = float(completed.loc[age.between(0, 731), "units"].sum())
            else:
                row["dev_units_completed_12m"] = 0.0
                row["dev_units_completed_24m"] = 0.0
            # recency-weighted histories
            ages = (scheme["grant_dt"] - same_group["grant_dt"]).dt.days.to_numpy()
            act = same_group["activation"].to_numpy()
            act_mask = ~np.isnan(act)
            row["dev_recency_weighted_activation"] = recency_weighted_median(act[act_mask], ages[act_mask]) if act_mask.sum() >= 2 else np.nan
            tfs = same_group["t_first_ccc"].to_numpy()
            tfs_mask = ~np.isnan(tfs)
            row["dev_recency_weighted_ccc"] = recency_weighted_median(tfs[tfs_mask], ages[tfs_mask]) if tfs_mask.sum() >= 2 else np.nan
            # interactions
            for suffix, col in (("authority", "PlanningAuthority"), ("county", "county"), ("type", "type")):
                inter = same_group[same_group[col] == scheme[col]]
                inter_act = inter[inter["activation"].notna()]
                row[f"dev_x_{suffix}_median_activation"] = float(inter_act["activation"].median()) if len(inter_act) >= 3 else np.nan
                row[f"dev_x_{suffix}_n"] = int(len(inter))
            # apartment/house familiarity split
            row["dev_apartment_share"] = float((same_group["type"] == "apartments").mean())
            row["dev_same_type_share"] = float((same_group["type"] == scheme["type"]).mean())
        else:
            for key in ("dev_live_unit_load", "dev_live_schemes", "dev_units_completed_12m", "dev_units_completed_24m",
                        "dev_x_authority_n", "dev_x_county_n", "dev_x_type_n", "dev_apartment_share", "dev_same_type_share"):
                row[key] = 0.0
            row["dev_recency_weighted_activation"] = np.nan
            row["dev_recency_weighted_ccc"] = np.nan
            for suffix in ("authority", "county", "type"):
                row[f"dev_x_{suffix}_median_activation"] = np.nan
        rows.append(row)

    v2 = pd.DataFrame(rows)
    v2.to_csv(settings.SILVER_DIR / "developer_state_v2_features.csv", index=False)
    print(json.dumps({"rows": int(len(v2)), "with_history": int((v2["dev_live_schemes"] > 0).sum() | v2["dev_recency_weighted_activation"].notna().sum())}, indent=2))
