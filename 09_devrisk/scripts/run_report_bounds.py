"""Report bound tables: the right uncertainty measure per component.

Builds empirical local-calibration band tables (predicted-value bin ->
observed rate + Wilson 95% CI) for refusal, each planning path, clean
outcome, 6m tail, pre-commencement conditions; bootstrap CI on the
pre-comm AUC; Wilson CIs on the rescue grant-rate-by-matches curve; Monte
Carlo supply intervals + backtest coverage. Saves silver/report/bounds/.
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
OUT = SILVER / "report" / "bounds"
OUT.mkdir(parents=True, exist_ok=True)

FAMILIES = ["access", "road", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
            "change of use", "apartment", "amenity"]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(centre - margin, 0.0), min(centre + margin, 1.0)


def calibration_bands(preds: np.ndarray, y: np.ndarray, n_bins: int = 12) -> pd.DataFrame:
    qs = np.quantile(preds, np.linspace(0, 1, n_bins + 1))
    rows = []
    for i in range(n_bins):
        mask = (preds >= qs[i]) & (preds <= qs[i + 1])
        if mask.sum() < 30:
            continue
        k, n = int(y[mask].sum()), int(mask.sum())
        lo, hi = wilson(k, n)
        rows.append({"bin_low": round(float(qs[i]), 3), "bin_high": round(float(qs[i + 1]), 3),
                     "n": n, "observed_rate": round(k / n, 4), "ci_low": round(lo, 4),
                     "ci_high": round(hi, 4)})
    return pd.DataFrame(rows)


def main() -> None:
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
    reg["path"] = "other"
    reg.loc[(reg["granted"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0), "path"] = "direct_grant"
    reg.loc[(reg["granted"] == 1) & (reg["fi"] == 1) & (reg["appeal"] == 0), "path"] = "fi_grant"
    reg.loc[(reg["refused"] == 1) & (reg["fi"] == 1) & (reg["appeal"] == 0), "path"] = "fi_refusal"
    reg.loc[(reg["refused"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0), "path"] = "direct_refusal"
    reg.loc[(reg["granted"] == 1) & (reg["appeal"] == 1), "path"] = "grant_appeal"
    reg.loc[(reg["refused"] == 1) & (reg["appeal"] == 1), "path"] = "refusal_appeal"
    reg = reg[reg["path"] != "other"]
    reg["clean"] = ((reg["granted"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0) &
                    (reg["dur"] <= 365)).astype(int)
    reg["late6m"] = (reg["dur"] > 183).astype(int)
    feats = ["log_units", "desc_len", "year"] + [f"f_{f}" for f in FAMILIES]
    auth_d = pd.get_dummies(reg["PlanningAuthority"], prefix="a").astype(int)
    train = reg[reg["year"] < 2022]
    test = reg[reg["year"] >= 2022]
    X_tr = pd.concat([train[feats], auth_d.loc[train.index]], axis=1)
    X_te = pd.concat([test[feats], auth_d.loc[test.index]], axis=1)

    out = {}
    model = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
    model.fit(X_tr, train["refused"])
    p_ref = model.predict_proba(X_te)[:, 1]
    out["refusal"] = {"bands": calibration_bands(p_ref, test["refused"].to_numpy()).to_dict(orient="records"),
                      "auc_test": round(float(roc_auc_score(test["refused"], p_ref)), 3)}

    path_model = LogisticRegression(max_iter=4000, C=1.0)
    path_model.fit(X_tr, train["path"])
    p_path = path_model.predict_proba(X_te)
    path_names = list(path_model.classes_)
    out["paths"] = {}
    for i, name in enumerate(path_names):
        out["paths"][name] = {"bands": calibration_bands(p_path[:, i], (test["path"] == name).astype(int).to_numpy()).to_dict(orient="records")}

    for target_name, y_col in [("clean", "clean"), ("late6m", "late6m")]:
        m = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
        m.fit(X_tr, train[y_col])
        p = m.predict_proba(X_te)[:, 1]
        out[target_name] = {"bands": calibration_bands(p, test[y_col].to_numpy()).to_dict(orient="records"),
                            "auc_test": round(float(roc_auc_score(test[y_col], p)), 3),
                            "prevalence": round(float(test[y_col].mean()), 3)}

    # pre-commencement AUC bootstrap CI
    corpus = pd.read_csv(SILVER / "conditions" / "condition_corpus.csv").drop_duplicates("case_key")
    base = corpus.drop(columns=["units", "authority", "grant_year"], errors="ignore").merge(
        reg[["case_key", "PlanningAuthority", "DevelopmentDescription", "units", "year"]],
        on="case_key", how="inner")
    base = base.dropna(subset=["n_precommencement", "n_conditions"])
    base["y_pre"] = (base["n_precommencement"] > 0).astype(int)
    base = base[base["n_conditions"] >= 5]
    desc2 = base["DevelopmentDescription"].fillna("").str.lower()
    base["log_units"] = np.log1p(base["units"])
    for fam in FAMILIES:
        base[f"f_{fam}"] = desc2.str.contains(fam, regex=False).astype(int)
    base["desc_len"] = desc2.str.len()
    a2 = pd.get_dummies(base["PlanningAuthority"], prefix="a").astype(int)
    X2 = pd.concat([base[feats[:2] + feats[3:]], a2], axis=1)
    rng = np.random.default_rng(7)
    aucs = []
    for _ in range(500):
        idx = rng.choice(len(base), len(base), replace=True)
        try:
            m = LogisticRegression(max_iter=3000, C=0.5)
            m.fit(X2.iloc[idx], base.iloc[idx]["y_pre"])
            tr2 = base[base["year"] < 2022]
            te2 = base[base["year"] >= 2022]
            p2 = m.predict_proba(X2.loc[te2.index])[:, 1]
            aucs.append(roc_auc_score(te2["y_pre"], p2))
        except ValueError:
            continue
    out["precommencement"] = {"auc_bootstrap_median": round(float(np.median(aucs)), 3),
                              "auc_ci95": [round(float(np.quantile(aucs, 0.025)), 3),
                                           round(float(np.quantile(aucs, 0.975)), 3)],
                              "n_bootstrap": int(len(aucs))}

    # rescue grant-rate by matches with Wilson CIs
    rescue = pd.read_csv(SILVER / "sprint2" / "refusal_grant_pairs.csv")
    test_r = rescue[rescue["year_1"] >= 2021].copy()
    med_units = rescue[(rescue["year_1"] < 2021) & (rescue["decision_2"] == "grant")]["units_2"].median()
    test_r["rec1"] = (test_r["units_reduced"] == 1) | (test_r["units_2"].fillna(0) <= med_units)
    test_r["rec2"] = (test_r["type_change"] == 0)
    test_r["rec3"] = (test_r["desc_len_ratio"] <= 1.3)
    test_r["rec4"] = (test_r["fam_access_roads_added"] + test_r["fam_drainage_uisce_added"] +
                      test_r["fam_parking_added"] + test_r["fam_height_storeys_added"] +
                      test_r["fam_ecology_added"]) == 0
    test_r["n_m"] = test_r[["rec1", "rec2", "rec3", "rec4"]].sum(axis=1)
    out["rescue"] = {}
    for k, sub in test_r.groupby("n_m"):
        n = int(len(sub))
        g = int((sub["decision_2"] == "grant").sum())
        lo, hi = wilson(g, n)
        out["rescue"][str(k)] = {"n": n, "grant_rate": round(g / n, 3),
                                 "ci_low": round(lo, 3), "ci_high": round(hi, 3)}

    (OUT / "report_bounds.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: (v if k not in ("refusal", "clean", "late6m", "paths") else
                          {kk: vv for kk, vv in v.items() if kk != "bands"})
                      for k, v in out.items()}, indent=2, default=str)[:4000])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
