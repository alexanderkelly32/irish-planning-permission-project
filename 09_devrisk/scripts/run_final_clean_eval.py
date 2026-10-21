"""Runner: final clean temporal evaluation.

Train through 2023, evaluate on the untouched 2024-25 cohort. Keeper
models: commencement (devstate v2 + pipeline), FI, appeal, decision
timing, sale (observed 2024-25 sales only). Bootstrap CIs on MAE/AUC.
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
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)


def bootstrap_mae(y, pred, n=500):
    err = np.abs(y - pred)
    out = []
    for _ in range(n):
        idx = RNG.integers(0, len(y), len(y))
        out.append(float(np.mean(err[idx])))
    return [round(float(np.percentile(out, 2.5)), 0), round(float(np.percentile(out, 97.5)), 0)]


if __name__ == "__main__":
    report: dict = {}
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "ReceivedDate", "DecisionDate", "PlanningAuthority",
                    "NumResidentialUnits", "DevelopmentDescription", "AreaofSite"]].drop_duplicates("case_key")
    devstate_v2 = pd.read_csv(settings.SILVER_DIR / "developer_state_v2_features.csv")
    pipeline = pd.read_csv(settings.SILVER_DIR / "pipeline_state_features.csv")
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")

    base = labels.merge(reg, on="case_key", how="inner")
    base = base.merge(devstate_v2, on="case_key", how="left")
    base = base.merge(pipeline, on="case_key", how="left")
    base = base.merge(constraints, on="case_key", how="left")
    base = base.merge(applicants, on="case_key", how="left")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["received_dt"] = pd.to_datetime(base["ReceivedDate"], utc=True, errors="coerce")
    base["received_year"] = base["received_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)

    # ---- Commencement: train grant<=2021 (pool), test = 2022 pool + 2023+
    # all-granted schemes with confirmed BCMS commencement links ----
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed_links = links[links["confidence_band"] == "confirmed"]
    linked_events = confirmed_links.merge(bcms[["bcms_event_id", "commencement_date_dt"]], on="bcms_event_id", how="inner")
    first_comm = linked_events.dropna(subset=["commencement_date_dt"]).groupby("scheme_id")["commencement_date_dt"].min()
    cohort["grant_dt_c"] = pd.to_datetime(cohort["grant_date_dt"], utc=True, errors="coerce")
    ext = cohort[cohort["grant_dt_c"] >= pd.Timestamp("2023-01-01", tz="UTC")].copy()
    ext["commencement_dt"] = ext["case_key"].astype(str).map(first_comm)
    ext["activation_ext"] = (pd.to_datetime(ext["commencement_dt"], utc=True, errors="coerce") - ext["grant_dt_c"]).dt.days
    ext = ext.dropna(subset=["activation_ext"])
    ext["activation"] = ext["activation_ext"].clip(lower=0)
    ext["grant_year"] = ext["grant_dt_c"].dt.year
    ext["log_units"] = np.log1p(pd.to_numeric(ext["NumResidentialUnits"], errors="coerce").fillna(0))
    ext["type_apartment"] = ext["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    ext = ext.merge(devstate_v2, on="case_key", how="left")
    ext = ext.merge(pipeline, on="case_key", how="left")
    ext = ext.merge(constraints, on="case_key", how="left")
    ext = ext.merge(applicants, on="case_key", how="left")
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    comm_train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    comm_test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    comm_test = pd.concat([comm_test, ext.reindex(columns=comm_test.columns)], ignore_index=True)
    COMM_FEATS = ["log_units", "type_apartment", "grant_year", "prior_auth_activation_rate",
                  "applicant_prior_median_activation", "has_applicant",
                  "dev_live_unit_load", "dev_units_completed_24m", "dev_recency_weighted_activation",
                  "dev_x_authority_median_activation", "dev_x_county_median_activation",
                  "1km_granted_not_commenced_units", "3km_granted_not_commenced_units",
                  "3km_progression_ratio", "5km_progression_ratio"]
    comm_feats = [c for c in COMM_FEATS if c in comm.columns]
    model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                      learning_rate=0.05, min_samples_leaf=15, random_state=7)
    model.fit(comm_train[comm_feats].fillna(0.0), comm_train["activation"])
    pred = np.maximum(model.predict(comm_test[comm_feats].fillna(0.0)), 1.0)
    y_te = comm_test["activation"].to_numpy()
    report["commencement"] = {
        "train": int(len(comm_train)), "test": int(len(comm_test)),
        "mae": round(float(np.mean(np.abs(y_te - pred))), 0),
        "mae_ci95": bootstrap_mae(y_te, pred),
        "pm180": round(float(np.mean(np.abs(y_te - pred) <= 180)), 3),
        "pm365": round(float(np.mean(np.abs(y_te - pred) <= 365)), 3),
    }

    # ---- FI: train received<=2023, test 2024-25 ----
    fi = base.dropna(subset=["fi_requested"]).copy()
    fi["fi_flag"] = fi["fi_requested"].astype(int)
    fi_train = fi[fi["received_year"] <= 2023]
    fi_test = fi[fi["received_year"] >= 2024]
    FI_FEATS = ["log_units", "type_apartment", "received_year", "1km_granted_not_commenced_units",
                "3km_granted_not_commenced_units", "5km_granted_not_commenced_units"]
    fi_feats = [c for c in FI_FEATS if c in fi.columns]
    if len(fi_test) >= 20 and fi_test["fi_flag"].nunique() == 2:
        clf = LogisticRegression(C=0.5, max_iter=2000)
        clf.fit(fi_train[fi_feats].fillna(0.0), fi_train["fi_flag"])
        p_fi = clf.predict_proba(fi_test[fi_feats].fillna(0.0))[:, 1]
        report["fi"] = {"train": int(len(fi_train)), "test": int(len(fi_test)),
                        "auc": round(float(roc_auc_score(fi_test["fi_flag"], p_fi)), 3)}

    # ---- Appeal: train received<=2023, test 2024-25 ----
    ap = base.dropna(subset=["appeal_submitted"]).copy()
    ap["appeal_flag"] = ap["appeal_submitted"].astype(int)
    ap_train = ap[ap["received_year"] <= 2023]
    ap_test = ap[ap["received_year"] >= 2024]
    AP_FEATS = ["log_units", "type_apartment", "received_year", "3km_granted_not_commenced_units"]
    ap_feats = [c for c in AP_FEATS if c in ap.columns]
    if len(ap_test) >= 20 and ap_test["appeal_flag"].nunique() == 2:
        clf = LogisticRegression(C=0.5, max_iter=2000)
        clf.fit(ap_train[ap_feats].fillna(0.0), ap_train["appeal_flag"])
        p_ap = clf.predict_proba(ap_test[ap_feats].fillna(0.0))[:, 1]
        report["appeal"] = {"train": int(len(ap_train)), "test": int(len(ap_test)),
                            "auc": round(float(roc_auc_score(ap_test["appeal_flag"], p_ap)), 3)}

    # ---- Sale: train grant<=2021, test 2022+ with observed sales ----
    exit_cols = [c for c in ("sales_linked", "time_to_first_sale_from_grant_days") if c not in base.columns]
    sale = base.merge(exit_labels[["scheme_id"] + exit_cols].rename(columns={"scheme_id": "case_key"}),
                      on="case_key", how="left")
    sold = sale[pd.to_numeric(sale["sales_linked"], errors="coerce").gt(0)].dropna(subset=["time_to_first_sale_from_grant_days"])
    sold["time_to_first_sale_from_grant_days"] = pd.to_numeric(sold["time_to_first_sale_from_grant_days"], errors="coerce")
    sold = sold.dropna(subset=["time_to_first_sale_from_grant_days"])
    sold_train = sold[sold["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    sold_test = sold[sold["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    if len(sold_test) >= 15:
        from sklearn.linear_model import ElasticNet  # noqa: E402
        SALE_FEATS = ["log_units", "type_apartment", "grant_year", "applicant_prior_median_tfs", "has_applicant",
                      "dev_recency_weighted_activation", "3km_granted_not_commenced_units"]
        sale_feats = [c for c in SALE_FEATS if c in sold.columns]
        enet = ElasticNet(alpha=0.5, max_iter=5000)
        y_tr = sold_train["time_to_first_sale_from_grant_days"].to_numpy(dtype=float)
        finite = np.isfinite(y_tr) & (y_tr > -1)
        enet.fit(sold_train[sale_feats].fillna(0.0).to_numpy()[finite], np.log1p(y_tr[finite]))
        p_sale = np.expm1(enet.predict(sold_test[sale_feats].fillna(0.0)))
        y_sale = sold_test["time_to_first_sale_from_grant_days"].to_numpy()
        report["sale"] = {"train": int(len(sold_train)), "test": int(len(sold_test)),
                          "mae": round(float(np.mean(np.abs(y_sale - p_sale))), 0),
                          "mae_ci95": bootstrap_mae(y_sale, p_sale)}

    out = settings.SILVER_DIR / "final_clean_eval.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
