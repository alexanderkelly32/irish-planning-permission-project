"""Runner: sale smooth CDF v2 - adds constraint proximity features.

v1 (scheme + market context) showed weak/no discrimination (td-AUC ~0.46-0.68).
v2 adds the submission-time-safe constraint set. Same split (grant < 2021
train, >= 2021 holdout).
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
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from run_sale_timing_model import build_frame, county_name, market_context  # noqa: E402
from run_sale_timing_smooth import HORIZONS, QUANTILE_GRID, monotone_cdf  # noqa: E402

RNG = 7

if __name__ == "__main__":
    frame = build_frame()
    frame["county_ppr"] = frame["PlanningAuthority"].map(county_name)
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    context = market_context(frame, ppr)
    frame = pd.concat([frame, context], axis=1)
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    frame = frame.merge(constraints, on="case_key", how="left")

    train = frame[frame["grant_year"] < 2021]
    test = frame[frame["grant_year"] >= 2021]
    y_train = train["sale_days"].to_numpy()
    y_test = test["sale_days"].to_numpy()
    print(f"train={len(train)}, test={len(test)}", flush=True)

    structured_cols = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month",
                       "covid_era", "price_level", "volume_12m", "momentum"]
    constraint_cols = ["fluvial_hit_any", "coastal_hit_any", "coastal_min_logdist", "fluvial_min_logdist",
                       "flood_depth__ncfhm__rp100__m", "niah_min_dist", "niah_count_500m", "wwtp_min_dist",
                       "traffic_min_dist", "natura_min_dist"]

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    X_train = np.hstack([train[structured_cols + constraint_cols].fillna(0.0).values, text_train])
    X_test = np.hstack([test[structured_cols + constraint_cols].fillna(0.0).values, text_test])

    models = {}
    quantile_predictions = []
    for q in QUANTILE_GRID:
        model = GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=10, random_state=RNG)
        model.fit(X_train, y_train)
        models[round(float(q), 2)] = model
        quantile_predictions.append(np.maximum(model.predict(X_test), 1.0))
        print(f"fit q={q:.2f}", flush=True)

    quantile_matrix = np.maximum.accumulate(np.vstack(quantile_predictions), axis=0)

    report = {"model": "sale_timing_smooth_cdf_v2", "n": {"train": int(len(train)), "test": int(len(test))},
              "added_features": constraint_cols}

    coverage_devs = []
    for row_idx, q in enumerate(QUANTILE_GRID):
        predicted = quantile_matrix[row_idx, :]
        coverage_devs.append(float(np.mean(y_test <= predicted)) - q)
    coverage_devs = np.array(coverage_devs)
    report["coverage_calibration"] = {
        "mean_abs_dev_pp": round(float(np.mean(np.abs(coverage_devs)) * 100), 1),
        "max_abs_dev_pp": round(float(np.max(np.abs(coverage_devs)) * 100), 1),
    }

    report["time_dependent_auc"] = {}
    report["brier_by_horizon"] = {}
    for horizon in HORIZONS:
        prob_before = monotone_cdf(quantile_matrix, QUANTILE_GRID, horizon)
        y_h = (y_test <= horizon).astype(int)
        auc = roc_auc_score(y_h, prob_before) if y_h.mean() not in (0.0, 1.0) else None
        report["time_dependent_auc"][str(horizon)] = round(float(auc), 4) if auc is not None else None
        report["brier_by_horizon"][str(horizon)] = {
            "prevalence": round(float(y_h.mean()), 4),
            "brier_smooth": round(float(brier_score_loss(y_h, np.clip(prob_before, 1e-6, 1 - 1e-6))), 4),
            "brier_base": round(float(brier_score_loss(y_h, np.full(len(y_h), y_h.mean()))), 4),
        }

    (settings.SILVER_DIR / "sale_timing_smooth_cdf_v2.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
