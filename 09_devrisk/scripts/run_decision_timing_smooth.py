"""Runner: smooth conditional CDF for decision timing (bin-free).

Fits quantile GBMs on a fine grid (0.05..0.95), enforces monotonicity per
scheme, and derives smooth P(T > t) for any horizon. Calibration is measured
by quantile coverage (empirical share of observations below each predicted
quantile should equal the quantile) - no bins.
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
from sklearn.metrics import brier_score_loss  # noqa: E402

from devrisk import settings  # noqa: E402
from run_decision_timing import add_congestion_features_fast, build_features, load_cohort  # noqa: E402

RNG = 7
QUANTILE_GRID = np.arange(0.05, 1.0, 0.05)


if __name__ == "__main__":
    frame = load_cohort()
    frame = add_congestion_features_fast(frame)
    train = frame[frame["received_year"] < 2024]
    test = frame[frame["received_year"] >= 2024]
    y_train = train["duration_days"].to_numpy()
    y_test = test["duration_days"].to_numpy()

    X_train = build_features(train)
    X_test = build_features(test)
    X_train["authority"] = train["PlanningAuthority"].astype(str)
    X_test["authority"] = test["PlanningAuthority"].astype(str)
    X_train_d = pd.get_dummies(X_train, columns=["authority"])
    X_test_d = X_test.reindex(columns=X_train_d.columns, fill_value=0)

    models = {}
    quantile_predictions = []
    for q in QUANTILE_GRID:
        model = GradientBoostingRegressor(
            loss="quantile", alpha=q, n_estimators=300, max_depth=3,
            learning_rate=0.05, min_samples_leaf=20, random_state=RNG,
        )
        model.fit(X_train_d, y_train)
        models[round(float(q), 2)] = model
        quantile_predictions.append(np.maximum(model.predict(X_test_d), 1.0))
        print(f"fit q={q:.2f}", flush=True)

    # Monotone quantile function per scheme (accumulate over sorted grid).
    quantile_matrix = np.vstack(quantile_predictions)  # rows = q, cols = schemes
    quantile_matrix = np.maximum.accumulate(quantile_matrix, axis=0)

    def smooth_prob_above(horizon: float) -> np.ndarray:
        return 1.0 - np.clip(np.interp(horizon, quantile_matrix[:, 0], QUANTILE_GRID), 0.0, 1.0) if False else 1.0 - _cdf_at(horizon)

    def _cdf_at(horizon: float) -> np.ndarray:
        # For each scheme, fraction of grid quantiles whose value <= horizon,
        # linearly interpolated at the crossing for smoothness.
        below = quantile_matrix <= horizon
        # find first q where qvalue > horizon; interpolate
        cdf = np.zeros(quantile_matrix.shape[1])
        for scheme in range(quantile_matrix.shape[1]):
            values = quantile_matrix[:, scheme]
            idx = np.searchsorted(values, horizon)
            if idx == 0:
                cdf[scheme] = 0.0
            elif idx >= len(values):
                cdf[scheme] = 1.0
            else:
                lo_q, hi_q = QUANTILE_GRID[idx - 1], QUANTILE_GRID[idx]
                lo_v, hi_v = values[idx - 1], values[idx]
                frac = (horizon - lo_v) / (hi_v - lo_v) if hi_v > lo_v else 0.0
                cdf[scheme] = lo_q + frac * (hi_q - lo_q)
        return cdf

    report = {"quantiles_fitted": int(len(QUANTILE_GRID))}

    # Bin-free calibration: quantile coverage.
    coverage_devs = []
    for row_idx, q in enumerate(QUANTILE_GRID):
        predicted = quantile_matrix[row_idx, :]
        observed_coverage = float(np.mean(y_test <= predicted))
        coverage_devs.append(observed_coverage - q)
    coverage_devs = np.array(coverage_devs)
    report["coverage_calibration"] = {
        "mean_abs_dev_pp": round(float(np.mean(np.abs(coverage_devs)) * 100), 1),
        "max_abs_dev_pp": round(float(np.max(np.abs(coverage_devs)) * 100), 1),
        "worst_quantile": round(float(QUANTILE_GRID[np.argmax(np.abs(coverage_devs))]), 2),
        "by_quantile": {round(float(q), 2): round(float(dev) * 100, 1) for q, dev in zip(QUANTILE_GRID, coverage_devs, strict=False)},
    }

    # Smooth horizon probabilities + proper scoring.
    for horizon in (183, 365):
        prob_above = 1.0 - _cdf_at(horizon)
        y_h = (y_test > horizon).astype(int)
        report[f"horizon_{horizon}d"] = {
            "prevalence": round(float(y_h.mean()), 4),
            "brier_smooth_cdf": round(float(brier_score_loss(y_h, np.clip(prob_above, 1e-6, 1 - 1e-6))), 4),
            "brier_constant": round(float(brier_score_loss(y_h, np.full(len(y_h), y_h.mean()))), 4),
            "mean_predicted": round(float(prob_above.mean()), 4),
            "calibration_in_large_pp": round(float(prob_above.mean() - y_h.mean()) * 100, 2),
        }

    out = settings.SILVER_DIR / "decision_timing_smooth_cdf.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    import joblib

    artifact = {
        "model_version": "decision_timing_smooth_cdf_v1",
        "quantile_grid": QUANTILE_GRID.tolist(),
        "models": models,
        "feature_columns": list(X_train_d.columns),
        "training_cutoff_exclusive": "2024-01-01",
    }
    path = settings.GOLD_DIR / "decision_timing_smooth_v1.joblib"
    joblib.dump(artifact, path)
    print(f"persisted -> {path}")
