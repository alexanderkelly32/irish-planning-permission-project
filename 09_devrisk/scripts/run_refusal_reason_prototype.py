"""Refusal-reason prediction prototype (zero-day target c).

Zero-day features -> primary refusal tag. Corpus: refusal_reasons_cases_
master.csv (1,411 labelled cases). Temporal split (decision year <2022 /
>=2022); high-confidence subset as cleaner eval. Metrics: per-tag AUC/AP,
top-1/top-3 recall, calibration; baselines: prevalence, description keyword.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "usp" / "refusal_reasons"
OUT.mkdir(parents=True, exist_ok=True)

FAMILIES = ["access", "road", "traffic", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "tree", "archaeolog", "heritage", "protected", "design", "density",
            "apartment", "amenity", "open space", "demolition", "retail"]


def main() -> None:
    m = pd.read_csv("03_refusal/current/refusal_reasons_cases_master.csv", low_memory=False)
    m["case_key"] = m["council"].astype(str) + "__" + m["application_number"].astype(str)
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "ReceivedDate"])
    reg = reg.drop_duplicates("case_key")
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    reg["year"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.year
    base = m.merge(reg, on="case_key", how="inner")
    base = base.dropna(subset=["case_top_primary_tag"])
    desc = base["DevelopmentDescription"].fillna("").str.lower()
    for fam in FAMILIES:
        base[f"f_{fam}"] = desc.str.contains(fam, regex=False).astype(int)
    base["desc_len"] = desc.str.len()
    base["log_units"] = np.log1p(base["units"])
    base["year"] = pd.to_numeric(base["decision_date"].str[:4], errors="coerce").fillna(base["year"])

    tags = ["design_layout", "land_use_policy", "density_scale", "traffic_access",
            "premature_or_info_gap"]
    for t in tags:
        base[f"y_{t}"] = (base["case_top_primary_tag"] == t).astype(int)
    base["high_conf"] = (base["tag_confidence"].astype(str).str.lower() == "high").astype(int)

    train = base[base["year"] < 2022]
    test = base[base["year"] >= 2022]
    report = {"n": int(len(base)), "n_train": int(len(train)), "n_test": int(len(test)),
              "n_high_conf": int(base["high_conf"].sum()),
              "tag_distribution": base["case_top_primary_tag"].value_counts().to_dict(),
              "tags": {}}
    feats = ["log_units", "desc_len", "year"] + [f"f_{f}" for f in FAMILIES]
    auth_d = pd.get_dummies(base["PlanningAuthority"], prefix="a").astype(int)
    for t in tags:
        tr, te = train[train[f"y_{t}"].notna()], test[test[f"y_{t}"].notna()]
        entry = {"n_pos_test": int(te[f"y_{t}"].sum()),
                 "prevalence": round(float(base[f"y_{t}"].mean()), 3)}
        if te[f"y_{t}"].nunique() < 2 or tr[f"y_{t}"].sum() < 20:
            entry["status"] = "insufficient"
            report["tags"][t] = entry
            continue
        X_tr = pd.concat([tr[feats], auth_d.loc[tr.index]], axis=1)
        X_te = pd.concat([te[feats], auth_d.loc[te.index]], axis=1)
        gbm = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                         min_samples_leaf=10, random_state=7)
        gbm.fit(X_tr, tr[f"y_{t}"])
        p = gbm.predict_proba(X_te)[:, 1]
        entry["auc"] = round(float(roc_auc_score(te[f"y_{t}"], p)), 3)
        entry["ap"] = round(float(average_precision_score(te[f"y_{t}"], p)), 3)
        kw = LogisticRegression(max_iter=3000, C=1.0)
        kw_cols = [c for c in feats if c.startswith("f_")]
        kw.fit(tr[kw_cols], tr[f"y_{t}"])
        p_kw = kw.predict_proba(te[kw_cols])[:, 1]
        entry["auc_keyword"] = round(float(roc_auc_score(te[f"y_{t}"], p_kw)), 3)
        report["tags"][t] = entry

    # top-k recall on the full tag set (top-8 tags)
    all_tags = base["case_top_primary_tag"].value_counts().head(8).index.tolist()
    probs = {}
    for t in all_tags:
        base_t = base.copy()
        base_t[f"y_t"] = (base_t["case_top_primary_tag"] == t).astype(int)
        tr = base_t[base_t["year"] < 2022]
        te = base_t[base_t["year"] >= 2022]
        if tr["y_t"].sum() < 20:
            probs[t] = np.full(len(te), float(tr["y_t"].mean()))
            continue
        X_tr = pd.concat([tr[feats], auth_d.loc[tr.index]], axis=1)
        X_te = pd.concat([te[feats], auth_d.loc[te.index]], axis=1)
        g = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=10, random_state=7)
        g.fit(X_tr, tr["y_t"])
        probs[t] = g.predict_proba(X_te)[:, 1]
    p_df = pd.DataFrame(probs, index=test.index)
    top1 = top2 = top3 = 0
    prev_rank = base.groupby("case_top_primary_tag").size().sort_values(ascending=False).head(3).index.tolist()
    base_top3 = 0
    for _, r in test.iterrows():
        actual = r["case_top_primary_tag"]
        ranked = p_df.loc[r.name].sort_values(ascending=False).index.tolist()
        top1 += int(ranked[0] == actual)
        top2 += int(actual in ranked[:2])
        top3 += int(actual in ranked[:3])
        base_top3 += int(actual in prev_rank)
    report["top_recall"] = {"top1": round(top1 / max(len(test), 1), 3),
                            "top2": round(top2 / max(len(test), 1), 3),
                            "top3": round(top3 / max(len(test), 1), 3),
                            "baseline_top3_prevalence": round(base_top3 / max(len(test), 1), 3)}
    (OUT / "refusal_reason_prototype.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
