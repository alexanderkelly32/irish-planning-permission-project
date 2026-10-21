"""Freeze the report runtime into a self-contained bundle.

1. Train once (register <= 2026-10-15) the runtime models the report uses:
   full GBMs (fi, appeal, appeal_tp, appeal_ap, clean, tail), band GBMs +
   calibration bands (refusal, fi, appeal, clean, tail, appeal_tp, appeal_ap),
   path logistic. Same hyperparameters/random_state as run_report_2026.py.
2. Freeze the condition predictors (fit on condition corpus).
3. Distill data tables: register_geo_min, refused_descriptions, supply_min,
   price_summary.
4. Copy the frozen v4 + context files into report_bundle/.

Output: 09_devrisk/data/report_bundle/
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
BUNDLE = SILVER / "report_bundle"
BUNDLE.mkdir(parents=True, exist_ok=True)
SUBMISSION = pd.Timestamp("2026-10-15")
FAMILIES = ["access", "road", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
            "change of use", "apartment", "amenity"]
ROOT = Path(__file__).resolve().parents[2]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(centre - margin, 0.0), min(centre + margin, 1.0)


def cal_bands(preds, y, n_bins=10):
    qs = np.quantile(preds, np.linspace(0, 1, n_bins + 1))
    out = []
    for i in range(n_bins):
        mask = (preds >= qs[i]) & (preds <= qs[i + 1])
        if mask.sum() < 30:
            continue
        k, n = int(y[mask].sum()), int(mask.sum())
        lo, hi = wilson(k, n)
        out.append({"lo": float(qs[i]), "hi": float(qs[i + 1]), "n": n,
                    "rate": k / n, "ci_lo": lo, "ci_hi": hi})
    return out


def main() -> None:
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = reg.drop_duplicates("case_key")
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["dec"] = pd.to_datetime(reg["DecisionDate"], utc=True, errors="coerce").dt.tz_localize(None)
    dec = reg["Decision"].fillna("").str.lower()
    reg["granted"] = dec.str.contains("grant|conditional|unconditional", regex=True).astype(int)
    reg["refused"] = dec.str.contains("refus").astype(int)
    reg = reg[((reg["granted"] == 1) | (reg["refused"] == 1))]
    reg["dur"] = (reg["dec"] - reg["recv"]).dt.days
    reg["fi"] = pd.notna(reg["FIRequestDate"]).astype(int)
    reg["appeal"] = pd.notna(reg["AppealSubmittedDate"]).astype(int)
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    reg["year"] = reg["recv"].dt.year
    desc = reg["DevelopmentDescription"].fillna("").str.lower()
    for fam in FAMILIES:
        reg[f"f_{fam}"] = desc.str.contains(fam, regex=False).astype(int)
    reg["desc_len"] = desc.str.len()
    reg["log_units"] = np.log1p(reg["units"])
    reg["clean"] = ((reg["granted"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0) &
                    (reg["dur"] <= 365)).astype(int)
    reg["late6m"] = (reg["dur"] > 183).astype(int)
    reg["y"] = reg["refused"].astype(int)
    reg["grant_appeal_flag"] = ((reg["granted"] == 1) & (reg["appeal"] == 1)).astype(int)
    reg["refusal_appeal_flag"] = ((reg["refused"] == 1) & (reg["appeal"] == 1)).astype(int)
    reg["path"] = "other"
    reg.loc[(reg["granted"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0), "path"] = "direct_grant"
    reg.loc[(reg["granted"] == 1) & (reg["fi"] == 1) & (reg["appeal"] == 0), "path"] = "fi_grant"
    reg.loc[(reg["refused"] == 1) & (reg["fi"] == 1) & (reg["appeal"] == 0), "path"] = "fi_refusal"
    reg.loc[(reg["refused"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0), "path"] = "direct_refusal"
    reg.loc[(reg["granted"] == 1) & (reg["appeal"] == 1), "path"] = "grant_appeal"
    reg.loc[(reg["refused"] == 1) & (reg["appeal"] == 1), "path"] = "refusal_appeal"
    reg = reg[(reg["path"] != "other") & (reg["year"] >= 2010)].reset_index(drop=True)

    feats = ["log_units", "desc_len", "year"] + [f"f_{f}" for f in FAMILIES]
    all_d = pd.get_dummies(reg["PlanningAuthority"], prefix="a").astype(int)
    train = reg[reg["recv"] < SUBMISSION]
    X_tr = pd.concat([train[feats], all_d.loc[train.index]], axis=1)
    band_train = reg[reg["year"] < 2023]
    band_cal = reg[(reg["year"].between(2023, 2025)) & (reg["recv"] < SUBMISSION)]
    X_bt = pd.concat([band_train[feats], all_d.loc[band_train.index]], axis=1)
    X_bc = pd.concat([band_cal[feats], all_d.loc[band_cal.index]], axis=1)

    full_models = {}
    col_map = {"appeal_tp": "grant_appeal_flag", "appeal_ap": "refusal_appeal_flag", "tail": "late6m"}
    for y_col in ("fi", "appeal", "grant_appeal_flag", "refusal_appeal_flag", "clean", "late6m"):
        m = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
        m.fit(X_tr, train[y_col])
        full_models[y_col] = m
    m_ref = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
    m_ref.fit(X_bt, band_train["y"])
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(m_ref.predict_proba(X_bc)[:, 1], band_cal["y"].to_numpy())
    full_models["refusal_raw"] = m_ref
    full_models["refusal_iso"] = iso
    pm = LogisticRegression(max_iter=4000, C=1.0)
    pm.fit(X_tr, train["path"])
    full_models["path"] = pm
    full_models["path_classes"] = list(pm.classes_)

    band_models, bands = {}, {}
    for y_col in ("y", "fi", "appeal", "clean", "late6m", "grant_appeal_flag", "refusal_appeal_flag"):
        m = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
        m.fit(X_bt, band_train[y_col])
        band_models[y_col] = m
        bands[y_col] = cal_bands(m.predict_proba(X_bc)[:, 1], band_cal[y_col].to_numpy())
    joblib.dump({"full_models": full_models, "band_models": band_models,
                 "feature_columns": list(X_tr.columns), "families": FAMILIES,
                 "cutoff": str(SUBMISSION)}, BUNDLE / "runtime_models.joblib")
    (BUNDLE / "bands.json").write_text(json.dumps(bands, indent=1), encoding="utf-8")

    # condition models frozen
    corpus = pd.read_csv(SILVER / "conditions" / "condition_corpus.csv").drop_duplicates("case_key")
    reg_desc = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "DevelopmentDescription"]).drop_duplicates("case_key")
    corpus = corpus.merge(reg_desc, on="case_key", how="left")
    corpus["y_pre"] = (corpus["n_precommencement"] > 0).astype(int)
    corpus["y_fin"] = (corpus["n_financial"] > 0).astype(int)
    inds = ["demolition", "protected structure", "brownfield", "infill", "creche",
            "retail", "extension", "change of use", "apartment"]
    cd = corpus["DevelopmentDescription"].fillna("").str.lower()
    ffeats = pd.DataFrame({"log_units": np.log1p(pd.to_numeric(corpus["units"], errors="coerce").fillna(1)),
                           "type_apartment": cd.str.contains("apartment|duplex", regex=True).astype(int),
                           "desc_len": cd.str.len()})
    for ind in inds:
        ffeats[f"desc_{ind.replace(' ', '_')}"] = cd.str.contains(ind, regex=False).astype(int)
    fauth = pd.get_dummies(corpus["authority"], prefix="a").astype(int)
    Xc = pd.concat([ffeats, fauth], axis=1)
    cond_models = {}
    for target, key in [("y_pre", "pre"), ("y_fin", "fin")]:
        mm = LogisticRegression(max_iter=3000, C=0.5)
        mm.fit(Xc, corpus[target])
        cond_models[key] = mm
    joblib.dump({"models": cond_models, "feature_columns": list(Xc.columns),
                 "prevalence_pre": {"rate": float(corpus["y_pre"].mean()), "n": int(len(corpus))},
                 "prevalence_fin": {"rate": float(corpus["y_fin"].mean()), "n": int(len(corpus))}},
                BUNDLE / "condition_models.joblib")

    # distill data tables
    reg_full = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg_full = reg_full.drop_duplicates("case_key")
    units_map = {}
    norm = lambda s: "".join(c for c in str(s).lower() if c.isalnum())
    for path in ("ground_source_units_corrected.csv", "holdout_units_extracted.csv", "ge10_units_reextracted.csv"):
        f = pd.read_csv(ROOT / "02_development" / "current" / path, low_memory=False)
        col = [c for c in f.columns if "unit" in c.lower()]
        if not col:
            continue
        for kk, v in zip(f["case_key"].astype(str), pd.to_numeric(f[col[0]], errors="coerce")):
            if pd.notna(v):
                units_map[norm(kk)] = v
    geo = reg_full[["case_key", "PlanningAuthority", "ITMEasting", "ITMNorthing",
                    "ReceivedDate", "Decision", "DevelopmentDescription",
                    "NumResidentialUnits"]].copy()
    geo["units"] = pd.to_numeric(geo["NumResidentialUnits"], errors="coerce")
    geo["units"] = geo["units"].fillna(geo["case_key"].map(lambda k: units_map.get(norm(k))))
    geo = geo.drop(columns=["NumResidentialUnits"])
    geo["desc_short"] = geo["DevelopmentDescription"].fillna("").str.slice(0, 160)
    geo = geo.drop(columns=["DevelopmentDescription"])
    geo.to_parquet(BUNDLE / "register_geo_min.parquet", index=False)

    refused = reg[(reg["y"] == 1) & (reg["recv"] < SUBMISSION)]
    refused = refused.dropna(subset=["DevelopmentDescription"])
    refused[["case_key", "PlanningAuthority", "DevelopmentDescription"]].to_parquet(
        BUNDLE / "refused_descriptions.parquet", index=False)

    supply = reg_full[["case_key", "PlanningAuthority", "ITMEasting", "ITMNorthing",
                       "NumResidentialUnits", "GrantDate"]].drop_duplicates("case_key").copy()
    supply["units"] = pd.to_numeric(supply["NumResidentialUnits"], errors="coerce")
    supply["units"] = supply["units"].fillna(supply["case_key"].map(lambda k: units_map.get(norm(k))))
    supply = supply.drop(columns=["NumResidentialUnits"])
    supply.to_parquet(BUNDLE / "supply_min.parquet", index=False)
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels[["case_key", "activation_days"]].to_parquet(BUNDLE / "activation_min.parquet", index=False)

    ppr = pd.read_parquet(settings.BRONZE_DIR / "ppr_bronze.parquet",
                          columns=["date_of_sale", "county", "price"])
    ppr["price"] = pd.to_numeric(ppr["price"].astype(str).str.replace("€", "", regex=False)
                                 .str.replace(",", "", regex=False), errors="coerce")
    ppr["dt"] = pd.to_datetime(ppr["date_of_sale"], utc=True, errors="coerce").dt.tz_localize(None)
    ppr = ppr.dropna(subset=["price"])
    ppr["ym"] = ppr["dt"].dt.to_period("M").astype(str)
    price_sum = (ppr.groupby(["county", "ym"])["price"].agg(median="median", q25=lambda s: s.quantile(0.25),
                                                            q75=lambda s: s.quantile(0.75), n="size").reset_index())
    price_sum.to_parquet(BUNDLE / "price_summary.parquet", index=False)
    shutil.copy2(settings.BRONZE_DIR / "ppr_bronze.parquet", BUNDLE / "ppr_bronze.parquet")

    # copy frozen v4 + context files
    v4 = ROOT / "05_policy" / "current" / "model_v4"
    for name in ("national_residential_v4_full.joblib", "manifest.json", "comparable_reference.joblib"):
        shutil.copy2(v4 / name, BUNDLE / name)
    for name in ("sa_reference.parquet", "flood_points.parquet", "plan_summary.parquet", "history_reference.parquet"):
        shutil.copy2(ROOT / "07_context" / "current" / name, BUNDLE / name)
    shutil.copy2(SILVER / "theme_exposure" / "theme_exposure_v6.joblib", BUNDLE / "theme_exposure_v6.joblib")
    shutil.copy2(SILVER / "report" / "zero_day" / "authority_type_baselines.csv", BUNDLE / "authority_type_baselines.csv")
    drafting = {"similar": {"n": 3706, "rate": 0.266, "ci_lo": 0.252, "ci_hi": 0.28},
                "trim": {"n": 3217, "rate": 0.073, "ci_lo": 0.064, "ci_hi": 0.082},
                "expand": {"n": 4179, "rate": 0.056, "ci_lo": 0.049, "ci_hi": 0.063},
                "rescue": {"0": 0.0, "1": 0.017, "2": 0.056, "3": 0.187, "4": 0.249},
                "abandonment": 0.41, "p_resub": 0.59,
                "units_effect": "OR 1.001, CI [-0.018, +0.021]"}
    (BUNDLE / "drafting_constants.json").write_text(json.dumps(drafting, indent=1), encoding="utf-8")

    total = sum(f.stat().st_size for f in BUNDLE.iterdir() if f.is_file())
    print("bundle files:")
    for f in sorted(BUNDLE.iterdir()):
        if f.is_file():
            print(f"  {f.stat().st_size/1e6:8.1f} MB  {f.name}")
    print(f"\nBUNDLE TOTAL: {total/1e6:.1f} MB")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
