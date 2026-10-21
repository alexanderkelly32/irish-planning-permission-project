"""Discrete-time grant->commencement hazard: family ablations + benchmarks.

Monthly logistic hazard h(m); P(within k) = 1 - prod(1-h). Families:
- cal: calendar only (grant_year + authority + calendar month)
- econ: cal + RPPI level/3m momentum + WPI + PPR new price/volume/momentum
- dev: cal + developer workload
- pipe: cal + local pipeline
Temporal split: train mk <= 2022-12, test mk >= 2023-01.
Comparators: frozen smooth-CDF benchmark (scheme-level P(<=365d) from
commencement_smooth_test_predictions.csv), calendar-only hazard.
Analysis only - no production model changes.
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
SPLIT_MK = (2022 + 1) * 12  # months >= 2023-01


def auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    try:
        return float(roc_auc_score(y, p))
    except ValueError:
        return float("nan")


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((y - p) ** 2))


def chained(pred_h: np.ndarray, k: int) -> np.ndarray:
    return 1.0 - np.prod(1.0 - pred_h[:, :k], axis=1)


def main() -> None:
    panel = pd.read_parquet(SILVER / "econ_hazard_panel.parquet")
    panel["has_econ"] = panel["rppi_nat"].notna()
    cal_feats = ["grant_year", "calendar_month", "m"]
    econ_feats = ["rppi_nat", "rppi_3m_mom"] + [c for c in panel.columns if c.startswith("wpi_")] + \
                 ["ppr_new_median", "ppr_new_volume", "ppr_new_6m_mom"]
    dev_feats = ["dev_granted_uncommenced", "dev_under_construction"]
    pipe_feats = ["pipe_granted_uncommenced", "pipe_under_construction"]
    all_num = ["months_remaining", "type_apartment", "units"]

    authority_dummies = pd.get_dummies(panel["authority"], prefix="auth").astype(int)

    train_mask = panel["mk"] < SPLIT_MK
    test_mask = panel["mk"] >= SPLIT_MK
    families = {"cal": cal_feats, "econ": cal_feats + econ_feats,
                "dev": cal_feats + dev_feats, "pipe": cal_feats + pipe_feats}
    models = {}
    horizon_preds = {}
    for name, feats in families.items():
        X_tr = pd.concat([panel.loc[train_mask, feats + all_num].fillna(-1.0),
                          authority_dummies.loc[train_mask]], axis=1)
        X_te = pd.concat([panel.loc[test_mask, feats + all_num].fillna(-1.0),
                          authority_dummies.loc[test_mask]], axis=1)
        y_tr = panel.loc[train_mask, "commence_within_1"].astype(int)
        model = LogisticRegression(max_iter=2000, C=1.0)
        model.fit(X_tr, y_tr)
        h = model.predict_proba(X_te)[:, 1]
        models[name] = model
        horizon_preds[name] = {"h1": h}
        for k in (3, 6, 12):
            hh = model.predict_proba(X_te)[:, 1]
            horizon_preds[name][f"h{k}"] = chained(hh.reshape(-1, 1) ** 0 + hh.reshape(-1, 1) * 0 + hh.reshape(-1, 1), k) if False else None
        horizon_preds[name]["p1"] = h
        horizon_preds[name]["p3"] = 1 - (1 - h) ** 3
        horizon_preds[name]["p6"] = 1 - (1 - h) ** 6
        horizon_preds[name]["p12"] = 1 - (1 - h) ** 12

    test = panel[test_mask].copy()
    obs = {}
    for k in (1, 3, 6, 12):
        mask = test["snap_gap_months"] >= k
        obs[k] = (test.loc[mask, f"commence_within_{k}"].astype(int).to_numpy(),
                  mask.to_numpy())

    report = {"families": {}}
    for name in families:
        entry = {}
        for k in (1, 3, 6, 12):
            y, mask = obs[k]
            p = horizon_preds[name][f"p{k}"][mask]
            entry[f"h{k}"] = {"n": int(len(y)), "auc": round(auc(y, p), 3),
                              "brier": round(brier(y, p), 4)}
        report["families"][name] = entry

    bench = pd.read_csv(SILVER / "commencement_smooth_test_predictions.csv")
    qcols = [c for c in bench.columns if c.startswith("q")]
    bench["p365"] = np.mean(
        [(bench[q] / 365.0).clip(0, 1) for q in qcols], axis=0)
    test_first = test.sort_values("m").groupby("case_key").first().reset_index()
    y12 = (test_first["commence_within_12"].astype(int).to_numpy(),
           test_first["snap_gap_months"] >= 12)
    b = test_first.merge(bench[["case_key", "p365"]], on="case_key", how="inner")
    b_mask = b["snap_gap_months"] >= 12
    if len(b) >= 20:
        report["benchmark_smooth_cdf"] = {
            "n": int(b_mask.sum()),
            "auc_12m": round(auc(b.loc[b_mask, "commence_within_12"].astype(int).to_numpy(),
                                  b.loc[b_mask, "p365"].to_numpy()), 3),
            "brier_12m": round(brier(b.loc[b_mask, "commence_within_12"].astype(int).to_numpy(),
                                      b.loc[b_mask, "p365"].to_numpy()), 4),
        }
    report["n_schemes_test"] = int(test["case_key"].nunique())
    report["n_rows_test"] = int(len(test))
    report["finance_family"] = "unavailable - ECB/CentralBank DNS unreachable from this machine (pending)"

    out = SILVER / "econ_hazard_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
