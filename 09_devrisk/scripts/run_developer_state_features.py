"""Runner: E4 - developer-state + interaction features.

Per scheme at grant date (time-safe from earlier schemes by the same
developer/group): live granted-uncommenced schemes+units, units under
construction, units completed 12/24m, authorities operated in, recent
median grant->start and start->CCC, size trajectory, type familiarity,
SPV count, county-expansion flag. Interactions: developer x authority,
developer x type, developer x size band (shrunk medians). Writes
developer_state_features.csv.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

K = 5.0


if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    entities = pd.read_csv(settings.SILVER_DIR / "applicant_entities.csv")
    groups = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv")
    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")

    frame = labels.merge(register[["case_key", "GrantDate", "PlanningAuthority", "NumResidentialUnits",
                                   "DevelopmentDescription", "ReceivedDate"]].drop_duplicates("case_key"), on="case_key", how="inner")
    frame = frame.merge(entities[["case_key", "entity_key"]], on="case_key", how="left")
    frame = frame.merge(groups[["case_key", "group_id"]], on="case_key", how="left")
    frame = frame.merge(completion[["scheme_id", "t_first_ccc"]], left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["units"] = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce").fillna(0)
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    frame["type"] = np.where(frame["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True), "apartments",
                             np.where(frame["DevelopmentDescription"].fillna("").str.contains(r"\bhouse", case=False, regex=True), "houses", "other"))
    frame["band"] = pd.cut(frame["units"], bins=[0, 29, 99, np.inf], labels=["10-29", "30-99", "100+"]).astype(str)
    frame = frame.sort_values("grant_dt").reset_index(drop=True)

    def median_recent(values: list[float]) -> float:
        recent = [v for v in values[-5:] if pd.notna(v)]
        return float(np.median(recent)) if recent else np.nan

    rows = []
    for i, scheme in frame.iterrows():
        prior = frame.iloc[:i]
        same_group = prior[prior["group_id"].eq(scheme["group_id"])] if pd.notna(scheme["group_id"]) else prior.iloc[0:0]
        same_spv = prior[prior["entity_key"].eq(scheme["entity_key"])] if pd.notna(scheme["entity_key"]) else prior.iloc[0:0]
        base = same_group if len(same_group) >= len(same_spv) else same_spv
        row = {"case_key": str(scheme["case_key"])}
        if len(base):
            row["dev_prior_schemes"] = int(len(base))
            row["dev_prior_units_granted"] = float(base["units"].sum())
            commenced_prior = base[base["activation_linked"].astype(str).str.lower() == "true"]
            row["dev_prior_units_commenced"] = float(commenced_prior["units"].sum()) if len(commenced_prior) else 0.0
            ccc_prior = base[base["t_first_ccc"].notna()]
            row["dev_prior_units_completed"] = float(ccc_prior["units"].sum()) if len(ccc_prior) else 0.0
            live = base[base["activation_linked"].astype(str).str.lower() != "true"]
            row["dev_live_granted_uncommenced"] = int(len(live))
            row["dev_authorities_count"] = int(base["PlanningAuthority"].nunique())
            row["dev_recent_median_grant_to_start"] = median_recent(commenced_prior["activation"].tolist()) if len(commenced_prior) else np.nan
            row["dev_recent_median_start_to_ccc"] = median_recent(ccc_prior["t_first_ccc"].tolist()) if len(ccc_prior) else np.nan
            row["dev_size_trajectory"] = float(scheme["units"]) - float(base["units"].median())
            row["dev_type_familiarity"] = float((base["type"] == scheme["type"]).mean())
            row["dev_county_expansion_flag"] = int(scheme["PlanningAuthority"] not in set(base["PlanningAuthority"]))
            row["dev_spv_count"] = int(base["entity_key"].nunique()) if base["entity_key"].notna().any() else 1
        else:
            for key in ("dev_prior_schemes", "dev_prior_units_granted", "dev_prior_units_commenced",
                        "dev_prior_units_completed", "dev_live_granted_uncommenced", "dev_authorities_count",
                        "dev_size_trajectory", "dev_type_familiarity", "dev_county_expansion_flag", "dev_spv_count"):
                row[key] = 0 if key not in ("dev_type_familiarity",) else np.nan
            row["dev_recent_median_grant_to_start"] = np.nan
            row["dev_recent_median_start_to_ccc"] = np.nan
        # Interaction shrunk medians (time-safe): group x authority / type / band.
        column_map = {"authority": "PlanningAuthority", "type": "type", "band": "band"}
        for suffix, key in (("authority", scheme["PlanningAuthority"]), ("type", scheme["type"]), ("band", scheme["band"])):
            col = column_map[suffix]
            inter = prior[(prior["group_id"].eq(scheme["group_id"])) & (prior[col] == key)] if pd.notna(scheme["group_id"]) else prior.iloc[0:0]
            inter_act = inter[inter["activation"].notna()]
            row[f"dev_x_{suffix}_median_activation"] = float(inter_act["activation"].median()) if len(inter_act) >= 3 else np.nan
        rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(settings.SILVER_DIR / "developer_state_features.csv", index=False)
    summary = {"rows": int(len(out)), "with_dev_history": int(out["dev_prior_schemes"].gt(0).sum()),
               "out": str(settings.SILVER_DIR / "developer_state_features.csv")}
    (settings.SILVER_DIR / "developer_state_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
