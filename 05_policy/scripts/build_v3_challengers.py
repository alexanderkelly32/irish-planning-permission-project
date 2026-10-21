#!/usr/bin/env python3
"""v3 challengers: neural net + gradient boosting + blend, on v3's EXACT
submission-time feature matrix.

Discipline: same pre-2025 train / 2025 holdout, same features, same target.
The frozen v3 ranking baseline is ROC-AUC 0.7989 / AP 0.4202 on the holdout.
A challenger is only interesting if it beats that with a full validation
story - this script measures ranking discrimination (AUC/AP) only.

Output: raw_planning_v3_challengers.json (candidate record; v3 untouched).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_comparable_feature_experiment import COMPARABLE_FEATURES_PATH, V3_FEATURES  # noqa: E402
from build_national_residential_model_v2 import TRAIN_CUTOFF, load_data_with_history  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402


def preprocess() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    data = load_data_with_history().reset_index(drop=True)
    comparable = pd.read_parquet(COMPARABLE_FEATURES_PATH)
    data = data.merge(comparable, on="case_key", how="left")
    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].copy()
    preprocessor = build_scaled_pipeline(V3_FEATURES[3:]).named_steps["preprocessor"]
    x_train = preprocessor.fit_transform(train[V3_FEATURES])
    x_test = preprocessor.transform(test[V3_FEATURES])
    return x_train, train["target_refused"].to_numpy(), x_test, test["target_refused"].to_numpy()


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "average_precision": round(float(average_precision_score(y, p)), 4),
    }


def main() -> None:
    print("preprocessing...", flush=True)
    start = time.time()
    x_train, y_train, x_test, y_test = preprocess()
    print(f"train {x_train.shape} test {x_test.shape} ({time.time()-start:.0f}s)", flush=True)

    results: dict = {
        "frozen_v3_baseline": {"roc_auc": 0.7989, "average_precision": 0.4202},
        "train_rows": int(len(y_train)),
        "test_rows": int(len(y_test)),
    }

    from sklearn.linear_model import LogisticRegression

    start = time.time()
    logistic = LogisticRegression(max_iter=3000, class_weight="balanced", C=0.5, solver="liblinear")
    logistic.fit(x_train, y_train)
    logistic_p = logistic.predict_proba(x_test)[:, 1]
    results["logistic_replication"] = {**metrics(y_test, logistic_p), "seconds": round(time.time() - start)}
    print(json.dumps({"logistic_replication": results["logistic_replication"]}), flush=True)

    from sklearn.neural_network import MLPClassifier

    start = time.time()
    mlp = MLPClassifier(
        hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
        alpha=1e-4, batch_size=512, learning_rate_init=1e-3,
        max_iter=12, early_stopping=True, n_iter_no_change=3,
        validation_fraction=0.05, random_state=7, verbose=False,
    )
    mlp.fit(x_train, y_train)
    mlp_p = mlp.predict_proba(x_test)[:, 1]
    results["mlp_128_64"] = {**metrics(y_test, mlp_p), "seconds": round(time.time() - start), "best_iteration": mlp.n_iter_}
    print(json.dumps({"mlp_128_64": results["mlp_128_64"]}), flush=True)

    from lightgbm import LGBMClassifier

    start = time.time()
    lgbm = LGBMClassifier(
        n_estimators=400, learning_rate=0.05, num_leaves=31,
        class_weight="balanced", random_state=7, verbose=-1, n_jobs=4,
    )
    lgbm.fit(x_train, y_train)
    lgbm_p = lgbm.predict_proba(x_test)[:, 1]
    results["lgbm_400"] = {**metrics(y_test, lgbm_p), "seconds": round(time.time() - start)}
    print(json.dumps({"lgbm_400": results["lgbm_400"]}), flush=True)

    blend_p = (logistic_p + mlp_p + lgbm_p) / 3.0
    results["blend_logistic_mlp_lgbm"] = metrics(y_test, blend_p)
    print(json.dumps({"blend": results["blend_logistic_mlp_lgbm"]}), flush=True)

    results["caveat"] = (
        "Challengers use v3's exact submission-time feature matrix and the same "
        "pre-2025/2025 split. This measures ranking discrimination only; any "
        "candidate that beats 0.7989 would still need the full validation "
        "standard (calibration, CIs, bands, temporal windows) before promotion."
    )
    (OUTPUT_DIR / "raw_planning_v3_challengers.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
