"""Runner: subfamily breakdown of the B-tier commencement gain."""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"09_devrisk")

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from devrisk import settings

RNG = 7

if __name__ == "__main__":
    feats = pd.read_csv(settings.SILVER_DIR / "btier_graph_features.csv")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    comm = labels.merge(reg, on="case_key", how="inner").merge(feats, on="case_key", how="left")
    comm["grant_dt"] = pd.to_datetime(comm["GrantDate"], utc=True, errors="coerce")
    comm["activation"] = pd.to_numeric(comm["activation_days"], errors="coerce").clip(lower=0)
    comm = comm[comm["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    comm["grant_year"] = comm["grant_dt"].dt.year
    comm["log_units"] = np.log1p(pd.to_numeric(comm["NumResidentialUnits"], errors="coerce").fillna(0))
    comm["type_apartment"] = comm["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]

    SUBFAMILIES = {
        "cro": ["group_age_days", "dissolved_sisters", "n_companies", "spv_age_at_2026", "spv_dissolved"],
        "doc_complexity": ["n_mentions", "n_roles"],
        "land_cover": ["brownfield_flag", "greenfield_flag"],
        "workload": ["cum_by_auth_type"],
    }
    BASE = ["log_units", "type_apartment", "grant_year"]

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=RNG)
        model.fit(train[cols].fillna(0.0), train["activation"])
        pred = np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)
        return round(float(np.mean(np.abs(test["activation"].to_numpy() - pred))), 0)

    report = {"base": run(BASE)}
    for name, cols in SUBFAMILIES.items():
        cols = [c for c in cols if c in comm.columns]
        report[f"base_plus_{name}"] = run(BASE + cols)
    out = settings.SILVER_DIR / "btier_subfamily_breakdown.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
