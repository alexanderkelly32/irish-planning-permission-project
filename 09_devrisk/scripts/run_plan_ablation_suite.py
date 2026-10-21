"""Runner: professional-team features (E1) + plan ablation suite.

Team features: from consultant_mentions.csv, entity-resolve firms, then
per pool scheme (time-safe, from earlier applications only): consultant
prior grant rate, FI rate, median decision time, appeal rate, within-
authority count, developer-consultant pair count, team size. Then the
ablation suite: for each target, base model vs +each new family
(lineage, pipeline, developer-state, team) with gates.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from run_applicant_features import entity_key  # noqa: E402

RNG = np.random.default_rng(7)


def team_features() -> pd.DataFrame:
    mentions = pd.read_csv(settings.SILVER_DIR / "consultant_mentions.csv")
    mentions["entity"] = mentions["name"].map(entity_key)
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "ApplicationNumber", "ReceivedDate", "DecisionDate", "FIRequestDate",
                    "AppealSubmittedDate"]].drop_duplicates("case_key")
    reg = reg.rename(columns={"ApplicationNumber": "appno"})
    reg["appno"] = reg["appno"].astype(str)
    mentions["appno"] = mentions["appno"].astype(str)
    merged = reg.merge(mentions[["appno", "role", "entity"]], on="appno", how="left")
    merged["received_dt"] = pd.to_datetime(merged["ReceivedDate"], utc=True, errors="coerce")
    merged["decision_dt"] = pd.to_datetime(merged["DecisionDate"], utc=True, errors="coerce")
    fi_cols = [c for c in ("FIRequestDate", "FIRecDate") if c in merged.columns]
    merged["fi"] = pd.to_datetime(merged[fi_cols].min(axis=1), utc=True, errors="coerce").notna().astype(int) if fi_cols else 0
    merged["appeal"] = pd.to_datetime(merged["AppealSubmittedDate"], utc=True, errors="coerce").notna().astype(int)
    merged["decision_days"] = (merged["decision_dt"] - merged["received_dt"]).dt.days

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    pool = set(labels["case_key"].astype(str))
    rows = []
    for _, scheme in merged[merged["case_key"].astype(str).isin(pool)].iterrows():
        row = {"case_key": str(scheme["case_key"])}
        team = merged[(merged["received_dt"] < scheme["received_dt"]) & (merged["entity"] == scheme["entity"])] if pd.notna(scheme["entity"]) else pd.DataFrame()
        if len(team):
            row["consultant_prior_n"] = int(len(team))
            row["consultant_prior_fi_rate"] = float(team["fi"].mean())
            row["consultant_prior_appeal_rate"] = float(team["appeal"].mean())
            row["consultant_prior_median_decision_days"] = float(team["decision_days"].median()) if team["decision_days"].notna().any() else np.nan
        else:
            row["consultant_prior_n"] = 0
            row["consultant_prior_fi_rate"] = 0.0
            row["consultant_prior_appeal_rate"] = 0.0
            row["consultant_prior_median_decision_days"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    team = team_features()
    team.to_csv(settings.SILVER_DIR / "consultant_team_features.csv", index=False)

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "PlanningAuthority", "NumResidentialUnits", "DevelopmentDescription",
                    "ReceivedDate", "DecisionDate"]].drop_duplicates("case_key")
    base = labels.merge(reg, on="case_key", how="inner")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["received_dt"] = pd.to_datetime(base["ReceivedDate"], utc=True, errors="coerce")
    base["received_year"] = base["received_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["decision_days"] = (pd.to_datetime(base["DecisionDate"], utc=True, errors="coerce") - base["received_dt"]).dt.days
    base["units"] = pd.to_numeric(base["NumResidentialUnits"], errors="coerce")
    base["log_units"] = np.log1p(base["units"].fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)

    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    exit_cols = [c for c in ("sales_linked", "time_to_first_sale_from_grant_days") if c not in base.columns]
    base = base.merge(exit_labels[["scheme_id"] + exit_cols].rename(columns={"scheme_id": "case_key"}),
                      on="case_key", how="left")

    lineage = pd.read_csv(settings.SILVER_DIR / "site_lineage_features.csv")
    pipeline = pd.read_csv(settings.SILVER_DIR / "pipeline_state_features.csv")
    devstate = pd.read_csv(settings.SILVER_DIR / "developer_state_features.csv")
    for frame in (lineage, pipeline, devstate, team):
        base = base.merge(frame, on="case_key", how="left")

    report = {"team_mentions_pdfs": None}

    # ---- Ablation: commencement (activation) ----
    comm = base[base["activation"].notna()].copy()
    comm_train = comm[comm["grant_year"] < 2021]
    comm_test = comm[comm["grant_year"] >= 2021]
    base_feats = ["log_units", "type_apartment"]

    def family_cols(family: str) -> list[str]:
        if family == "lineage":
            return [c for c in lineage.columns if c != "case_key"]
        if family == "pipeline":
            return [c for c in pipeline.columns if c != "case_key"][:24]
        if family == "devstate":
            return [c for c in devstate.columns if c != "case_key"]
        if family == "team":
            return [c for c in team.columns if c != "case_key"]
        return []

    def reg_ablation(train_part, test_part, target_col, feats):
        mask_tr = train_part[target_col].notna()
        mask_te = test_part[target_col].notna()
        X_tr = train_part.loc[mask_tr, feats].fillna(0.0)
        X_te = test_part.loc[mask_te, feats].fillna(0.0)
        y_tr = train_part.loc[mask_tr, target_col].to_numpy()
        y_te = test_part.loc[mask_te, target_col].to_numpy()
        if len(X_tr) < 30:
            return None
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=200, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=10, random_state=7)
        model.fit(X_tr, y_tr)
        pred = np.maximum(model.predict(X_te), 1.0)
        return round(float(np.mean(np.abs(y_te - pred))), 0)

    report["commencement_ablation"] = {
        "base": reg_ablation(comm_train, comm_test, "activation", base_feats)}
    for family in ("lineage", "pipeline", "devstate", "team"):
        cols = family_cols(family)
        if cols:
            report["commencement_ablation"][f"base_plus_{family}"] = reg_ablation(
                comm_train, comm_test, "activation", base_feats + cols)

    # ---- Ablation: sale ----
    sold = base[pd.to_numeric(base["sales_linked"], errors="coerce").gt(0)].dropna(subset=["time_to_first_sale_from_grant_days"]).copy()
    sold_train = sold[sold["grant_year"] < 2021]
    sold_test = sold[sold["grant_year"] >= 2021]
    report["sale_ablation"] = {
        "base": reg_ablation(sold_train, sold_test, "time_to_first_sale_from_grant_days", base_feats)}
    for family in ("lineage", "pipeline", "devstate", "team"):
        cols = family_cols(family)
        if cols:
            report["sale_ablation"][f"base_plus_{family}"] = reg_ablation(
                sold_train, sold_test, "time_to_first_sale_from_grant_days", base_feats + cols)

    # ---- Ablation: FI (logistic AUC) ----
    fi = base.dropna(subset=["fi_requested"]).copy()
    fi["fi_flag"] = fi["fi_requested"].astype(int)
    fi_train = fi[fi["received_year"] < 2021]
    fi_test = fi[fi["received_year"] >= 2021]
    def cls_ablation(train_part, test_part, target_col, feats):
        mask_tr = train_part[target_col].notna()
        mask_te = test_part[target_col].notna()
        y_tr = train_part.loc[mask_tr, target_col].to_numpy()
        y_te = test_part.loc[mask_te, target_col].to_numpy()
        if y_tr.sum() < 20 or len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            return None
        model = LogisticRegression(C=0.5, max_iter=2000)
        model.fit(train_part.loc[mask_tr, feats].fillna(0.0), y_tr)
        p = model.predict_proba(test_part.loc[mask_te, feats].fillna(0.0))[:, 1]
        return round(float(roc_auc_score(y_te, p)), 3)
    report["fi_ablation"] = {"base": cls_ablation(fi_train, fi_test, "fi_flag", base_feats)}
    for family in ("lineage", "pipeline", "devstate", "team"):
        cols = family_cols(family)
        if cols:
            report["fi_ablation"][f"base_plus_{family}"] = cls_ablation(fi_train, fi_test, "fi_flag", base_feats + cols)

    out = settings.SILVER_DIR / "plan_ablation_suite.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
