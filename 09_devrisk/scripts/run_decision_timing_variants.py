"""Runner: decision-timing model variants - does including <10-unit schemes help?

Variants (all evaluated on the same GE10 holdout, received >= 2024, n=433):
  A. GE10-only (current shipped model)
  B. all-residential weighted 0.05 for <10 units
  C. all-residential weighted 0.20 for <10 units
  D. all-residential unweighted (known-weak)

Metric: pinball loss at P20/P50/P80 + MAE on the GE10 holdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402
from scripts.run_decision_timing import (  # noqa: E402
    QUANTILES,
    add_congestion_features_fast,
    build_features,
    load_cohort,
    load_population_cohort,
)

RNG = 7


def pinball(y, pred, tau):
    diff = y - pred
    return float(np.mean(np.where(diff >= 0, tau * diff, (tau - 1) * diff)))


def evaluate_variant(name, X_train, y_train, weights, X_test, y_test):
    rows = {}
    for tau in QUANTILES:
        gbm = GradientBoostingRegressor(
            loss="quantile", alpha=tau, n_estimators=300, max_depth=3,
            learning_rate=0.05, min_samples_leaf=20, random_state=RNG,
        )
        gbm.fit(X_train, y_train, sample_weight=weights if weights is not None else None)
        pred = np.maximum(gbm.predict(X_test), 1.0)
        rows[f"pinball_p{int(tau * 100)}"] = round(pinball(y_test, pred, tau), 1)
    return name, rows


if __name__ == "__main__":
    # GE10 cohort with features (train < 2024, holdout >= 2024).
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

    # Population frame (all residential).
    pop = load_population_cohort()
    pop = add_congestion_features_fast(pop)
    pop_train = pop[pop["received_year"] < 2024]
    pop_units = pd.to_numeric(pop_train["NumResidentialUnits"], errors="coerce")
    y_pop = pop_train["duration_days"].to_numpy()
    X_pop = build_features(pop_train)
    X_pop["authority"] = pop_train["PlanningAuthority"].astype(str)
    X_pop_d = pd.get_dummies(X_pop, columns=["authority"])
    X_test_pop = X_test_d.reindex(columns=X_pop_d.columns, fill_value=0)

    results = {}
    for name, Xt, yt, w in (
        ("A_ge10_only", X_train_d, y_train, None),
        ("B_pop_weighted_005", X_pop_d, y_pop, np.where(pop_units >= 10, 1.0, 0.05)),
        ("C_pop_weighted_020", X_pop_d, y_pop, np.where(pop_units >= 10, 1.0, 0.20)),
        ("D_pop_unweighted", X_pop_d, y_pop, None),
    ):
        name, rows = evaluate_variant(name, Xt, yt, w, X_test_pop if "pop" in name else X_test_d, y_test)
        results[name] = rows
        print(name, rows, flush=True)

    out = settings.SILVER_DIR / "decision_timing_variants.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
