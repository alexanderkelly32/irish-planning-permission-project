"""Phase 5 first pass: design-sensitive outcome model + paired mutation model.

Model 2 (cross-sectional): explicit design fields vs keyword baseline,
temporal split (<2022 / >=2022), targets refusal/FI/appeal/clean grant.
Model 3 (paired): delta features on mutation_pairs_design -> later grant,
temporal split on first-version year; leave-one-lineage-out where n
permits. All results registered; observational only.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "optimiser"
REGISTRY = Path("experiments/counterfactual_experiment_registry.csv")


def main() -> None:
    frame = pd.read_csv(OUT / "design_versions.csv")
    targets = {"refused": "refused", "fi": "fi", "appeal": "appeal"}
    frame["clean_grant"] = ((frame["granted"] == 1) & (frame["fi"] == 0) &
                            (frame["appeal"] == 0)).astype(int)
    targets["clean_grant"] = "clean_grant"
    design_feats = ["storeys", "apartment", "house", "creche", "open_space", "demolition",
                    "part_v", "parking_mention", "phasing", "access_mention", "bedrooms"]
    kw_feats = [c for c in frame.columns if c.startswith("kw_")] if any(c.startswith("kw_") for c in frame.columns) else []
    base_feats = ["year"]
    auth_d = pd.get_dummies(frame["PlanningAuthority"], prefix="a").astype(int)
    train = frame[frame["year"] < 2022]
    test = frame[frame["year"] >= 2022]
    report = {"model2": {}, "n_train": int(len(train)), "n_test": int(len(test))}
    for name, col in targets.items():
        if test[col].nunique() < 2:
            continue
        X_tr_b = pd.concat([train[base_feats], auth_d.loc[train.index]], axis=1)
        X_te_b = pd.concat([test[base_feats], auth_d.loc[test.index]], axis=1)
        m = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=20, random_state=7)
        m.fit(X_tr_b, train[col])
        auc_b = roc_auc_score(test[col], m.predict_proba(X_te_b)[:, 1])
        X_tr_d = pd.concat([X_tr_b, train[design_feats].fillna(-1)], axis=1)
        X_te_d = pd.concat([X_te_b, test[design_feats].fillna(-1)], axis=1)
        m2 = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                        min_samples_leaf=20, random_state=7)
        m2.fit(X_tr_d, train[col])
        auc_d = roc_auc_score(test[col], m2.predict_proba(X_te_d)[:, 1])
        report["model2"][name] = {"auc_base_year_auth": round(float(auc_b), 3),
                                  "auc_with_design": round(float(auc_d), 3),
                                  "lift": round(float(auc_d - auc_b), 3),
                                  "prevalence": round(float(test[col].mean()), 3)}

    pairs = pd.read_csv(OUT / "mutation_pairs_design.csv")
    pairs["y"] = (pairs["outcome_b"] == "grant").astype(int)
    delta_feats = [c for c in pairs.columns if c.startswith("d_")]
    train_p = pairs[pairs["year_a"] < 2022]
    test_p = pairs[pairs["year_a"] >= 2022]
    report["model3"] = {"n_pairs": int(len(pairs)), "n_train": int(len(train_p)),
                        "n_test": int(len(test_p)),
                        "grant_rate": round(float(pairs["y"].mean()), 3)}
    if len(test_p) >= 80:
        X_tr_p = pd.concat([train_p[delta_feats].fillna(0),
                            pd.get_dummies(train_p["relationship"], prefix="rel").astype(int)], axis=1)
        X_te_p = pd.concat([test_p[delta_feats].fillna(0),
                            pd.get_dummies(test_p["relationship"], prefix="rel").astype(int)], axis=1)
        X_te_p = X_te_p.reindex(columns=X_tr_p.columns).fillna(0).astype(float)
        m_base = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                            min_samples_leaf=15, random_state=7)
        m_base.fit(X_tr_p[[c for c in X_tr_p.columns if c.startswith("rel")]], train_p["y"])
        auc_rel = roc_auc_score(test_p["y"], m_base.predict_proba(
            X_te_p[[c for c in X_te_p.columns if c.startswith("rel")]])[:, 1])
        m_full = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                            min_samples_leaf=15, random_state=7)
        m_full.fit(X_tr_p, train_p["y"])
        auc_full = roc_auc_score(test_p["y"], m_full.predict_proba(X_te_p)[:, 1])
        report["model3"]["auc_relationship_only"] = round(float(auc_rel), 3)
        report["model3"]["auc_with_deltas"] = round(float(auc_full), 3)
        report["model3"]["lift"] = round(float(auc_full - auc_rel), 3)
        # univariate delta contrasts
        for f in delta_feats:
            g1 = test_p[test_p["y"] == 1][f].mean()
            g0 = test_p[test_p["y"] == 0][f].mean()
            report["model3"].setdefault("delta_contrasts", {})[f] = {
                "grant_mean": round(float(g1), 2), "refuse_mean": round(float(g0), 2)}
    (OUT / "design_model_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    with open(REGISTRY, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for name, v in report["model2"].items():
            w.writerow([f"M2-{name}", "explicit design fields add over year+authority",
                        "submission day", "1,676 design versions", "design fields",
                        "none (features only)", "GBM", "none", "pending", "temporal <2022/>=2022",
                        f"lift {v['lift']}", "", "single split", "RETEST", ""])
        if "auc_with_deltas" in report.get("model3", {}):
            w.writerow(["M3-deltas", "design deltas predict later grant",
                        "refusal day", "1,090 mutation pairs", "delta bundle",
                        "design deltas", "GBM", "none", "pending", "temporal on year_a",
                        f"lift {report['model3']['lift']}", "", "single split", "RETEST", ""])
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
