"""Runner: smooth conditional CDF for grant->first-sale timing (bin-free).

19-quantile GBMs + per-scheme monotone interpolation -> P(T <= t) for ANY
horizon. Continuous evaluation: time-dependent AUC curve across horizons
(12/18/24/30/36/48/60 months) instead of binned horizon classifiers, plus
bin-free quantile coverage calibration and Brier vs strata at each horizon.

Conditional-on-sold framing (unlinked = UNKNOWN, never "never sells":
retained/BTR schemes are not random censoring).
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

RNG = 7
QUANTILE_GRID = np.arange(0.05, 1.0, 0.05)
HORIZONS = [365, 548, 730, 913, 1096, 1461, 1826]


def monotone_cdf(quantile_matrix: np.ndarray, grid: np.ndarray, horizon: float) -> np.ndarray:
    cdf = np.zeros(quantile_matrix.shape[1])
    for scheme in range(quantile_matrix.shape[1]):
        values = quantile_matrix[:, scheme]
        idx = np.searchsorted(values, horizon)
        if idx == 0:
            cdf[scheme] = 0.0
        elif idx >= len(values):
            cdf[scheme] = 1.0
        else:
            lo_q, hi_q = grid[idx - 1], grid[idx]
            lo_v, hi_v = values[idx - 1], values[idx]
            frac = (horizon - lo_v) / (hi_v - lo_v) if hi_v > lo_v else 0.0
            cdf[scheme] = lo_q + frac * (hi_q - lo_q)
    return np.clip(cdf, 0.0, 1.0)


if __name__ == "__main__":
    frame = build_frame()
    frame["county_ppr"] = frame["PlanningAuthority"].map(county_name)
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    context = market_context(frame, ppr)
    frame = pd.concat([frame, context], axis=1)

    train = frame[frame["grant_year"] < 2021]
    test = frame[frame["grant_year"] >= 2021]
    y_train = train["sale_days"].to_numpy()
    y_test = test["sale_days"].to_numpy()
    print(f"train={len(train)}, test={len(test)}, test median {np.median(y_test):.0f}d", flush=True)

    structured_cols = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month",
                       "covid_era", "price_level", "volume_12m", "momentum"]
    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    X_train = np.hstack([train[structured_cols].fillna(0.0).values, text_train])
    X_test = np.hstack([test[structured_cols].fillna(0.0).values, text_test])

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

    report = {"model": "sale_timing_smooth_cdf_v1", "n": {"train": int(len(train)), "test": int(len(test))},
              "test_median_days": round(float(np.median(y_test)), 1)}

    coverage_devs = []
    for row_idx, q in enumerate(QUANTILE_GRID):
        predicted = quantile_matrix[row_idx, :]
        coverage_devs.append(float(np.mean(y_test <= predicted)) - q)
    coverage_devs = np.array(coverage_devs)
    report["coverage_calibration"] = {
        "mean_abs_dev_pp": round(float(np.mean(np.abs(coverage_devs)) * 100), 1),
        "max_abs_dev_pp": round(float(np.max(np.abs(coverage_devs)) * 100), 1),
    }

    interval_80 = quantile_matrix[17, :] - quantile_matrix[1, :]
    report["interval_80_mean_width_days"] = round(float(np.mean(interval_80)), 1)

    report["time_dependent_auc"] = {}
    report["brier_by_horizon"] = {}
    for horizon in HORIZONS:
        prob_before = monotone_cdf(quantile_matrix, QUANTILE_GRID, horizon)
        y_h = (y_test <= horizon).astype(int)
        if y_h.mean() not in (0.0, 1.0):
            auc = roc_auc_score(y_h, prob_before)
        else:
            auc = None
        report["time_dependent_auc"][str(horizon)] = round(float(auc), 4) if auc is not None else None
        brier_smooth = brier_score_loss(y_h, np.clip(prob_before, 1e-6, 1 - 1e-6))
        brier_base = brier_score_loss(y_h, np.full(len(y_h), y_h.mean()))
        report["brier_by_horizon"][str(horizon)] = {
            "prevalence": round(float(y_h.mean()), 4),
            "brier_smooth": round(float(brier_smooth), 4),
            "brier_base": round(float(brier_base), 4),
        }

    (settings.SILVER_DIR / "sale_timing_smooth_cdf.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    import joblib

    artifact = {
        "model_version": "sale_timing_smooth_cdf_v1",
        "quantile_grid": QUANTILE_GRID.tolist(),
        "models": models,
        "structured_columns": structured_cols,
        "tfidf": tfidf,
        "horizons": HORIZONS,
    }
    path = settings.GOLD_DIR / "sale_timing_smooth_v1.joblib"
    joblib.dump(artifact, path)
    print(f"persisted -> {path}")
