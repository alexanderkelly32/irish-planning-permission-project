"""Runner: AlphaEarth real-data experiments (three tests, gates + CIs).

E1 pre-commencement: at grant, target commencement within 365/730 days;
features from the last completed annual observation BEFORE the grant year.
E2 monitoring: after commencement, target first CCC within 365 days /
stall indicator from post-commencement change.
E3 sale: AE site-change features added to the dev-level sale ladder;
requires >=10% MAE improvement + bootstrap CI.
"""
from __future__ import annotations

import json
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

RNG = np.random.default_rng(7)
BAND_COLS = [f"band{i}_mean" for i in range(64)]


def load_features() -> pd.DataFrame:
    frame = pd.read_csv(settings.RAW_DIR / "alphaearth" / "alphaearth_features.csv")
    frame = frame.drop_duplicates(subset=["development_id", "year"], keep="last")
    return frame


if __name__ == "__main__":
    features = load_features()
    AE_FEATS = [c for c in ("site_mean_norm", "contrast", "change_mean", "change_median", "change_p90", "heterogeneity") if c in features.columns]
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    register = register[["case_key", "GrantDate", "PlanningAuthority", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")

    base = labels.merge(register, on="case_key", how="inner")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base = base.merge(completion[["scheme_id", "t_first_ccc"]], left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    exit_cols = [c for c in ("time_to_first_sale_from_grant_days",) if c not in base.columns]
    base = base.merge(exit_labels[["scheme_id"] + exit_cols],
                      left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)

    report = {}

    # ---- E1 pre-commencement: last completed annual obs before grant ----
    e1 = base.merge(features, left_on=["case_key", "grant_year"], right_on=["development_id", "year"], how="left")
    e1 = e1.dropna(subset=AE_FEATS)
    e1["commence_365"] = (e1["activation"].notna() & (e1["activation"] <= 365)).astype(int)
    e1["commence_730"] = (e1["activation"].notna() & (e1["activation"] <= 730)).astype(int)
    train = e1[e1["grant_year"] < 2021]
    test = e1[e1["grant_year"] >= 2021]
    for target in ("commence_365", "commence_730"):
        y_tr = train[target].to_numpy()
        y_te = test[target].to_numpy()
        X_tr = train[AE_FEATS].fillna(0.0).to_numpy()
        X_te = test[AE_FEATS].fillna(0.0).to_numpy()
        model = LogisticRegression(C=0.5, max_iter=2000)
        model.fit(X_tr, y_tr)
        p = model.predict_proba(X_te)[:, 1]
        base_rate = np.full(len(y_te), y_tr.mean())
        report[f"E1_{target}"] = {
            "n_train": int(len(train)), "n_test": int(len(test)),
            "prevalence_test": round(float(y_te.mean()), 3),
            "auc": round(float(roc_auc_score(y_te, p)), 3) if len(np.unique(y_te)) == 2 else None,
            "brier_ae": round(float(np.mean((y_te - p) ** 2)), 4),
            "brier_base": round(float(np.mean((y_te - base_rate) ** 2)), 4),
        }

    # ---- E2 monitoring: after commencement, CCC within 365 ----
    e2 = base[base["activation"].notna()].copy()
    e2 = e2.merge(features, left_on=["case_key", "grant_year"], right_on=["development_id", "year"], how="left")
    e2 = e2.dropna(subset=AE_FEATS)
    e2["ccc_after_commencement"] = (e2["t_first_ccc"] - e2["activation"]).clip(lower=0)
    e2["ccc_365"] = (e2["ccc_after_commencement"] <= 365).astype(int)
    train2 = e2[e2["grant_year"] < 2021]
    test2 = e2[e2["grant_year"] >= 2021]
    y_tr2 = train2["ccc_365"].to_numpy()
    y_te2 = test2["ccc_365"].to_numpy()
    X_tr2 = train2[AE_FEATS].fillna(0.0).to_numpy()
    X_te2 = test2[AE_FEATS].fillna(0.0).to_numpy()
    model2 = LogisticRegression(C=0.5, max_iter=2000)
    model2.fit(X_tr2, y_tr2)
    p2 = model2.predict_proba(X_te2)[:, 1]
    report["E2_ccc_within_365"] = {
        "n_train": int(len(train2)), "n_test": int(len(test2)),
        "auc": round(float(roc_auc_score(y_te2, p2)), 3) if len(np.unique(y_te2)) == 2 else None,
        "brier_ae": round(float(np.mean((y_te2 - p2) ** 2)), 4),
        "brier_base": round(float(np.mean((y_te2 - np.full(len(y_te2), y_tr2.mean())) ** 2)), 4),
    }

    # ---- E3 sale: AE features added to the dev ladder ----
    e3 = base[pd.to_numeric(base["sales_linked"], errors="coerce").gt(0)].copy()
    e3 = e3.dropna(subset=["time_to_first_sale_from_grant_days"])
    e3 = e3.merge(features, left_on=["case_key", "grant_year"], right_on=["development_id", "year"], how="left")
    e3 = e3.dropna(subset=AE_FEATS)
    units = pd.to_numeric(e3["NumResidentialUnits"], errors="coerce")
    e3["log_units"] = np.log1p(units.fillna(0))
    feats = ["log_units"] + AE_FEATS
    train3 = e3[e3["grant_year"] < 2021]
    test3 = e3[e3["grant_year"] >= 2021]
    y_tr3 = train3["time_to_first_sale_from_grant_days"].to_numpy()
    y_te3 = test3["time_to_first_sale_from_grant_days"].to_numpy()
    X_tr3 = train3[feats].fillna(0.0).to_numpy()
    X_te3 = test3[feats].fillna(0.0).to_numpy()
    gbm = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=200, max_depth=3,
                                    learning_rate=0.05, min_samples_leaf=10, random_state=7)
    gbm.fit(X_tr3, y_tr3)
    p3 = np.maximum(gbm.predict(X_te3), 1.0)
    baseline = np.full(len(y_te3), np.median(y_tr3))
    ae_mae = float(np.mean(np.abs(y_te3 - p3)))
    base_mae = float(np.mean(np.abs(y_te3 - baseline)))
    boot = []
    for _ in range(400):
        idx = RNG.integers(0, len(y_te3), len(y_te3))
        boot.append(float(np.mean(np.abs(y_te3[idx] - p3[idx]))))
    report["E3_sale"] = {
        "n_train": int(len(train3)), "n_test": int(len(test3)),
        "base_mae": round(base_mae, 0), "ae_mae": round(ae_mae, 0),
        "improvement_pct": round((1 - ae_mae / base_mae) * 100, 1),
        "ae_mae_ci95": [round(float(np.percentile(boot, 2.5)), 0), round(float(np.percentile(boot, 97.5)), 0)],
        "gate_10pct": bool(ae_mae <= base_mae * 0.9),
    }

    out = settings.SILVER_DIR / "alphaearth_experiments_real.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
