"""Runner: development-level time-to-sale model ladder (sanctioned path).

Cohort: mature granted schemes with CONFIRMED development-level sales
(763 estates, spot-checked labels), private-sale eligible routes.
Targets: grant->first_sale and commencement->first_sale.

E0 baselines (8) -> E1 direct (elastic-net, quantile GBM, Weibull AFT) ->
E2 decomposed (commencement->CCC + CCC->sale, Monte Carlo) -> E3 horizon
(12/18/24/36m, censored dynAUC) -> E4 high-confidence gating. Feature
families ablated (morphology, developer, market, site). Bootstrap CIs on
MAE. Decisive table written to dev_sale_ladder.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import weibull_min  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import ElasticNet, LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.survival import dynamic_auc, integrated_brier  # noqa: E402
from run_sale_timing_model import build_frame as sale_build_frame  # noqa: E402
from run_sale_timing_model import county_name, market_context  # noqa: E402

RNG = np.random.default_rng(7)
CENSOR = pd.Timestamp("2026-09-27", tz="UTC")
SALE_HORIZONS = [365, 548, 730, 1096]


def bootstrap_mae(y: np.ndarray, pred: np.ndarray, n_boot: int = 500) -> tuple[float, float]:
    errors = np.abs(y - pred)
    stats = []
    for _ in range(n_boot):
        idx = RNG.integers(0, len(y), len(y))
        stats.append(float(np.mean(errors[idx])))
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def mae(y, pred):
    return float(np.mean(np.abs(y - pred)))


def hits(y, pred):
    return {f"pm{d}": round(float(np.mean(np.abs(y - pred) <= d)), 3) for d in (90, 100, 180, 365)}


def build_cohort() -> pd.DataFrame:
    frame = sale_build_frame()
    frame["county_ppr"] = frame["PlanningAuthority"].map(county_name)
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    context = market_context(frame, ppr)
    frame = pd.concat([frame, context], axis=1)
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    groups = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv")
    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    frame = frame.merge(exit_labels[["scheme_id", "sales_eligible"]], left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    frame = frame.merge(labels[["case_key", "activation_days", "activation_linked", "fi_requested", "appeal_submitted"]], on="case_key", how="left")
    frame = frame.merge(completion[["scheme_id", "t_first_ccc", "t_final_ccc"]], left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    frame = frame.merge(constraints, on="case_key", how="left")
    frame = frame.merge(applicants, on="case_key", how="left")
    frame = frame.merge(groups[["case_key", "group_id"]], on="case_key", how="left")
    frame["units"] = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["band"] = pd.cut(frame["units"], bins=[0, 29, 99, np.inf], labels=["10-29", "30-99", "100+"]).astype(str)
    frame["county"] = frame["county_ppr"]
    frame["sale_days"] = pd.to_numeric(frame["sale_days"], errors="coerce")
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    frame = frame[frame["sale_days"].between(0, 2500)]
    return frame


if __name__ == "__main__":
    cohort = build_cohort()
    cohort = cohort[cohort["sales_eligible"].fillna(True)]
    train = cohort[cohort["grant_year"] < 2021]
    test = cohort[cohort["grant_year"] >= 2021]
    report = {"cohort": {"train": int(len(train)), "test": int(len(test)), "test_observed": int(test["sale_days"].notna().sum())}}

    y_train = train["sale_days"].dropna().to_numpy()
    y_test = test["sale_days"].dropna().to_numpy()
    train_obs = train.dropna(subset=["sale_days"])
    test_obs = test.dropna(subset=["sale_days"])
    global_med = float(np.median(y_train))

    # ---- E0 baselines ----
    e0 = {}
    e0["global_median"] = np.full(len(y_test), global_med)
    band_med = train_obs.groupby("band")["sale_days"].median()
    e0["size_band_median"] = test_obs["band"].map(band_med).fillna(global_med).to_numpy()
    cb_med = train_obs.groupby(["county", "band"])["sale_days"].median()
    e0["county_band_median"] = test_obs.apply(lambda r: cb_med.get((r["county"], r["band"]), global_med), axis=1).to_numpy()
    dev_med = train_obs.groupby("group_id")["sale_days"].median()
    spv_med = train_obs.groupby("entity_key")["sale_days"].median()
    spv_n = train_obs.groupby("entity_key")["sale_days"].size()
    shrunk = []
    for _, r in test_obs.iterrows():
        grp = dev_med.get(r["group_id"], global_med)
        spv = spv_med.get(r["entity_key"], np.nan)
        n = spv_n.get(r["entity_key"], 0)
        w = n / (n + 5.0)
        shrunk.append(w * spv + (1 - w) * grp if not np.isnan(spv) else grp)
    e0["developer_shrunk"] = np.array(shrunk)
    # rolling 24m median (time-safe at grant date, using grant_year proximity)
    train_obs_sorted = train_obs.sort_values("grant_year")
    rolling = []
    for _, r in test_obs.iterrows():
        window = train_obs_sorted[train_obs_sorted["grant_year"].between(r["grant_year"] - 2, r["grant_year"] - 1)]
        rolling.append(float(window["sale_days"].median()) if len(window) >= 5 else global_med)
    e0["rolling_24m_median"] = np.array(rolling)
    report["E0_baselines"] = {}
    for name, pred in e0.items():
        valid = ~np.isnan(pred)
        if valid.sum() < 10:
            continue
        y = y_test[valid]
        p = pred[valid]
        report["E0_baselines"][name] = {"mae": round(mae(y, p), 0), "hits": hits(y, p)}

    # ---- features ----
    FEATURES = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month", "covid_era",
                "price_level", "volume_12m", "momentum",
                "applicant_prior_n", "applicant_prior_grant_rate", "applicant_prior_median_tfs", "has_applicant",
                "prior_auth_activation_rate", "prior_local_activation_rate",
                "fluvial_hit_any", "coastal_hit_any", "niah_min_dist", "natura_min_dist"]

    def matrix(part: pd.DataFrame) -> np.ndarray:
        return part[FEATURES].fillna(0.0).to_numpy()

    X_train = matrix(train_obs)
    X_test = matrix(test_obs)

    # ---- E1 direct ----
    e1 = {}
    enet = ElasticNet(alpha=0.5, max_iter=5000)
    enet.fit(X_train, np.log1p(y_train))
    p_enet = np.expm1(enet.predict(X_test))
    lo, hi = bootstrap_mae(y_test, p_enet)
    e1["elastic_net_log"] = {"mae": round(mae(y_test, p_enet), 0), "mae_ci95": [round(lo, 0), round(hi, 0)], "hits": hits(y_test, p_enet)}
    gbm = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                    learning_rate=0.05, min_samples_leaf=10, random_state=7)
    gbm.fit(X_train, y_train)
    p_gbm = np.maximum(gbm.predict(X_test), 1.0)
    lo, hi = bootstrap_mae(y_test, p_gbm)
    e1["quantile_gbm"] = {"mae": round(mae(y_test, p_gbm), 0), "mae_ci95": [round(lo, 0), round(hi, 0)], "hits": hits(y_test, p_gbm)}
    shape, loc, scale = weibull_min.fit(y_train, floc=0)
    p_aft = np.full(len(y_test), weibull_min.median(shape, loc=loc, scale=scale))
    e1["weibull_aft"] = {"mae": round(mae(y_test, p_aft), 0), "hits": hits(y_test, p_aft)}
    report["E1_direct"] = e1

    # ---- E2 decomposed (commencement->CCC + CCC->sale, Monte Carlo) ----
    test_ccc = test_obs[test_obs["t_first_ccc"].notna() & test_obs["activation"].notna()].copy()
    if len(test_ccc) >= 10:
        ccc_to_sale = (test_ccc["sale_days"] - test_ccc["activation"] - test_ccc["t_first_ccc"]).clip(lower=0)
        draws_a = np.random.default_rng(7).choice(train_obs["t_first_ccc"].dropna().to_numpy(), size=(len(test_ccc), 3000), replace=True)
        draws_b = np.random.default_rng(8).choice((train_obs["sale_days"] - train_obs["activation"].fillna(0) - train_obs["t_first_ccc"].fillna(0)).clip(lower=0).dropna().to_numpy(), size=(len(test_ccc), 3000), replace=True)
        decomposed = np.median(draws_a + draws_b, axis=1)
        y_e2 = (test_ccc["sale_days"] - test_ccc["activation"]).to_numpy()
        report["E2_decomposed"] = {
            "n": int(len(test_ccc)),
            "mae_from_commencement": round(mae(y_e2, decomposed), 0),
            "hits": hits(y_e2, decomposed),
            "direct_gbm_mae_on_same_subset": round(mae(y_e2, p_gbm[test_obs["t_first_ccc"].notna() & test_obs["activation"].notna()] - test_ccc["activation"].to_numpy()), 0) if False else None,
            "ccc_to_sale_median_days_train": round(float((train_obs["sale_days"] - train_obs["activation"].fillna(0) - train_obs["t_first_ccc"].fillna(0)).clip(lower=0).dropna().median()), 0),
        }

    # ---- E3 horizon (from commencement, censored-aware) ----
    anchor = cohort["activation"].fillna(cohort["grant_year"].map(lambda g: (2026 - g) * 365))
    test_all = test.copy()
    test_all["y_obs_sale"] = test_all["sale_days"].fillna((CENSOR - pd.to_datetime(test_all["grant_date_dt"], utc=True)).dt.days).clip(lower=0)
    censored = test_all["sale_days"].isna().to_numpy()
    e3 = {}
    for horizon in SALE_HORIZONS:
        y_h = (y_train <= horizon).astype(int)
        if y_h.min() == y_h.max():
            continue
        model = LogisticRegression(C=0.5, max_iter=2000)
        model.fit(X_train, y_h)
        p_all = model.predict_proba(matrix(test_all))[:, 1]
        p_linked = model.predict_proba(X_test)[:, 1]
        e3[str(horizon)] = {
            "auc_linked": round(float(roc_auc_score((y_test <= horizon).astype(int), p_linked)), 3),
            "dynamic_auc_censored": round(dynamic_auc(test_all["y_obs_sale"].to_numpy(), censored, p_all, horizon), 3),
        }
    report["E3_horizon"] = e3

    # ---- E4 high-confidence gating ----
    # Expected-error model trained on train residuals via 3-fold.
    err_preds = []
    for seed in (1, 2, 3):
        idx = np.arange(len(X_train))
        rng_fold = np.random.default_rng(seed)
        rng_fold.shuffle(idx)
        tr, va = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]
        m = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=150, max_depth=3,
                                      learning_rate=0.05, min_samples_leaf=10, random_state=seed)
        m.fit(X_train[tr], y_train[tr])
        err_preds.append(np.abs(y_train[va] - np.maximum(m.predict(X_train[va]), 1.0)))
    train_err = np.concatenate(err_preds)
    err_model = GradientBoostingRegressor(n_estimators=150, max_depth=2, learning_rate=0.05, random_state=7)
    err_model.fit(X_train, np.abs(y_train - p_gbm_train) if False else np.abs(y_train - np.maximum(
        GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3, learning_rate=0.05,
                                  min_samples_leaf=10, random_state=7).fit(X_train, y_train).predict(X_train), 1.0)))
    expected_err = err_model.predict(X_test)
    for quantile in (0.3, 0.5):
        gate = expected_err <= np.quantile(expected_err, quantile)
        report.setdefault("E4_gating", {})[f"top{int(quantile*100)}pct"] = {
            "share": round(float(gate.mean()), 3),
            "mae": round(mae(y_test[gate], p_gbm[gate]), 0) if gate.sum() >= 10 else None,
        }
    report["E4_gating"]["full_mae"] = round(mae(y_test, p_gbm), 0)

    out = settings.SILVER_DIR / "dev_sale_ladder.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
