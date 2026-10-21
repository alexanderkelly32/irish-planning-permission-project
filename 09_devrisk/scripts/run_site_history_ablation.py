"""Does site history help the refusal model? Direct feature ablation.

Site-history features (zero-day, from KD-tree 150m clusters):
- n_prior_apps_150m, prior_refused_150m, prior_granted_150m
- same_site_ever_refused, same_site_last_decision_granted
- years_since_last_app_150m
Ablation: GBM refusal model +/- site-history features, temporal split.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "usp" / "site_history"
OUT.mkdir(parents=True, exist_ok=True)

FAMILIES = ["access", "road", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
            "change of use", "apartment", "amenity"]


def main() -> None:
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "ITMEasting", "ITMNorthing",
                                   "ReceivedDate", "Decision"])
    reg = reg.drop_duplicates("case_key")
    reg = reg.dropna(subset=["ITMEasting", "ITMNorthing"])
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    dec = reg["Decision"].fillna("").str.lower()
    reg["y"] = dec.str.contains("refus").astype(int)
    reg = reg[dec.str.contains("refus|grant", regex=True)].dropna(subset=["recv"])
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    reg["year"] = reg["recv"].dt.year
    desc = reg["DevelopmentDescription"].fillna("").str.lower()
    for fam in FAMILIES:
        reg[f"f_{fam}"] = desc.str.contains(fam, regex=False).astype(int)
    reg["desc_len"] = desc.str.len()
    reg["log_units"] = np.log1p(reg["units"])
    reg = reg[reg["year"] >= 2012].sort_values("recv").reset_index(drop=True)

    rows = []
    for authority, g in reg.groupby("PlanningAuthority"):
        if len(g) < 2:
            continue
        coords = g[["ITMEasting", "ITMNorthing"]].to_numpy()
        tree = cKDTree(coords)
        parent = list(range(len(g)))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        for a, b in tree.query_pairs(r=150.0, output_type="ndarray"):
            union(int(a), int(b))
        g = g.copy().reset_index(drop=True)
        g["site_id"] = authority + "|" + pd.Series([find(i) for i in range(len(g))]).astype(str)
        rows.append(g)
    frame = pd.concat(rows, ignore_index=True)

    feats_hist = []
    for i, r in frame.iterrows():
        prior = frame[(frame["site_id"] == r["site_id"]) & (frame["recv"] < r["recv"])]
        same_site_prior = prior
        close_prior = frame[(frame["PlanningAuthority"] == r["PlanningAuthority"]) &
                            (frame["recv"] < r["recv"])]
        n_prior = len(prior)
        feats_hist.append({
            "case_key": r["case_key"],
            "n_prior_same_site": n_prior,
            "prior_refused_same_site": int((prior["y"] == 1).sum()) if n_prior else 0,
            "prior_granted_same_site": int((prior["y"] == 0).sum()) if n_prior else 0,
            "same_site_ever_refused": int((prior["y"] == 1).any()) if n_prior else 0,
            "years_since_last_same_site": float((r["recv"] - prior["recv"].max()).days / 365.25) if n_prior else 99.0,
        })
    hist = pd.DataFrame(feats_hist)
    frame = frame.merge(hist, on="case_key", how="left")

    feats = ["log_units", "desc_len", "year"] + [f"f_{f}" for f in FAMILIES]
    hfeats = ["n_prior_same_site", "prior_refused_same_site", "prior_granted_same_site",
              "same_site_ever_refused", "years_since_last_same_site"]
    auth_d = pd.get_dummies(frame["PlanningAuthority"], prefix="a").astype(int)
    train = frame[frame["year"] < 2022]
    test = frame[frame["year"] >= 2022]
    out = {"n": int(len(frame)), "n_train": int(len(train)), "n_test": int(len(test)),
           "pct_with_site_history": round(float((frame["n_prior_same_site"] > 0).mean() * 100), 1)}
    X_tr = pd.concat([train[feats], auth_d.loc[train.index]], axis=1)
    X_te = pd.concat([test[feats], auth_d.loc[test.index]], axis=1)
    m = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                   min_samples_leaf=30, random_state=7)
    m.fit(X_tr, train["y"])
    auc_base = roc_auc_score(test["y"], m.predict_proba(X_te)[:, 1])
    X_tr_h = pd.concat([X_tr, train[hfeats]], axis=1)
    X_te_h = pd.concat([X_te, test[hfeats]], axis=1)
    m_h = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                     min_samples_leaf=30, random_state=7)
    m_h.fit(X_tr_h, train["y"])
    auc_hist = roc_auc_score(test["y"], m_h.predict_proba(X_te_h)[:, 1])
    out["auc_base"] = round(float(auc_base), 3)
    out["auc_with_site_history"] = round(float(auc_hist), 3)
    out["lift"] = round(float(auc_hist - auc_base), 3)
    sub = test[test["n_prior_same_site"] > 0]
    if len(sub) >= 200:
        X_te2 = pd.concat([sub[feats], auth_d.loc[sub.index]], axis=1)
        X_te2_h = pd.concat([X_te2, sub[hfeats]], axis=1)
        out["auc_base_sites_with_history"] = round(float(roc_auc_score(sub["y"], m.predict_proba(X_te2)[:, 1])), 3)
        out["auc_hist_sites_with_history"] = round(float(roc_auc_score(sub["y"], m_h.predict_proba(X_te2_h)[:, 1])), 3)
        out["lift_on_history_sites"] = round(float(out["auc_hist_sites_with_history"] - out["auc_base_sites_with_history"]), 3)
    (OUT / "site_history_ablation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
