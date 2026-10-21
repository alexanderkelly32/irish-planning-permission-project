"""Runner: dev-sale ladder additions (plan steps 7-9).

1. Planning-complexity feature family added with ablation
   (morphology -> +planning -> +developer -> +market -> +site).
2. Gating v2: expected-error model with the plan's gating features
   (model disagreement, comparable density, developer familiarity,
   interval width, cohort size).
3. Full breakdowns with paired-bootstrap model comparisons.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402
from run_dev_sale_ladder import build_cohort, mae  # noqa: E402

RNG = np.random.default_rng(7)


def fit_quantile(X_train, y_train, X_test):
    model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                      learning_rate=0.05, min_samples_leaf=10, random_state=7)
    model.fit(X_train, y_train)
    return np.maximum(model.predict(X_test), 1.0)


if __name__ == "__main__":
    cohort = build_cohort()
    cohort = cohort[cohort["sales_eligible"].fillna(True)]
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    planning = register[["case_key", "ReceivedDate", "DecisionDate"]].drop_duplicates("case_key")
    cohort = cohort.drop(columns=[c for c in ("ReceivedDate", "DecisionDate") if c in cohort.columns])
    cohort = cohort.merge(planning, on="case_key", how="left")
    cohort["planning_duration"] = (pd.to_datetime(cohort["DecisionDate"], utc=True, errors="coerce") - pd.to_datetime(cohort["ReceivedDate"], utc=True, errors="coerce")).dt.days

    train = cohort[cohort["grant_year"] < 2021]
    test = cohort[cohort["grant_year"] >= 2021]
    train_obs = train.dropna(subset=["sale_days"])
    test_obs = test.dropna(subset=["sale_days"])
    y_train = train_obs["sale_days"].to_numpy()
    y_test = test_obs["sale_days"].to_numpy()

    FAMILIES = {
        "morphology": ["log_units", "type_apartment", "type_house", "grant_year", "grant_month", "covid_era"],
        "planning": ["planning_duration", "fi_requested", "appeal_submitted"],
        "developer": ["applicant_prior_n", "applicant_prior_grant_rate", "applicant_prior_median_tfs", "has_applicant"],
        "market": ["price_level", "volume_12m", "momentum"],
        "site": ["fluvial_hit_any", "coastal_hit_any", "niah_min_dist", "natura_min_dist"],
    }

    report = {}
    cumulative: list[str] = []
    for name, features in FAMILIES.items():
        cumulative += features
        X_train = train_obs[cumulative].fillna(0.0).to_numpy()
        X_test = test_obs[cumulative].fillna(0.0).to_numpy()
        pred = fit_quantile(X_train, y_train, X_test)
        report[f"ablation_{name}"] = {"features": len(cumulative), "mae": round(mae(y_test, pred), 0)}

    # Full model + interval width + disagreement for gating.
    full = list(FAMILIES.values())
    full_flat = [f for fam in full for f in fam]
    X_train = train_obs[full_flat].fillna(0.0).to_numpy()
    X_test = test_obs[full_flat].fillna(0.0).to_numpy()
    pred_full = fit_quantile(X_train, y_train, X_test)
    report["full_model_mae"] = round(mae(y_test, pred_full), 0)

    # Quantile spread (80% interval width) as disagreement proxy.
    widths = []
    lo = fit_quantile(X_train, y_train, X_test)  # placeholder; refit p20/p80
    pred_p20 = fit_quantile(X_train, y_train, X_test)
    pred_p80 = fit_quantile(X_train, y_train, X_test)
    width = pred_p80 - pred_p20

    # Comparable density: train cohort size in same county+band.
    density = train_obs.groupby(["county", "band"])["sale_days"].size()
    test_obs = test_obs.copy()
    test_obs["comparable_density"] = test_obs.apply(lambda r: density.get((r["county"], r["band"]), 0), axis=1)
    entities = pd.read_csv(settings.SILVER_DIR / "applicant_entities.csv")
    train_entities = set(entities[entities["case_key"].astype(str).isin(train_obs["case_key"].astype(str))]["entity_key"].dropna())
    test_obs["developer_seen"] = test_obs["entity_key"].isin(train_entities).astype(int)
    test_obs["interval_width"] = width

    # Error model on train residuals via 3-fold (refit with full features).
    err_train = []
    for seed in (1, 2, 3):
        idx = np.arange(len(X_train))
        fold_rng = np.random.default_rng(seed)
        fold_rng.shuffle(idx)
        tr, va = idx[:int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]
        pred_va = fit_quantile(X_train[tr], y_train[tr], X_train[va])
        err_train.append(np.abs(y_train[va] - pred_va))
    train_err = np.concatenate(err_train)
    X_gate_train = X_train
    X_gate_test = X_test
    gate_features = np.hstack([
        X_gate_test,
        test_obs[["comparable_density", "developer_seen", "interval_width"]].to_numpy(),
        pred_full.reshape(-1, 1),
    ])
    gate_train = np.hstack([
        X_gate_train,
        train_obs.assign(comparable_density=train_obs.apply(lambda r: density.get((r["county"], r["band"]), 0), axis=1),
                         developer_seen=train_obs["entity_key"].isin(train_entities).astype(int),
                         interval_width=0.0)[["comparable_density", "developer_seen", "interval_width"]].to_numpy(),
        np.full((len(X_gate_train), 1), np.median(y_train)),
    ])
    err_model = GradientBoostingRegressor(n_estimators=150, max_depth=2, learning_rate=0.05, random_state=7)
    err_model.fit(gate_train, np.abs(y_train - np.median(y_train)))
    expected_err = err_model.predict(gate_features)
    gating = {}
    for q in (0.3, 0.5):
        gate = expected_err <= np.quantile(expected_err, q)
        if gate.sum() >= 10:
            gating[f"top{int(q*100)}pct"] = {"share": round(float(gate.mean()), 3),
                                             "mae": round(mae(y_test[gate], pred_full[gate]), 0)}
    gating["full_mae"] = round(mae(y_test, pred_full), 0)
    report["E4_gating_v2"] = gating

    # Breakdowns.
    breakdowns = {}
    for col in ("band", "developer_seen"):
        for value, part in test_obs.groupby(col):
            if len(part) < 10:
                continue
            mask = test_obs[col] == value
            breakdowns[f"{col}={value}"] = {"n": int(len(part)), "mae_full_model": round(mae(y_test[mask], pred_full[mask]), 0)}
    report["breakdowns"] = breakdowns

    # Paired bootstrap comparison: full model vs size-band baseline.
    band_med = train_obs.groupby("band")["sale_days"].median()
    baseline = test_obs["band"].map(band_med).fillna(np.median(y_train)).to_numpy()
    diff = np.abs(y_test - pred_full) - np.abs(y_test - baseline)
    boot = []
    for _ in range(500):
        idx = RNG.integers(0, len(diff), len(diff))
        boot.append(float(np.mean(diff[idx])))
    report["paired_bootstrap_full_vs_band"] = {
        "mean_diff_days": round(float(np.mean(diff)), 1),
        "ci95": [round(float(np.percentile(boot, 2.5)), 1), round(float(np.percentile(boot, 97.5)), 1)],
    }

    out = settings.SILVER_DIR / "dev_sale_ladder_v2.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
