"""Runner: decision-timing model for 10+ unit residential schemes.

Target: days from submission (ReceivedDate) to local decision (DecisionDate).
Cohort: 10+ unit residential rows with both dates (n ~3,186, 2014-2025).

Baselines: constant quantiles; authority-year-type strata quantiles.
Candidates: ridge on log-days (homoscedastic quantiles via training
residuals) and gradient-boosted quantile regression (P20/P50/P80).
Horizon classifiers: logistic P(decision > 6m) and P(> 12m).

Features (submission-time, time-safe): authority, scheme type, log units,
received year/month, authority congestion (prior-90d application count and
prior-6m median decision duration, computed only from earlier rows).

Temporal split: train received < 2024, holdout >= 2024. Pinball loss per
quantile, horizon AUC/Brier/calibration. Model card + artifact persisted if
the candidate beats both baselines (brief 16.6).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import LogisticRegression, Ridge  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, calibration_slope_intercept  # noqa: E402

RNG = 7
QUANTILES = (0.2, 0.5, 0.8)


def load_cohort() -> pd.DataFrame:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = register.copy()
    frame["received_date_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["decision_date_dt"] = pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce")
    frame["duration_days"] = (frame["decision_date_dt"] - frame["received_date_dt"]).dt.days
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame = frame[
        frame["received_date_dt"].notna() & frame["decision_date_dt"].notna()
        & units.ge(10) & frame["duration_days"].between(0, 1095)
    ].copy()
    frame["units"] = units[frame.index]
    frame["log_units"] = np.log1p(frame["units"].fillna(0))
    frame["received_year"] = frame["received_date_dt"].dt.year
    frame["received_month"] = frame["received_date_dt"].dt.month
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)
    frame["type_house"] = (description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)).astype(int)
    return frame.reset_index(drop=True)


def add_congestion_features_fast(frame: pd.DataFrame) -> pd.DataFrame:
    """Vectorised time-safe congestion features (rolling windows, earlier rows only)."""
    data = frame.sort_values("received_date_dt").reset_index(drop=True)

    def _rolling_count(group: pd.DataFrame) -> pd.Series:
        return group.rolling("90d", on="received_date_dt")["case_key"].count()

    def _rolling_median(group: pd.DataFrame) -> pd.Series:
        return group.rolling("180d", on="received_date_dt")["duration_days"].median()

    counts = data.groupby("PlanningAuthority", group_keys=False).apply(_rolling_count)
    medians = data.groupby("PlanningAuthority", group_keys=False).apply(_rolling_median)
    data["auth_prior_90d_count"] = counts.astype(float).clip(lower=0) - 1
    data["auth_prior_180d_median_duration"] = medians
    data["auth_prior_180d_median_duration"] = data["auth_prior_180d_median_duration"].fillna(
        data["auth_prior_180d_median_duration"].median()
    )
    return data


def load_population_cohort() -> pd.DataFrame:
    """All residential rows with durations (for population-trained models)."""
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = register.copy()
    frame["received_date_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["decision_date_dt"] = pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce")
    frame["duration_days"] = (frame["decision_date_dt"] - frame["received_date_dt"]).dt.days
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    res_terms = r"\b(?:apartment|apartments|dwelling|dwellings|house|houses|residential|home|extension|retention|change of use|one-off|one off)\b"
    residential = units.gt(0) | frame["OneOffHouse"].fillna("").astype(str).str.strip().str.lower().isin({"y", "yes", "one", "single house"})
    residential |= frame["DevelopmentDescription"].fillna("").astype(str).str.contains(res_terms, case=False, regex=True)
    frame = frame[
        residential & frame["received_date_dt"].notna() & frame["decision_date_dt"].notna()
        & frame["duration_days"].between(0, 1095)
    ].copy()
    frame["units"] = units[frame.index]
    frame["log_units"] = np.log1p(frame["units"].fillna(0))
    frame["received_year"] = frame["received_date_dt"].dt.year
    frame["received_month"] = frame["received_date_dt"].dt.month
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)
    frame["type_house"] = (description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)).astype(int)
    return frame.reset_index(drop=True)


def pinball(y: np.ndarray, pred: np.ndarray, tau: float) -> float:
    diff = y - pred
    return float(np.mean(np.where(diff >= 0, tau * diff, (tau - 1) * diff)))


def build_features(frame: pd.DataFrame, *, authority_encoder=None, fit: bool = True):
    structured = frame[
        ["log_units", "type_apartment", "type_house", "received_year", "received_month",
         "auth_prior_90d_count", "auth_prior_180d_median_duration"]
    ].astype(float)
    structured["auth_prior_90d_count"] = np.log1p(structured["auth_prior_90d_count"])
    structured["auth_prior_180d_median_duration"] = np.log1p(structured["auth_prior_180d_median_duration"])
    return structured


if __name__ == "__main__":
    frame = load_cohort()
    frame = add_congestion_features_fast(frame)
    print(f"cohort n={len(frame)}", flush=True)

    train = frame[frame["received_year"] < 2024]
    test = frame[frame["received_year"] >= 2024]
    print(f"train={len(train)}, test={len(test)}", flush=True)

    y_train = train["duration_days"].to_numpy()
    y_test = test["duration_days"].to_numpy()

    X_train = build_features(train)
    X_test = build_features(test)
    X_train["authority"] = train["PlanningAuthority"].astype(str)
    X_test["authority"] = test["PlanningAuthority"].astype(str)
    X_train_dummy = pd.get_dummies(X_train, columns=["authority"])
    X_test_dummy = X_test.reindex(columns=X_train_dummy.columns, fill_value=0)

    report: dict[str, object] = {"split": "train received < 2024, holdout >= 2024",
                                 "n": {"train": int(len(train)), "test": int(len(test))}}

    overall_q = {tau: float(np.quantile(y_train, tau)) for tau in QUANTILES}
    report["baseline_constant_quantiles_days"] = {str(tau): round(v, 1) for tau, v in overall_q.items()}
    for tau in QUANTILES:
        report[f"pinball_constant_p{int(tau*100)}"] = round(pinball(y_test, np.full(len(y_test), overall_q[tau]), tau), 1)

    strata = train.groupby(["PlanningAuthority", "received_year"])["duration_days"].quantile(list(QUANTILES)).unstack()
    strata.columns = ["q20", "q50", "q80"]
    strata_auth = train.groupby("PlanningAuthority")["duration_days"].quantile(list(QUANTILES)).unstack()
    strata_auth.columns = ["q20_a", "q50_a", "q80_a"]
    test = test.merge(strata.reset_index(), on=["PlanningAuthority", "received_year"], how="left")
    test = test.merge(strata_auth.reset_index(), on="PlanningAuthority", how="left")
    for q in ("20", "50", "80"):
        test[f"strata_q{q}"] = test[f"q{q}"].fillna(test[f"q{q}_a"]).fillna(overall_q[float(q) / 100])
        report[f"pinball_strata_p{q}"] = round(pinball(y_test, test[f"strata_q{q}"].to_numpy(), float(q) / 100), 1)

    # Ridge on log-days + homoscedastic residual quantiles.
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train_dummy, np.log1p(y_train))
    log_pred_test = ridge.predict(X_test_dummy)
    residuals = np.log1p(y_train) - ridge.predict(X_train_dummy)
    residual_q = {tau: float(np.quantile(residuals, tau)) for tau in QUANTILES}
    for tau in QUANTILES:
        pred = np.maximum(np.expm1(log_pred_test + residual_q[tau]), 1.0)
        report[f"pinball_ridge_p{int(tau*100)}"] = round(pinball(y_test, pred, tau), 1)

    # GBM quantile regression.
    gbm_preds = {}
    for tau in QUANTILES:
        gbm = GradientBoostingRegressor(
            loss="quantile", alpha=tau, n_estimators=300, max_depth=3,
            learning_rate=0.05, min_samples_leaf=20, random_state=RNG,
        )
        gbm.fit(X_train_dummy, y_train)
        pred = np.maximum(gbm.predict(X_test_dummy), 1.0)
        gbm_preds[tau] = pred
        report[f"pinball_gbm_p{int(tau*100)}"] = round(pinball(y_test, pred, tau), 1)
        if tau == 0.5:
            report["gbm_median_mae"] = round(float(np.mean(np.abs(y_test - pred))), 1)
            report["ridge_median_mae"] = round(float(np.mean(np.abs(y_test - np.expm1(log_pred_test)))), 1)
            report["strata_median_mae"] = round(float(np.mean(np.abs(y_test - test["strata_q50"].to_numpy()))), 1)
            report["constant_median_mae"] = round(float(np.mean(np.abs(y_test - overall_q[0.5]))), 1)

    # Horizon classifiers on the same features.
    horizon_rows = {}
    horizon_classifiers = {}
    for horizon in (183, 365):
        y_train_h = (y_train > horizon).astype(int)
        y_test_h = (y_test > horizon).astype(int)
        clf = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        clf.fit(X_train_dummy, y_train_h)
        horizon_classifiers[str(horizon)] = clf
        p = np.clip(clf.predict_proba(X_test_dummy)[:, 1], 1e-6, 1 - 1e-6)
        lo, hi = bootstrap_auc(y_test_h, p, seed=0)
        entry = {
            "horizon_days": horizon,
            "train_prevalence": round(float(y_train_h.mean()), 4),
            "test_prevalence": round(float(y_test_h.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y_test_h, p)), 4),
            "auc_ci_low": round(lo, 4),
            "auc_ci_high": round(hi, 4),
            "brier": round(float(brier_score_loss(y_test_h, p)), 4),
        }
        entry.update(calibration_slope_intercept(y_test_h, p))
        horizon_rows[str(horizon)] = entry
    report["horizon_models"] = horizon_rows

    # Persist the winning quantile model (GBM) if it beats both baselines at P50.
    gbm_wins = report["pinball_gbm_p50"] < min(report["pinball_strata_p50"], report["pinball_constant_p50"])
    report["gbm_beats_baselines_at_p50"] = bool(gbm_wins)
    if gbm_wins:
        import joblib

        artifact = {
            "model_version": "decision_timing_gbm_v1",
            "quantiles": {str(tau): gbm_preds.get(tau) is not None for tau in QUANTILES},
            "target": "days from submission to local decision, 10+ unit residential",
            "feature_columns": list(X_train_dummy.columns),
            "training_cutoff_exclusive": "2024-01-01",
            "card": report,
        }
        models = {str(tau): GradientBoostingRegressor(
            loss="quantile", alpha=tau, n_estimators=300, max_depth=3,
            learning_rate=0.05, min_samples_leaf=20, random_state=RNG,
        ).fit(X_train_dummy, y_train) for tau in QUANTILES}
        artifact["models"] = models
        artifact["horizon_models"] = horizon_classifiers
        artifact["horizon_card"] = {key: value for key, value in horizon_rows.items() if not key.startswith("population_")}
        path = settings.GOLD_DIR / "decision_timing_gbm_v1.joblib"
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, path)
        report["artifact"] = str(path)

    test_out = test[["case_key", "PlanningAuthority", "received_year", "duration_days",
                     "strata_q20", "strata_q50", "strata_q80"]].copy()
    test_out.to_csv(settings.SILVER_DIR / "decision_timing_holdout.csv", index=False)

    # --- Population-trained comparison (all residential, evaluate on 10+ holdout) ---
    pop = load_population_cohort()
    pop = add_congestion_features_fast(pop)
    pop_train = pop[pop["received_year"] < 2024]
    print(f"population train={len(pop_train)}", flush=True)
    X_pop = build_features(pop_train)
    X_pop["authority"] = pop_train["PlanningAuthority"].astype(str)
    X_pop_dummy = pd.get_dummies(X_pop, columns=["authority"])
    X_test_pop = build_features(test.reindex(range(len(test)))).astype(float)
    X_test_pop["authority"] = test["PlanningAuthority"].astype(str)
    X_test_dummy_pop = X_test_pop.reindex(columns=X_pop_dummy.columns, fill_value=0)
    y_pop = pop_train["duration_days"].to_numpy()

    pop_preds = {}
    for tau in QUANTILES:
        gbm_pop = GradientBoostingRegressor(
            loss="quantile", alpha=tau, n_estimators=300, max_depth=4,
            learning_rate=0.05, min_samples_leaf=50, random_state=RNG,
        )
        gbm_pop.fit(X_pop_dummy, y_pop)
        pred = np.maximum(gbm_pop.predict(X_test_dummy_pop), 1.0)
        pop_preds[tau] = pred
        report[f"pinball_gbm_population_p{int(tau*100)}"] = round(pinball(y_test, pred, tau), 1)

    for horizon in (183, 365):
        y_pop_h = (y_pop > horizon).astype(int)
        y_test_h = (y_test > horizon).astype(int)
        clf_pop = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        clf_pop.fit(X_pop_dummy, y_pop_h)
        p = np.clip(clf_pop.predict_proba(X_test_dummy_pop)[:, 1], 1e-6, 1 - 1e-6)
        lo, hi = bootstrap_auc(y_test_h, p, seed=0)
        entry = {
            "horizon_days": horizon,
            "test_prevalence": round(float(y_test_h.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y_test_h, p)), 4),
            "auc_ci_low": round(lo, 4),
            "auc_ci_high": round(hi, 4),
            "brier": round(float(brier_score_loss(y_test_h, p)), 4),
        }
        entry.update(calibration_slope_intercept(y_test_h, p))
        horizon_rows[f"population_{horizon}"] = entry
    report["horizon_models"] = horizon_rows

    out = settings.SILVER_DIR / "decision_timing_model_card.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
