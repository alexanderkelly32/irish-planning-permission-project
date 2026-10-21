"""Runner: permission-timing forecast (product brief 6.8/6.9, must-ship #8).

Outcome: days from submission (ReceivedDate) to local decision (DecisionDate)
for granted 10+ unit schemes. Outputs:
  - P20/P50/P80 duration forecasts (point estimates with pinball-loss eval);
  - fixed-horizon probabilities P(decision > 12m) and P(decision > 24m);
  - baselines: overall median, authority-year-type strata; challenger adds
    TF-IDF description features via ridge on log-days / logistic horizons.
Temporal split by received year (train < 2020, test >= 2021). Research-grade;
calibration and baselines are the acceptance criteria (brief 11).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression, Ridge  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, calibration_slope_intercept, load_cohort  # noqa: E402
from devrisk.models.survival import kaplan_meier, km_probability_by  # noqa: E402

HORIZONS = (365, 548)


def pinball(y: np.ndarray, pred: np.ndarray, tau: float) -> float:
    diff = y - pred
    return float(np.mean(np.where(diff >= 0, tau * diff, (tau - 1) * diff)))


if __name__ == "__main__":
    frame = load_cohort()
    frame = frame[frame["planning_duration_days"].notna()].copy()
    frame["log_days"] = np.log1p(frame["planning_duration_days"])

    train = frame[frame["received_year"] < 2020]
    test = frame[frame["received_year"] >= 2021]
    print(f"train={len(train)}, test={len(test)}", flush=True)

    report: dict[str, object] = {"split": "train received < 2020, test received >= 2021"}

    # Baseline 0: overall median (constant).
    overall_median = float(train["planning_duration_days"].median())
    report["baseline_overall_median_days"] = round(overall_median, 1)

    # Baseline 1: authority-year-type strata quantiles (fallback authority).
    strata = train.groupby(["PlanningAuthority", "received_year", "scheme_type"])["planning_duration_days"].quantile([0.2, 0.5, 0.8]).unstack()
    strata.columns = ["q20", "q50", "q80"]
    strata_auth = train.groupby(["PlanningAuthority", "received_year"])["planning_duration_days"].quantile([0.2, 0.5, 0.8]).unstack()
    strata_auth.columns = ["q20_auth", "q50_auth", "q80_auth"]
    overall_q = {
        "q20_overall": float(train["planning_duration_days"].quantile(0.2)),
        "q50_overall": float(train["planning_duration_days"].quantile(0.5)),
        "q80_overall": float(train["planning_duration_days"].quantile(0.8)),
    }
    report["overall_quantiles_days"] = overall_q
    test = test.merge(strata.reset_index(), on=["PlanningAuthority", "received_year", "scheme_type"], how="left")
    test = test.merge(strata_auth.reset_index(), on=["PlanningAuthority", "received_year"], how="left")
    for q in ("20", "50", "80"):
        test[f"strata_q{q}"] = test[f"q{q}"].fillna(test[f"q{q}_auth"]).fillna(overall_q[f"q{q}_overall"])

    # Challenger: ridge on log-days with structured + text.
    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"])
    text_test = tfidf.transform(test["description_lower"])
    structured_cols = ["log_units", "log_site_area", "density", "received_year", "covid_era", "type_house", "type_apartment"]
    X_train = np.hstack([train[structured_cols].fillna(0.0).to_numpy(), text_train.toarray()])
    X_test = np.hstack([test[structured_cols].fillna(0.0).to_numpy(), text_test.toarray()])
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train_s, train["log_days"])
    test["ridge_log_days"] = ridge.predict(X_test_s)
    test["ridge_days"] = np.expm1(test["ridge_log_days"]).clip(lower=30, upper=2000)

    for tau, q in ((0.2, "20"), (0.5, "50"), (0.8, "80")):
        report[f"pinball_median_p{int(tau*100)}"] = round(
            pinball(test["planning_duration_days"].to_numpy(), np.full(len(test), overall_median), tau), 1)
        report[f"pinball_strata_p{int(tau*100)}"] = round(
            pinball(test["planning_duration_days"].to_numpy(), test[f"strata_q{q}"].to_numpy(), tau), 1)
        report[f"pinball_ridge_p{int(tau*100)}"] = round(
            pinball(test["planning_duration_days"].to_numpy(), test["ridge_days"].to_numpy(), tau), 1)

    # Fixed-horizon probabilities.
    horizon_rows = {}
    for horizon in HORIZONS:
        y_train_h = (train["planning_duration_days"] > horizon).astype(int).to_numpy()
        y_test_h = (test["planning_duration_days"] > horizon).astype(int).to_numpy()
        base_rate = y_train_h.mean()
        if y_train_h.sum() < 10 or y_test_h.sum() < 5:
            horizon_rows[str(horizon)] = {"status": "skipped_too_few_positives",
                                          "train_prevalence": round(float(base_rate), 4),
                                          "test_prevalence": round(float(y_test_h.mean()), 4)}
            continue
        clf = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        clf.fit(X_train_s, y_train_h)
        p = np.clip(clf.predict_proba(X_test_s)[:, 1], 1e-6, 1 - 1e-6)
        lo, hi = bootstrap_auc(y_test_h, p, seed=0)
        entry = {
            "horizon_days": horizon,
            "train_prevalence": round(float(base_rate), 4),
            "test_prevalence": round(float(y_test_h.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y_test_h, p)), 4),
            "auc_ci_low": round(lo, 4),
            "auc_ci_high": round(hi, 4),
            "brier": round(float(brier_score_loss(y_test_h, p)), 4),
            "brier_base_rate": round(float(brier_score_loss(y_test_h, np.full(len(y_test_h), base_rate))), 4),
        }
        entry.update(calibration_slope_intercept(y_test_h, p))
        horizon_rows[str(horizon)] = entry
    report["horizon_models"] = horizon_rows

    km = kaplan_meier(test["planning_duration_days"].to_numpy(), np.ones(len(test)))
    report["km_test"] = {
        "p_decision_by_12m": round(km_probability_by(km, 365), 3),
        "p_decision_by_24m": round(km_probability_by(km, 730), 3),
    }

    test_out = test[["case_key", "PlanningAuthority", "received_year", "planning_duration_days",
                     "strata_q20", "strata_q50", "strata_q80", "ridge_days"]].copy()
    test_out.to_csv(settings.SILVER_DIR / "permission_timing_predictions.csv", index=False)

    out = settings.SILVER_DIR / "permission_timing_model_card.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
