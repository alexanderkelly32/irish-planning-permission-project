"""Confirmatory pass: divergence flag on fresh eras + generalization of
divergence-as-signal across other estimator pairs.

A. Divergence flag re-run on UNTOUCHED eras (train <2020 -> test 2020-21;
train <2021 -> test 2021-22), same 15pp threshold.
B. Generalization: (1) path model vs nn path-frequency on clean-path;
(2) refusal model vs authority static baseline; (3) clean model vs nn
clean rate. Test: does divergence predict higher |residual| in each?
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "report" / "confirmatory"
OUT.mkdir(parents=True, exist_ok=True)

FAMILIES = ["access", "road", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
            "change of use", "apartment", "amenity"]


def build_frame() -> pd.DataFrame:
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
    reg = reg[reg["dur"].between(0, 3000)]
    reg["fi"] = pd.notna(reg["FIRequestDate"]).astype(int)
    reg["appeal"] = pd.notna(reg["AppealSubmittedDate"]).astype(int)
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    reg["year"] = reg["recv"].dt.year
    desc = reg["DevelopmentDescription"].fillna("").str.lower()
    for fam in FAMILIES:
        reg[f"f_{fam}"] = desc.str.contains(fam, regex=False).astype(int)
    reg["desc_len"] = desc.str.len()
    reg["log_units"] = np.log1p(reg["units"])
    reg["y"] = reg["refused"].astype(int)
    reg["clean"] = ((reg["granted"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0) &
                    (reg["dur"] <= 365)).astype(int)
    reg["path"] = "other"
    reg.loc[(reg["granted"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0), "path"] = "direct_grant"
    reg.loc[(reg["granted"] == 1) & (reg["fi"] == 1) & (reg["appeal"] == 0), "path"] = "fi_grant"
    reg.loc[(reg["refused"] == 1) & (reg["fi"] == 1) & (reg["appeal"] == 0), "path"] = "fi_refusal"
    reg.loc[(reg["refused"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0), "path"] = "direct_refusal"
    reg.loc[(reg["granted"] == 1) & (reg["appeal"] == 1), "path"] = "grant_appeal"
    reg.loc[(reg["refused"] == 1) & (reg["appeal"] == 1), "path"] = "refusal_appeal"
    return reg[reg["path"] != "other"].reset_index(drop=True)


def divergence_test(tr: pd.DataFrame, te: pd.DataFrame, feats, auth_d) -> dict:
    X_tr = pd.concat([tr[feats], auth_d.loc[tr.index]], axis=1)
    X_te = pd.concat([te[feats], auth_d.loc[te.index]], axis=1)
    model = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
    model.fit(X_tr, tr["y"])
    te = te.copy()
    te["p_ref"] = model.predict_proba(X_te)[:, 1]
    nn = []
    for i, r in te.iterrows():
        hist = tr[(tr["PlanningAuthority"] == r["PlanningAuthority"])]
        if len(hist) < 15:
            hist = tr
        d = np.sqrt((hist["log_units"] - r["log_units"]) ** 2 * 2.0 +
                    (hist["f_apartment"] - r["f_apartment"]) ** 2 * 4.0 +
                    (hist["units"] - r["units"]) ** 2 / 400.0)
        k = min(15, len(d))
        idx = np.argsort(d)[:k]
        nn.append(float(hist["y"].iloc[idx].mean()))
    te["nn"] = nn
    te["resid"] = np.abs(te["y"] - te["p_ref"])
    te["flag"] = (te["p_ref"] - te["nn"]).abs() > 0.15
    flagged = te[te["flag"]]
    unflagged = te[~te["flag"]]
    out = {"n": int(len(te)), "n_flagged": int(len(flagged)),
           "corr": round(float(te["p_ref"].corr(te["nn"])), 3)}
    if len(flagged) >= 100 and len(unflagged) >= 100:
        out["auc_flagged"] = round(float(roc_auc_score(flagged["y"], flagged["p_ref"])), 3)
        out["auc_unflagged"] = round(float(roc_auc_score(unflagged["y"], unflagged["p_ref"])), 3)
        out["resid_flagged"] = round(float(flagged["resid"].mean()), 3)
        out["resid_unflagged"] = round(float(unflagged["resid"].mean()), 3)
    return out


def main() -> None:
    reg = build_frame()
    feats = ["log_units", "desc_len", "year"] + [f"f_{f}" for f in FAMILIES]
    auth_d = pd.get_dummies(reg["PlanningAuthority"], prefix="a").astype(int)

    out = {"divergence_original_era": None, "divergence_fresh_eras": {},
           "generalizations": {}}
    # original era re-stated
    out["divergence_original_era"] = divergence_test(reg[reg["year"] < 2022], reg[reg["year"] >= 2022], feats, auth_d)
    # fresh eras (train strictly before test era)
    out["divergence_fresh_eras"]["era2020_21"] = divergence_test(
        reg[reg["year"] < 2020], reg[reg["year"].between(2020, 2021)], feats, auth_d)
    out["divergence_fresh_eras"]["era2021_22"] = divergence_test(
        reg[reg["year"] < 2021], reg[reg["year"].between(2021, 2022)], feats, auth_d)

    # Generalization 1: path model vs nn clean-path frequency
    tr = reg[reg["year"] < 2022]
    te = reg[reg["year"] >= 2022].copy()
    pm = LogisticRegression(max_iter=4000, C=1.0)
    X_tr = pd.concat([tr[feats], auth_d.loc[tr.index]], axis=1)
    X_te = pd.concat([te[feats], auth_d.loc[te.index]], axis=1)
    pm.fit(X_tr, tr["path"])
    pp = pm.predict_proba(X_te)
    names = list(pm.classes_)
    clean_idx = [i for i, n in enumerate(names) if n in ("direct_grant", "fi_grant")]
    te["path_clean_p"] = pp[:, clean_idx].sum(axis=1)
    nn_clean = []
    for i, r in te.iterrows():
        hist = tr[tr["PlanningAuthority"] == r["PlanningAuthority"]]
        if len(hist) < 15:
            hist = tr
        d = np.sqrt((hist["log_units"] - r["log_units"]) ** 2 * 2.0 +
                    (hist["f_apartment"] - r["f_apartment"]) ** 2 * 4.0 +
                    (hist["units"] - r["units"]) ** 2 / 400.0)
        k = min(15, len(d))
        idx = np.argsort(d)[:k]
        nn_clean.append(float(hist["path"].iloc[idx].isin(["direct_grant", "fi_grant"]).mean()))
    te["nn_clean"] = nn_clean
    te["clean_true"] = te["path"].isin(["direct_grant", "fi_grant"]).astype(int)
    te["resid_clean"] = np.abs(te["clean_true"] - te["path_clean_p"])
    te["flag_clean"] = (te["path_clean_p"] - te["nn_clean"]).abs() > 0.15
    g1 = {"n_flagged": int(te["flag_clean"].sum())}
    if te["flag_clean"].sum() >= 100 and (~te["flag_clean"]).sum() >= 100:
        g1["resid_clean_flagged"] = round(float(te[te["flag_clean"]]["resid_clean"].mean()), 3)
        g1["resid_clean_unflagged"] = round(float(te[~te["flag_clean"]]["resid_clean"].mean()), 3)
        g1["brier_flagged"] = round(float(np.mean(te[te["flag_clean"]]["resid_clean"] ** 2)), 4)
        g1["brier_unflagged"] = round(float(np.mean(te[~te["flag_clean"]]["resid_clean"] ** 2)), 4)
    out["generalizations"]["clean_path_model_vs_nn"] = g1

    # Generalization 2: refusal model vs authority static baseline
    static = tr.groupby(["PlanningAuthority", "f_apartment"])["y"].agg(["mean", "size"]).rename(
        columns={"mean": "static_rate", "size": "static_n"}).reset_index()
    static["static_rate"] = static["static_rate"].where(static["static_n"] >= 30)
    base = te.copy()
    base["p_ref"] = te["p_ref"] if "p_ref" in te.columns else np.nan
    if "p_ref" not in te.columns:
        model = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                           min_samples_leaf=30, random_state=7)
        model.fit(X_tr, tr["y"])
        base["p_ref"] = model.predict_proba(X_te)[:, 1]
    base = base.merge(static, left_on=["PlanningAuthority", "f_apartment"],
                      right_on=["PlanningAuthority", "f_apartment"], how="left")
    base = base.dropna(subset=["static_rate"])
    base["flag_static"] = (base["p_ref"] - base["static_rate"]).abs() > 0.15
    base["resid"] = np.abs(base["y"] - base["p_ref"])
    g2 = {"n": int(len(base)), "n_flagged": int(base["flag_static"].sum())}
    if base["flag_static"].sum() >= 100 and (~base["flag_static"]).sum() >= 100:
        g2["resid_flagged"] = round(float(base[base["flag_static"]]["resid"].mean()), 3)
        g2["resid_unflagged"] = round(float(base[~base["flag_static"]]["resid"].mean()), 3)
        g2["auc_flagged"] = round(float(roc_auc_score(base[base["flag_static"]]["y"],
                                                      base[base["flag_static"]]["p_ref"])), 3)
        g2["auc_unflagged"] = round(float(roc_auc_score(base[~base["flag_static"]]["y"],
                                                        base[~base["flag_static"]]["p_ref"])), 3)
    out["generalizations"]["refusal_model_vs_static_baseline"] = g2

    (OUT / "confirmatory_divergence.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str)[:5000])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
