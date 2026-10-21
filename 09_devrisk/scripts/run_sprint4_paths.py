"""Sprint 4: E1 Planning Path Distribution + E2 Tail-Risk Score.

E1: competing-risk style multinomial path model (submission-time features,
temporal split) vs component binary models; full path-distribution
calibration; empirical stratified baseline. E2: adverse-outcome flags +
whether tail-risk ranking adds beyond refusal probability; conditional
delay and percentile time-to-certainty by risk decile.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint4"
OUT.mkdir(parents=True, exist_ok=True)

FAMILIES = ["access", "road", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
            "change of use", "apartment", "amenity"]


def main() -> None:
    import re
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "ReceivedDate", "DecisionDate",
                                   "FIRequestDate", "FIRecDate", "AppealSubmittedDate",
                                   "AppealDecisionDate", "AppealStatus", "Decision"])
    reg = reg.drop_duplicates("case_key")
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["dec"] = pd.to_datetime(reg["DecisionDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["fi"] = pd.notna(reg["FIRequestDate"])
    reg["appeal"] = pd.notna(reg["AppealSubmittedDate"])
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    dec = reg["Decision"].fillna("").str.lower()
    reg["granted"] = dec.str.contains("grant|conditional|unconditional", regex=True).astype(int)
    reg["refused"] = dec.str.contains("refus").astype(int)
    reg = reg[((reg["granted"] == 1) | (reg["refused"] == 1))]
    reg = reg.dropna(subset=["recv", "dec"])
    reg["duration_days"] = (reg["dec"] - reg["recv"]).dt.days
    reg = reg[reg["duration_days"].between(0, 3000)]
    reg["year"] = reg["recv"].dt.year
    desc = reg["DevelopmentDescription"].fillna("").str.lower()
    for fam in FAMILIES:
        reg[f"f_{fam}"] = desc.str.contains(fam, regex=False).astype(int)
    reg["desc_len"] = desc.str.len()
    reg["log_units"] = np.log1p(reg["units"])

    reg["path"] = "other"
    reg.loc[(reg["granted"] == 1) & ~reg["fi"] & ~reg["appeal"], "path"] = "direct_grant"
    reg.loc[(reg["granted"] == 1) & reg["fi"] & ~reg["appeal"], "path"] = "fi_grant"
    reg.loc[(reg["refused"] == 1) & reg["fi"] & ~reg["appeal"], "path"] = "fi_refusal"
    reg.loc[(reg["refused"] == 1) & ~reg["fi"] & ~reg["appeal"], "path"] = "direct_refusal"
    reg.loc[(reg["granted"] == 1) & reg["appeal"], "path"] = "grant_appeal"
    reg.loc[(reg["refused"] == 1) & reg["appeal"], "path"] = "refusal_appeal"
    reg = reg[reg["path"] != "other"]
    path_counts = reg["path"].value_counts()
    keep_paths = path_counts[path_counts >= 200].index
    reg = reg[reg["path"].isin(keep_paths)]

    feats = ["log_units", "desc_len", "year"] + [f"f_{f}" for f in FAMILIES]
    auth_d = pd.get_dummies(reg["PlanningAuthority"], prefix="a").astype(int)
    train = reg[reg["year"] < 2022]
    test = reg[reg["year"] >= 2022]
    train = train[train["path"].isin(keep_paths)]
    test = test[test["path"].isin(keep_paths)]
    e1 = {"path_support_train": train["path"].value_counts().to_dict(),
          "path_support_test": test["path"].value_counts().to_dict(),
          "n_train": int(len(train)), "n_test": int(len(test))}

    X_tr = pd.concat([train[feats], auth_d.loc[train.index]], axis=1)
    X_te = pd.concat([test[feats], auth_d.loc[test.index]], axis=1)
    path_model = LogisticRegression(max_iter=4000, C=1.0)
    path_model.fit(X_tr, train["path"])
    p_path = path_model.predict_proba(X_te)
    path_names = list(path_model.classes_)
    log_loss = float(-np.mean(np.log(p_path[np.arange(len(test)),
                              [path_names.index(p) for p in test["path"]]] + 1e-12)))
    e1["path_model_log_loss"] = round(log_loss, 4)
    # empirical stratified baseline: authority x year mode proportions
    strat = train.groupby(["PlanningAuthority", "year"])["path"].value_counts(normalize=True).unstack().fillna(0)
    base_ll = []
    for _, r in test.iterrows():
        row = strat.loc[(r["PlanningAuthority"], r["year"])] if (r["PlanningAuthority"], r["year"]) in strat.index else None
        if row is None or len(row) == 0:
            row = train["path"].value_counts(normalize=True)
        base_ll.append(np.log(row.get(r["path"], 1e-12) + 1e-12))
    e1["stratified_baseline_log_loss"] = round(float(-np.mean(base_ll)), 4)

    # calibration of P(clean paths) composite: direct_grant + fi_grant
    clean_true = test["path"].isin(["direct_grant", "fi_grant"]).astype(int)
    clean_pred = p_path[:, [path_names.index(p) for p in ("direct_grant", "fi_grant") if p in path_names]].sum(axis=1)
    e1["clean_path"] = {"prevalence": round(float(clean_true.mean()), 3),
                        "brier": round(float(brier_score_loss(clean_true, clean_pred)), 4),
                        "auc": round(float(roc_auc_score(clean_true, clean_pred)), 3)}
    e1["grant_share_of_clean"] = round(float((test["path"] == "direct_grant").mean()), 3)

    # ---- E2 tail risk ----
    e2 = {}
    flags = {"late6m": reg["duration_days"] > 183, "late12m": reg["duration_days"] > 365,
             "late18m": reg["duration_days"] > 548, "late24m": reg["duration_days"] > 730}
    reg["refusal"] = reg["refused"].astype(int)
    for name, mask in flags.items():
        reg[f"flag_{name}"] = mask.astype(int)
    tr = reg[reg["year"] < 2022]
    te = reg[reg["year"] >= 2022]
    for name in flags:
        tr_f = tr[tr[f"flag_{name}"].notna()]
        te_f = te[te[f"flag_{name}"].notna()]
        gbm = GradientBoostingClassifier(n_estimators=250, max_depth=3,
                                         learning_rate=0.05, min_samples_leaf=30, random_state=7)
        Xt = pd.concat([tr_f[feats], auth_d.loc[tr_f.index]], axis=1)
        Xv = pd.concat([te_f[feats], auth_d.loc[te_f.index]], axis=1)
        gbm.fit(Xt, tr_f[f"flag_{name}"])
        p_tail = gbm.predict_proba(Xv)[:, 1]
        auc_tail = roc_auc_score(te_f[f"flag_{name}"], p_tail)
        refusal_gbm = GradientBoostingClassifier(n_estimators=250, max_depth=3,
                                                 learning_rate=0.05, min_samples_leaf=30, random_state=7)
        refusal_gbm.fit(Xt, tr_f["refusal"])
        p_ref = refusal_gbm.predict_proba(Xv)[:, 1]
        auc_ref_only = roc_auc_score(te_f[f"flag_{name}"], p_ref)
        e2[name] = {"prevalence": round(float(te_f[f"flag_{name}"].mean()), 3),
                    "auc_tail_model": round(float(auc_tail), 3),
                    "auc_refusal_as_tail_score": round(float(auc_ref_only), 3),
                    "lift_over_refusal": round(float(auc_tail - auc_ref_only), 3)}
    e2["refusal_flag_auc_refusal_model"] = round(float(roc_auc_score(
        te["refusal"], LogisticRegression(max_iter=3000).fit(X_tr, train["refused"]).predict_proba(X_te)[:, 1])), 3)

    report = {"e1_paths": e1, "e2_tail_risk": e2}
    (OUT / "sprint4_e1_e2_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
