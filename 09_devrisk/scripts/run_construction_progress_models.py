"""Progress-based completion states: baselines, ablation, ML, gates.

Primary target: remaining time to final CCC. Scheme-grouped temporal split
(commencement < 2022 train, >= 2022 test). Baselines before ML; the key
ablation is elapsed-time only vs elapsed + % certified (+ descriptors).
Pre-registered gates: a progress state is product-useful if 80% width
falls >=20% vs preceding state, or MAE improves >=10% over best elapsed-
only baseline, or horizon discrimination improves. ML retained only if
>=10% MAE over best simple baseline on temporal holdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import QuantileRegressor
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "construction_progress"


def mae(y, p):
    return float(np.mean(np.abs(y - p)))


def med_ae(y, p):
    return float(np.median(np.abs(y - p)))


def hit(y, p, tol):
    return float((np.abs(y - p) <= tol).mean() * 100)


def width(y, pct=0.8):
    return float(np.quantile(y, 0.5 + pct / 2) - np.quantile(y, 0.5 - pct / 2))


def main() -> None:
    snaps = pd.read_csv(OUT / "construction_progress_snapshots.csv")
    snaps = snaps.dropna(subset=["target_final_ccc_days"])
    snaps = snaps[(snaps["target_final_ccc_days"] >= 0) & (snaps["target_final_ccc_days"] <= 4000)]
    snaps["comm_year"] = pd.to_datetime(snaps["snapshot_dt"]).dt.year

    events = pd.read_csv(OUT / "construction_progress_events.csv")
    comm_year = events.groupby("case_key")["comm_dt"].min().map(
        lambda d: pd.to_datetime(d).year)
    snaps["comm_year"] = snaps["case_key"].map(comm_year)
    train = snaps[snaps["comm_year"] < 2022].copy()
    test = snaps[snaps["comm_year"] >= 2022].copy()
    report = {"n_train": int(len(train)), "n_test": int(len(test)),
              "n_schemes_train": int(train["case_key"].nunique()),
              "n_schemes_test": int(test["case_key"].nunique())}

    y_tr = train["target_final_ccc_days"].to_numpy()
    y_te = test["target_final_ccc_days"].to_numpy()

    global_med = float(np.median(y_tr))
    def band(v):
        if v <= 0:
            return "0"
        if v < 25:
            return "0-25"
        if v < 50:
            return "25-50"
        if v < 75:
            return "50-75"
        if v < 100:
            return "75-100"
        return "100+"
    train["band"] = train["cum_pct"].map(band)
    test["band"] = test["cum_pct"].map(band)
    band_med = train.groupby("band")["target_final_ccc_days"].median().to_dict()
    train["elapsed_band"] = pd.cut(train["elapsed_days"], [0, 90, 180, 365, 730, 5000], labels=["0-90", "90-180", "180-365", "365-730", "730+"])
    test["elapsed_band"] = pd.cut(test["elapsed_days"], [0, 90, 180, 365, 730, 5000], labels=["0-90", "90-180", "180-365", "365-730", "730+"])
    elapsed_med = train.groupby("elapsed_band")["target_final_ccc_days"].median().to_dict()

    baselines = {}
    p = np.full_like(y_te, global_med)
    baselines["global_median"] = {"mae": round(mae(y_te, p), 1),
                                  "med_ae": round(med_ae(y_te, p), 1),
                                  "hit_180": round(hit(y_te, p, 180), 1),
                                  "hit_365": round(hit(y_te, p, 365), 1)}
    p = test["band"].map(band_med).fillna(global_med).to_numpy()
    baselines["progress_band_median"] = {"mae": round(mae(y_te, p), 1),
                                         "med_ae": round(med_ae(y_te, p), 1),
                                         "hit_180": round(hit(y_te, p, 180), 1),
                                         "hit_365": round(hit(y_te, p, 365), 1)}
    p = test["elapsed_band"].astype(str).map(elapsed_med).fillna(global_med).to_numpy()
    baselines["elapsed_band_median"] = {"mae": round(mae(y_te, p), 1),
                                        "med_ae": round(med_ae(y_te, p), 1),
                                        "hit_180": round(hit(y_te, p, 180), 1),
                                        "hit_365": round(hit(y_te, p, 365), 1)}

    feats = {
        "elapsed_only": ["elapsed_days"],
        "elapsed_progress": ["elapsed_days", "cum_pct", "n_ccc_to_date",
                             "days_since_last_ccc", "velocity_90d", "units_remaining"],
        "elapsed_progress_descriptors": ["elapsed_days", "cum_pct", "n_ccc_to_date",
                                         "days_since_last_ccc", "velocity_90d",
                                         "units_remaining", "scheme_units", "type_apartment"],
    }
    models = {}
    for name, cols in feats.items():
        X_tr = train[cols].fillna(0.0)
        X_te = test[cols].fillna(0.0)
        gbm = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=300,
                                        max_depth=3, learning_rate=0.05,
                                        min_samples_leaf=20, random_state=7)
        gbm.fit(X_tr, y_tr)
        p = np.maximum(gbm.predict(X_te), 0.0)
        models[name] = {"mae": round(mae(y_te, p), 1), "med_ae": round(med_ae(y_te, p), 1),
                        "hit_180": round(hit(y_te, p, 180), 1),
                        "hit_365": round(hit(y_te, p, 365), 1)}
        if name == "elapsed_progress":
            models[name]["mae_gain_vs_elapsed_only"] = round(
                (1 - mae(y_te, p) / (models["elapsed_only"]["mae"] or 1)) * 100, 1)

    qr = QuantileRegressor(quantile=0.5, alpha=1.0, solver="highs")
    X_tr = train[feats["elapsed_progress"]].fillna(0.0)
    X_te = test[feats["elapsed_progress"]].fillna(0.0)
    qr.fit(X_tr, y_tr)
    p = np.maximum(qr.predict(X_te), 0.0)
    models["quantile_reg_progress"] = {"mae": round(mae(y_te, p), 1),
                                       "med_ae": round(med_ae(y_te, p), 1),
                                       "hit_180": round(hit(y_te, p, 180), 1),
                                       "hit_365": round(hit(y_te, p, 365), 1)}

    try:
        X_te2 = test[feats["elapsed_progress"]].fillna(0.0)
        gbm2 = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=300,
                                         max_depth=3, learning_rate=0.05,
                                         min_samples_leaf=20, random_state=7)
        gbm2.fit(train[feats["elapsed_progress"]].fillna(0.0), y_tr)
        p12 = gbm2.predict(X_te2)
        within_hat = (p12 <= 365).astype(int)
        auc12 = roc_auc_score(test["within_12m_final"], p12 * -1)
        report["horizon_auc_12m"] = {
            "progress_model_score": round(float(auc12), 3),
            "n_pos": int(test["within_12m_final"].sum()),
            "n_neg": int(len(test) - test["within_12m_final"].sum()),
        }
    except ValueError:
        report["horizon_auc_12m"] = "degenerate"

    uncertainty = {}
    state_order = ["commenced", "first_ccc", "pct25", "pct50", "pct75"]
    prev_width = None
    for state in state_order:
        sub = snaps[snaps["state"] == state]
        if len(sub) < 20:
            continue
        w = width(sub["target_final_ccc_days"], 0.8)
        entry = {"n": int(len(sub)), "n_schemes": int(sub["case_key"].nunique()),
                 "median_remaining": round(float(sub["target_final_ccc_days"].median()), 1),
                 "width_80": round(w, 1)}
        entry["reduction_vs_commenced"] = round(
            (1 - w / uncertainty.get("commenced", {}).get("width_80", w)) * 100, 1) if state != "commenced" else None
        entry["reduction_vs_previous"] = round((1 - w / prev_width) * 100, 1) if prev_width else None
        uncertainty[state] = entry
        prev_width = w

    sur = {}
    for state in ["pct25", "pct50", "pct75"]:
        sub = snaps[snaps["state"] == state].copy()
        if len(sub) < 40:
            continue
        sub["reach_speed"] = pd.qcut(sub["elapsed_days"], 2, labels=["fast", "slow"])
        entry = {"n": int(len(sub))}
        for g, gsub in sub.groupby("reach_speed"):
            entry[f"reached_{g}_median_remaining"] = round(float(gsub["target_final_ccc_days"].median()), 1)
            entry[f"reached_{g}_within_12m"] = round(float(gsub["within_12m_final"].mean() * 100), 1)
        sur[state] = entry

    out = {"baselines": baselines, "models": models, "uncertainty_by_state": uncertainty,
           "survivorship": sur, "sample": report}
    (OUT / "construction_progress_models.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
