"""Sprint 4: E3 Condition Burden (rolling-origin stress) + E4 Clean
Planning Outcome.

E3: rolling-origin AUC for pre-commencement + financial family models;
empirical severity associations (resubmission, compliance cycles,
commencement duration - checked, not resurrected if null).
E4: clean outcome = grant & no FI & no appeal & decision <= 12m, on the
full register; calibration + how different it is from refusal probability.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint4"

TEXT_INDICATORS = ["demolition", "protected structure", "brownfield", "infill",
                   "creche", "retail", "extension", "change of use", "apartment"]


def main() -> None:
    corpus = pd.read_csv(SILVER / "conditions" / "condition_corpus.csv").drop_duplicates("case_key")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "DevelopmentDescription", "NumResidentialUnits"])
    register = register.drop_duplicates("case_key")
    base = corpus.merge(register, on="case_key", how="left")
    base["units"] = pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(1)
    base["log_units"] = np.log1p(base["units"])
    desc = base["DevelopmentDescription"].fillna("").str.lower()
    for ind in TEXT_INDICATORS:
        base[f"desc_{ind.replace(' ', '_')}"] = desc.str.contains(ind, regex=False).astype(int)
    base["desc_len"] = desc.str.len()
    base["type_apartment"] = desc.str.contains("apartment|duplex", regex=True).astype(int)
    base["y_pre"] = (base["n_precommencement"] > 0).astype(int)
    base["y_fin"] = (base["n_financial"] > 0).astype(int)
    fam_cols = [c for c in corpus.columns if c.startswith("n_") and c not in
                ("n_conditions", "n_precommencement")]
    base["n_families"] = (base[fam_cols] > 0).sum(axis=1)
    auth_d = pd.get_dummies(base["authority"], prefix="a").astype(int)
    feats = ["log_units", "type_apartment", "desc_len"] + \
            [f"desc_{i.replace(' ', '_')}" for i in TEXT_INDICATORS]
    e3 = {"rolling_origin": {}}
    for cutoff in (2020, 2021, 2022):
        tr = base[base["grant_year"] < cutoff]
        te = base[base["grant_year"] >= cutoff]
        for name, target in [("precommencement", "y_pre"), ("financial", "y_fin")]:
            if len(tr) >= 25 and len(te) >= 15 and te[target].nunique() == 2:
                model = LogisticRegression(max_iter=3000, C=0.5)
                model.fit(pd.concat([tr[feats].fillna(0.0), auth_d.loc[tr.index]], axis=1), tr[target])
                p = model.predict_proba(pd.concat([te[feats].fillna(0.0), auth_d.loc[te.index]], axis=1))[:, 1]
                e3["rolling_origin"][f"cutoff{cutoff}_{name}"] = {
                    "n_train": int(len(tr)), "n_test": int(len(te)),
                    "auc": round(float(roc_auc_score(te[target], p)), 3),
                    "prevalence": round(float(te[target].mean()), 3)}
    e3["n_families_median"] = float(base["n_families"].median())

    report = {"e3_conditions": e3}
    (OUT / "sprint4_e3_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # ---- E4 clean outcome on the full register ----
    import re
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "ReceivedDate", "DecisionDate",
                                   "FIRequestDate", "AppealSubmittedDate", "Decision"])
    reg = reg.drop_duplicates("case_key")
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["dec"] = pd.to_datetime(reg["DecisionDate"], utc=True, errors="coerce").dt.tz_localize(None)
    dec = reg["Decision"].fillna("").str.lower()
    reg["granted"] = dec.str.contains("grant|conditional|unconditional", regex=True).astype(int)
    reg["refused"] = dec.str.contains("refus").astype(int)
    reg = reg[((reg["granted"] == 1) | (reg["refused"] == 1))].dropna(subset=["recv", "dec"])
    reg["dur"] = (reg["dec"] - reg["recv"]).dt.days
    reg["fi"] = pd.notna(reg["FIRequestDate"]).astype(int)
    reg["appeal"] = pd.notna(reg["AppealSubmittedDate"]).astype(int)
    reg["clean"] = ((reg["granted"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0) &
                    (reg["dur"] <= 365)).astype(int)
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    reg["year"] = reg["recv"].dt.year
    reg = reg[reg["year"] >= 2015]
    desc2 = reg["DevelopmentDescription"].fillna("").str.lower()
    for fam in ["access", "road", "parking", "storey", "drainage", "water", "flood",
                "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
                "change of use", "apartment", "amenity"]:
        reg[f"f_{fam}"] = desc2.str.contains(fam, regex=False).astype(int)
    reg["desc_len"] = desc2.str.len()
    reg["log_units"] = np.log1p(reg["units"])
    feats4 = ["log_units", "desc_len", "year"] + [f"f_{f}" for f in
              ["access", "road", "parking", "storey", "drainage", "water", "flood",
               "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
               "change of use", "apartment", "amenity"]]
    a4 = pd.get_dummies(reg["PlanningAuthority"], prefix="a").astype(int)
    tr4 = reg[reg["year"] < 2022]
    te4 = reg[reg["year"] >= 2022]
    model = LogisticRegression(max_iter=3000, C=1.0)
    model.fit(pd.concat([tr4[feats4], a4.loc[tr4.index]], axis=1), tr4["clean"])
    p_clean = model.predict_proba(pd.concat([te4[feats4], a4.loc[te4.index]], axis=1))[:, 1]
    p_grant = reg.loc[te4.index, "granted"]
    model_g = LogisticRegression(max_iter=3000, C=1.0)
    model_g.fit(pd.concat([tr4[feats4], a4.loc[tr4.index]], axis=1), tr4["granted"])
    p_g = model_g.predict_proba(pd.concat([te4[feats4], a4.loc[te4.index]], axis=1))[:, 1]
    e4 = {
        "n_train": int(len(tr4)), "n_test": int(len(te4)),
        "prevalence_clean": round(float(te4["clean"].mean()), 3),
        "prevalence_grant": round(float(te4["granted"].mean()), 3),
        "clean_model": {"auc": round(float(roc_auc_score(te4["clean"], p_clean)), 3),
                        "brier": round(float(brier_score_loss(te4["clean"], p_clean)), 4)},
        "grant_model_auc": round(float(roc_auc_score(te4["granted"], p_g)), 3),
        "corr_clean_pred_vs_grant_pred": round(float(np.corrcoef(p_clean, p_g)[0, 1]), 3),
        "clean_given_grant_share": round(float(te4.loc[te4["granted"] == 1, "clean"].mean()), 3),
    }
    report["e4_clean_outcome"] = e4
    (OUT / "sprint4_e3_e4_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
