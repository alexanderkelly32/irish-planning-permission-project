"""Submission-time condition-family prediction experiment.

Targets: any_financial / any_arch_ecol / any_uisce_drainage / any_roads /
any_phasing / any_precommencement + n_conditions. Features: authority,
log units, apartment flag, grant year, description text indicators.
Temporal split (grant < 2022 train / >= 2022 test). Logistic regression
per family; report AUC, prevalence, n. First-look pilot, small corpus.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "conditions"

TEXT_INDICATORS = ["demolition", "protected structure", "brownfield", "infill",
                   "creche", "retail", "extension", "change of use", "apartment"]


def auc(y, p):
    from sklearn.metrics import roc_auc_score
    try:
        return float(roc_auc_score(y, p))
    except ValueError:
        return float("nan")


def main() -> None:
    corpus = pd.read_csv(OUT / "condition_corpus.csv")
    corpus = corpus.drop_duplicates("case_key")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "DevelopmentDescription",
                                        "NumResidentialUnits"])
    register = register.drop_duplicates("case_key")
    base = corpus.merge(register, on="case_key", how="left")
    base["units"] = pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(1)
    base["log_units"] = np.log1p(base["units"])
    desc = base["DevelopmentDescription"].fillna("").str.lower()
    for ind in TEXT_INDICATORS:
        base[f"desc_{ind.replace(' ', '_')}"] = desc.str.contains(ind, regex=False).astype(int)
    base["desc_len"] = desc.str.len()
    base["type_apartment"] = desc.str.contains("apartment|duplex", regex=True).astype(int)

    families = [c for c in corpus.columns if c.startswith("n_") and c not in ("n_conditions", "n_precommencement")]
    fam_any = {}
    for fam in families:
        name = fam[2:]
        corpus[f"any_{name}"] = (corpus[fam] > 0).astype(int)
        fam_any[name] = f"any_{name}"
    corpus["any_precommencement"] = (corpus["n_precommencement"] > 0).astype(int)
    base = base.merge(corpus[["case_key"] + list(fam_any.values()) + ["any_precommencement"]],
                      on="case_key", how="left")

    auth_dummies = pd.get_dummies(base["authority"], prefix="auth").astype(int)
    feats = ["log_units", "type_apartment", "desc_len"] + \
            [f"desc_{i.replace(' ', '_')}" for i in TEXT_INDICATORS]
    train = base[base["grant_year"] < 2022]
    test = base[base["grant_year"] >= 2022]
    report = {"n_train": int(len(train)), "n_test": int(len(test)),
              "n_usable": int((base["n_conditions"] >= 5).sum()),
              "families": {}}
    for name, col in list(fam_any.items()) + [("precommencement", "any_precommencement")]:
        sub = base[base[col].notna()]
        tr = sub[sub["grant_year"] < 2022]
        te = sub[sub["grant_year"] >= 2022]
        entry = {"prevalence": round(float(sub[col].mean()), 3),
                 "n_labeled": int(len(sub))}
        if len(tr) >= 25 and len(te) >= 15 and te[col].nunique() == 2:
            X_tr = pd.concat([tr[feats].fillna(0.0), auth_dummies.loc[tr.index]], axis=1)
            X_te = pd.concat([te[feats].fillna(0.0), auth_dummies.loc[te.index]], axis=1)
            model = LogisticRegression(max_iter=3000, C=0.5)
            model.fit(X_tr, tr[col].astype(int))
            p = model.predict_proba(X_te)[:, 1]
            entry["auc_test"] = round(auc(te[col].astype(int).to_numpy(), p), 3)
            entry["n_train_family"] = int(len(tr))
            entry["n_test_family"] = int(len(te))
        report["families"][name] = entry

    sub = base[base["n_conditions"] >= 5]
    tr = sub[sub["grant_year"] < 2022]
    te = sub[sub["grant_year"] >= 2022]
    report["n_conditions_regression"] = {"n_train": int(len(tr)), "n_test": int(len(te)),
                                         "median_conditions_train": float(tr["n_conditions"].median()),
                                         "median_conditions_test": float(te["n_conditions"].median())}
    (OUT / "conditions_experiment_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
