"""Runner: devstate-v2 + local absorption ablations on production models.

Commencement: production quantile GBM + devstate v2 families.
Sale: production ladder (elastic-net) + devstate v2 + absorption families.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import ElasticNet  # noqa: E402

from devrisk import settings  # noqa: E402
from run_dev_sale_ladder import build_cohort  # noqa: E402

RNG = 7


if __name__ == "__main__":
    devstate_v2 = pd.read_csv(settings.SILVER_DIR / "developer_state_v2_features.csv")
    absorption = pd.read_csv(settings.SILVER_DIR / "local_absorption_features.csv")
    dev_v2_cols = [c for c in devstate_v2.columns if c != "case_key"]
    abs_cols = [c for c in absorption.columns if c != "case_key"]
    report: dict = {}

    # ---- Commencement ----
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    comm = labels.merge(register[["case_key", "GrantDate", "DevelopmentDescription", "NumResidentialUnits", "AreaofSite"]].drop_duplicates("case_key"), on="case_key", how="inner")
    comm = comm.merge(constraints, on="case_key", how="left").merge(applicants, on="case_key", how="left")
    comm = comm.merge(devstate_v2, on="case_key", how="left")
    comm["grant_dt"] = pd.to_datetime(comm["GrantDate"], utc=True, errors="coerce")
    comm["activation"] = pd.to_numeric(comm["activation_days"], errors="coerce").clip(lower=0)
    comm = comm[comm["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    comm["grant_year"] = comm["grant_dt"].dt.year
    u = pd.to_numeric(comm["NumResidentialUnits"], errors="coerce")
    s = pd.to_numeric(comm["AreaofSite"], errors="coerce")
    comm["log_units"] = np.log1p(u.fillna(0))
    comm["log_site"] = np.log1p(s.fillna(0))
    comm["density"] = (u / s * 10000.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    comm["type_apartment"] = comm["DevelopmentDescription"].fillna("").str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)
    comm_train = comm[comm["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC")]
    comm_test = comm[comm["grant_dt"] >= pd.Timestamp("2020-01-01", tz="UTC")]
    COMM_BASE = ["log_units", "log_site", "density", "type_apartment", "grant_year",
                 "prior_auth_activation_rate", "applicant_prior_median_activation", "has_applicant"]
    DEV_V1_COLS = ["dev_prior_schemes", "dev_prior_units_granted", "dev_prior_units_commenced",
                   "dev_prior_units_completed", "dev_live_granted_uncommenced", "dev_authorities_count",
                   "dev_recent_median_grant_to_start", "dev_recent_median_start_to_ccc", "dev_type_familiarity"]

    def comm_run(feats):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=RNG)
        model.fit(comm_train[feats].fillna(0.0), comm_train["activation"])
        pred = np.maximum(model.predict(comm_test[feats].fillna(0.0)), 1.0)
        return round(float(np.mean(np.abs(comm_test["activation"].to_numpy() - pred))), 0)

    report["COMMENCEMENT"] = {
        "base": comm_run(COMM_BASE),
        "base_plus_devstate_v1": comm_run(COMM_BASE + [c for c in DEV_V1_COLS if c in comm.columns]),
        "base_plus_devstate_v2": comm_run(COMM_BASE + [c for c in dev_v2_cols if c in comm.columns]),
    }

    # ---- Sale ----
    sale = build_cohort()
    sale = sale[sale["sales_eligible"].fillna(True)]
    sale = sale.merge(devstate_v2, on="case_key", how="left")
    sale = sale.merge(absorption, on="case_key", how="left")
    sale_train = sale[sale["grant_year"] < 2021]
    sale_test = sale[sale["grant_year"] >= 2021]
    SALE_BASE = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month",
                 "price_level", "volume_12m", "momentum", "applicant_prior_median_tfs", "has_applicant"]

    def sale_run(feats):
        y_tr = sale_train["sale_days"].to_numpy()
        y_te = sale_test["sale_days"].to_numpy()
        model = ElasticNet(alpha=0.5, max_iter=5000)
        model.fit(sale_train[feats].fillna(0.0), np.log1p(y_tr))
        pred = np.expm1(model.predict(sale_test[feats].fillna(0.0)))
        return round(float(np.mean(np.abs(y_te - pred))), 0)

    report["SALE"] = {
        "base": sale_run(SALE_BASE),
        "base_plus_devstate_v2": sale_run(SALE_BASE + [c for c in dev_v2_cols if c in sale.columns]),
        "base_plus_absorption": sale_run(SALE_BASE + [c for c in abs_cols if c in sale.columns]),
        "base_plus_both": sale_run(SALE_BASE + [c for c in (dev_v2_cols + abs_cols) if c in sale.columns]),
    }

    out = settings.SILVER_DIR / "devstate_v2_absorption_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
