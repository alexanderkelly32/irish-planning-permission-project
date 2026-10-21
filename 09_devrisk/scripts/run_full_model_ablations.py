"""Runner: full-model incremental ablations (production models, not
2-feature baselines).

For each deployable model, adds the plan families one at a time and
measures the OOS delta on the SAME protocol the model uses:
- FI v2 (GBM, structured+history+applicant+TF-IDF; train<2020/val2020/holdout>=2021)
- Commencement (quantile GBM, structured+constraints+applicant+TF-IDF;
  train grant<2020, test>=2020)
- Sale ladder (elastic-net log on the ladder feature set;
  train grant<2021, test>=2021)
- Appeal (logistic, structured+TF-IDF; train received<2021, test>=2021)
- Decision timing (GBM p50; train received<2024, test>=2024;
  lineage + team only - pipeline/devstate are grant-time features and
  would leak into decision timing)
- Completion (hazard, morphology features; train commencement<2020,
  test>=2020)
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
from run_appeal_model import build_frame as appeal_build_frame  # noqa: E402

RNG = 7


def load_families() -> dict[str, pd.DataFrame]:
    frames = {}
    for name in ("site_lineage_features", "pipeline_state_features", "developer_state_features", "consultant_team_features"):
        path = settings.SILVER_DIR / f"{name}.csv"
        if path.exists():
            frames[name.split("_features")[0].replace("consultant_team", "team").replace("site_lineage", "lineage").replace("pipeline_state", "pipeline").replace("developer_state", "devstate")] = pd.read_csv(path)
    return frames


def family_cols(frames: dict[str, pd.DataFrame], name: str) -> list[str]:
    if name not in frames:
        return []
    return [c for c in frames[name].columns if c != "case_key"]


if __name__ == "__main__":
    families = load_families()
    report: dict = {}

    # ---------- FI v2 ----------
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    v2 = pd.read_csv(settings.SILVER_DIR / "fi_appeal_labels_v2.csv")
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    fi = register[units.ge(10)].copy()
    fi = fi.merge(v2[["case_key", "fi_requested_v2"]], on="case_key", how="left")
    fi["fi_flag"] = fi["fi_requested_v2"].astype(int)
    fi["received_dt"] = pd.to_datetime(fi["ReceivedDate"], utc=True, errors="coerce")
    fi["received_year"] = fi["received_dt"].dt.year
    fi["log_units"] = np.log1p(units[units.ge(10)].fillna(0))
    fi["site_area"] = pd.to_numeric(fi["AreaofSite"], errors="coerce")
    fi["log_site"] = np.log1p(fi["site_area"].fillna(0))
    fi["type_apartment"] = fi["DevelopmentDescription"].fillna("").str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)
    fi["type_house"] = (fi["DevelopmentDescription"].fillna("").str.contains(r"\b(?:house|houses|dwelling)\b", case=False, regex=True) & ~fi["DevelopmentDescription"].fillna("").str.contains("apartment", case=False)).astype(int)
    for name, frame in families.items():
        fi = fi.merge(frame, on="case_key", how="left")
    fi_train = fi[fi["received_year"] < 2020]
    fi_test = fi[fi["received_year"] >= 2021]
    FI_BASE = ["log_units", "log_site", "type_apartment", "type_house", "received_year"]

    # TF-IDF on descriptions (production v2 uses it).
    from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
    text_tr = tfidf.fit_transform(fi_train["DevelopmentDescription"].fillna("")).toarray()
    text_te = tfidf.transform(fi_test["DevelopmentDescription"].fillna("")).toarray()

    def fi_run(feats, with_text: bool):
        y_tr = fi_train["fi_flag"].to_numpy()
        y_te = fi_test["fi_flag"].to_numpy()
        X_tr = np.hstack([fi_train[feats].fillna(0.0).to_numpy(), text_tr]) if with_text else fi_train[feats].fillna(0.0).to_numpy()
        X_te = np.hstack([fi_test[feats].fillna(0.0).to_numpy(), text_te]) if with_text else fi_test[feats].fillna(0.0).to_numpy()
        model = LogisticRegression(C=0.1, max_iter=2000, solver="liblinear")
        model.fit(X_tr, y_tr)
        p = model.predict_proba(X_te)[:, 1]
        return round(float(roc_auc_score(y_te, p)), 3)

    fi_auc = {"base": fi_run(FI_BASE, True)}
    for name in families:
        fi_auc[f"base_plus_{name}"] = fi_run(FI_BASE + family_cols(families, name), True)
    report["FI"] = fi_auc

    # ---------- Commencement ----------
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    comm = labels.merge(register[["case_key", "GrantDate", "DevelopmentDescription", "NumResidentialUnits", "AreaofSite"]].drop_duplicates("case_key"), on="case_key", how="inner")
    comm = comm.merge(constraints, on="case_key", how="left").merge(applicants, on="case_key", how="left")
    for name, frame in families.items():
        comm = comm.merge(frame, on="case_key", how="left")
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
    def comm_run(feats):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=RNG)
        model.fit(comm_train[feats].fillna(0.0), comm_train["activation"])
        pred = np.maximum(model.predict(comm_test[feats].fillna(0.0)), 1.0)
        return round(float(np.mean(np.abs(comm_test["activation"].to_numpy() - pred))), 0)
    comm_mae = {"base": comm_run(COMM_BASE)}
    for name in families:
        comm_mae[f"base_plus_{name}"] = comm_run(COMM_BASE + family_cols(families, name))
    report["COMMENCEMENT"] = comm_mae

    # ---------- Sale ladder ----------
    from run_dev_sale_ladder import build_cohort  # noqa: E402

    sale = build_cohort()
    sale = sale[sale["sales_eligible"].fillna(True)]
    for name, frame in families.items():
        sale = sale.merge(frame, on="case_key", how="left")
    sale_train = sale[sale["grant_year"] < 2021]
    sale_test = sale[sale["grant_year"] >= 2021]
    SALE_BASE = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month",
                 "price_level", "volume_12m", "momentum", "applicant_prior_median_tfs", "has_applicant"]
    def sale_run(feats):
        y_tr = sale_train["sale_days"].to_numpy()
        y_te = sale_test["sale_days"].to_numpy()
        from sklearn.linear_model import ElasticNet  # noqa: E402
        model = ElasticNet(alpha=0.5, max_iter=5000)
        model.fit(sale_train[feats].fillna(0.0), np.log1p(y_tr))
        pred = np.expm1(model.predict(sale_test[feats].fillna(0.0)))
        return round(float(np.mean(np.abs(y_te - pred))), 0)
    sale_mae = {"base": sale_run(SALE_BASE)}
    for name in families:
        sale_mae[f"base_plus_{name}"] = sale_run(SALE_BASE + family_cols(families, name))
    report["SALE"] = sale_mae

    # ---------- Appeal ----------
    appeal = appeal_build_frame()
    for name, frame in families.items():
        appeal = appeal.merge(frame, on="case_key", how="left")
    ap_train = appeal[appeal["received_year"] < 2021]
    ap_test = appeal[appeal["received_year"] >= 2021]
    AP_BASE = ["log_units", "type_apartment", "type_house", "received_year", "received_month"]
    ap_tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
    ap_text_tr = ap_tfidf.fit_transform(ap_train["description_lower"]).toarray()
    ap_text_te = ap_tfidf.transform(ap_test["description_lower"]).toarray()

    def ap_run(feats, with_text: bool):
        X_tr = np.hstack([ap_train[feats].fillna(0.0).to_numpy(), ap_text_tr]) if with_text else ap_train[feats].fillna(0.0).to_numpy()
        X_te = np.hstack([ap_test[feats].fillna(0.0).to_numpy(), ap_text_te]) if with_text else ap_test[feats].fillna(0.0).to_numpy()
        model = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        model.fit(X_tr, ap_train["appeal_flag"])
        p = model.predict_proba(X_te)[:, 1]
        return round(float(roc_auc_score(ap_test["appeal_flag"], p)), 3)

    ap_auc = {"base": ap_run(AP_BASE, True)}
    for name in families:
        ap_auc[f"base_plus_{name}"] = ap_run(AP_BASE + family_cols(families, name), True)
    report["APPEAL"] = ap_auc

    # ---------- Decision timing (lineage + team only; pipeline/devstate
    # are grant-time features and would leak) ----------
    ge10 = register[units.ge(10)].copy()
    ge10["received_dt"] = pd.to_datetime(ge10["ReceivedDate"], utc=True, errors="coerce")
    ge10["decision_dt"] = pd.to_datetime(ge10["DecisionDate"], utc=True, errors="coerce")
    dec = ge10.dropna(subset=["received_dt", "decision_dt"]).copy()
    dec["duration"] = (dec["decision_dt"] - dec["received_dt"]).dt.days.clip(upper=1500)
    dec["received_year"] = dec["received_dt"].dt.year
    dec["log_units"] = np.log1p(pd.to_numeric(dec["NumResidentialUnits"], errors="coerce").fillna(0))
    dec["type_apartment"] = dec["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    # authority congestion proxy (train-safe): prior received count at authority
    dec = dec.sort_values("received_dt")
    dec["auth_prior_n"] = dec.groupby("PlanningAuthority").cumcount()
    dec = dec.merge(families.get("lineage", pd.DataFrame()), on="case_key", how="left")
    dec = dec.merge(families.get("team", pd.DataFrame()), on="case_key", how="left")
    dec_train = dec[dec["received_year"] < 2024]
    dec_test = dec[dec["received_year"] >= 2024]
    DEC_BASE = ["log_units", "type_apartment", "received_year", "auth_prior_n"]
    def dec_run(feats):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=200, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=20, random_state=RNG)
        model.fit(dec_train[feats].fillna(0.0), dec_train["duration"])
        pred = np.maximum(model.predict(dec_test[feats].fillna(0.0)), 1.0)
        return round(float(np.mean(np.abs(dec_test["duration"].to_numpy() - pred))), 0)
    dec_mae = {"base": dec_run(DEC_BASE)}
    for name in ("lineage", "team"):
        if name in families:
            dec_mae[f"base_plus_{name}"] = dec_run(DEC_BASE + family_cols(families, name))
    report["DECISION"] = dec_mae

    out = settings.SILVER_DIR / "full_model_ablations.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
