"""Runner: B-tier + graph-derived features, then ablation (knock test).

1. Graph-derived: developer degree, consultant two-hop (consultant's
   other developers), parcel prior-depth (have), portfolio siblings.
2. B-tier: CRO group age/status/dissolved sisters, document complexity
   (PDF count/pages/chars per scheme), brownfield/land-cover regex,
   authority workload by application type (rolling, time-safe).
Ablation on commencement / sale / FI vs the frozen benchmark.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = 7


if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    pool = set(labels["case_key"].astype(str))
    reg = register[register["case_key"].astype(str).isin(pool)].drop_duplicates("case_key")

    features = reg[["case_key"]].copy()
    features["case_key"] = features["case_key"].astype(str)

    # ---- CRO derived ----
    cro = pd.read_csv(settings.SILVER_DIR / "applicant_entities_with_cro.csv", dtype=str)
    cro = cro.dropna(subset=["company_number"])
    cro = cro.rename(columns={"group_id": "group_id_cro"}) if "group_id" not in cro.columns else cro
    groups_map = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv")
    cro = cro.merge(groups_map[["case_key", "group_id"]], on="case_key", how="left")
    cro["reg_date"] = pd.to_datetime(cro["incorporation_date"], utc=True, errors="coerce")
    cro["dissolved"] = cro["company_status"].fillna("").str.lower().str.contains("dissolv|strike|liquidat", na=False).astype(int)
    group_age = cro.groupby("group_id").agg(group_min_reg=("reg_date", "min"), dissolved_sisters=("dissolved", "sum"), n_companies=("company_number", "nunique")).reset_index()
    features = features.merge(cro[["case_key", "group_id", "company_status", "reg_date"]], on="case_key", how="left")
    features = features.merge(group_age, on="group_id", how="left")
    features["spv_age_at_2026"] = (pd.Timestamp("2026-01-01", tz="UTC") - features["reg_date"]).dt.days
    features["spv_dissolved"] = features["company_status"].fillna("").str.lower().str.contains("dissolv|strike|liquidat", na=False).astype(int)
    features["group_age_days"] = (pd.Timestamp("2026-01-01", tz="UTC") - features["group_min_reg"]).dt.days

    # ---- Document complexity ----
    mentions = pd.read_csv(settings.SILVER_DIR / "consultant_mentions.csv")
    mentions_by_app = mentions.groupby("appno").agg(n_mentions=("name", "size"), n_roles=("role", "nunique")).reset_index()
    features = features.merge(reg[["case_key", "ApplicationNumber"]].assign(appno=reg["ApplicationNumber"].astype(str).astype(object)),
                              on="case_key", how="left")
    features = features.merge(mentions_by_app.assign(appno=mentions_by_app["appno"].astype(object)), on="appno", how="left")

    # ---- Land-cover / brownfield regex ----
    desc = reg[["case_key", "DevelopmentDescription"]].set_index("case_key")["DevelopmentDescription"].fillna("").astype(str)
    features["brownfield_flag"] = features["case_key"].map(lambda k: int(bool(re.search(r"brownfield|demolition|demolish|redevelop|vacant site|former", desc.get(k, ""), re.I))))
    features["greenfield_flag"] = features["case_key"].map(lambda k: int(bool(re.search(r"greenfield", desc.get(k, ""), re.I))))

    # ---- Authority workload by type (time-safe rolling) ----
    reg2 = register.copy()
    reg2["received_dt"] = pd.to_datetime(reg2["ReceivedDate"], utc=True, errors="coerce")
    reg2 = reg2.dropna(subset=["received_dt"]).sort_values("received_dt")
    reg2["type_cat"] = reg2["ApplicationType"].fillna("").astype(str).str.upper().str[:6]
    reg2["cum_by_auth_type"] = reg2.groupby(["PlanningAuthority", "type_cat"]).cumcount()
    features = features.merge(reg2[["case_key", "cum_by_auth_type"]].drop_duplicates("case_key"), on="case_key", how="left")

    # ---- Graph-derived: developer degree + siblings ----
    devstate_v2 = pd.read_csv(settings.SILVER_DIR / "developer_state_v2_features.csv")
    features = features.merge(devstate_v2[["case_key", "dev_live_schemes", "dev_x_type_n"]], on="case_key", how="left")

    features = features.drop(columns=[c for c in features.columns if c.endswith("_r") or c == "appno"])
    features.to_csv(settings.SILVER_DIR / "btier_graph_features.csv", index=False)

    # ---- Ablation ----
    base = labels.merge(reg[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription", "ReceivedDate"]].drop_duplicates("case_key"), on="case_key", how="inner")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["received_dt"] = pd.to_datetime(base["ReceivedDate"], utc=True, errors="coerce")
    base["received_year"] = base["received_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    base = base.merge(features, on="case_key", how="left")

    BTIER = [c for c in ("group_age_days", "dissolved_sisters", "n_companies", "spv_age_at_2026",
                         "spv_dissolved", "n_mentions", "n_roles", "brownfield_flag", "greenfield_flag",
                         "cum_by_auth_type") if c in features.columns]

    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    comm_train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    comm_test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    COMM_BASE = ["log_units", "type_apartment", "grant_year"]

    def comm_run(feats):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=RNG)
        model.fit(comm_train[feats].fillna(0.0), comm_train["activation"])
        pred = np.maximum(model.predict(comm_test[feats].fillna(0.0)), 1.0)
        return round(float(np.mean(np.abs(comm_test["activation"].to_numpy() - pred))), 0)

    report = {"commencement": {"base": comm_run(COMM_BASE),
                               "base_plus_btier": comm_run(COMM_BASE + BTIER)}}

    fi = base.dropna(subset=["fi_requested"]).copy()
    fi["fi_flag"] = fi["fi_requested"].astype(int)
    fi_train = fi[fi["received_year"] < 2021]
    fi_test = fi[fi["received_year"] >= 2021]
    if fi_test["fi_flag"].nunique() == 2:
        clf = LogisticRegression(C=0.5, max_iter=2000)
        clf.fit(fi_train[["log_units", "type_apartment", "received_year"]].fillna(0.0), fi_train["fi_flag"])
        p_base = clf.predict_proba(fi_test[["log_units", "type_apartment", "received_year"]].fillna(0.0))[:, 1]
        clf2 = LogisticRegression(C=0.5, max_iter=2000)
        clf2.fit(fi_train[["log_units", "type_apartment", "received_year"] + BTIER].fillna(0.0), fi_train["fi_flag"])
        p_bt = clf2.predict_proba(fi_test[["log_units", "type_apartment", "received_year"] + BTIER].fillna(0.0))[:, 1]
        report["fi"] = {"base": round(float(roc_auc_score(fi_test["fi_flag"], p_base)), 3),
                        "base_plus_btier": round(float(roc_auc_score(fi_test["fi_flag"], p_bt)), 3)}

    out = settings.SILVER_DIR / "btier_graph_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
