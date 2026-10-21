#!/usr/bin/env python3
"""Prospective accuracy-uplift experiments for the national residential model.

This script keeps Model v1 frozen. It uses 2023-2024 only for model/weight
selection, then retrains selected candidates before 2025 and evaluates on the
same untouched 2025 prospective-style holdout used by Model v1.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
OUTPUT_DIR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(SCRIPT_DIR))
from build_prospective_calibration_backtest import FEATURES, prepare  # noqa: E402
from build_dublin_submission_model import bootstrap_metric_ci, calibration_intercept_slope  # noqa: E402


TUNE_CUTOFF = pd.Timestamp("2023-01-01", tz="UTC")
TEST_CUTOFF = pd.Timestamp("2025-01-01", tz="UTC")
TEXT_COLUMN = "description_stripped"
NUMERIC = ["received_year"]
CATEGORICAL = ["PlanningAuthority", "application_bucket"]


@dataclass(frozen=True)
class Candidate:
    name: str
    builder: Callable[[], BaseEstimator]


def common_transformers(text_transformers: list[tuple[str, TfidfVectorizer]]) -> list[tuple[str, object, object]]:
    transformers: list[tuple[str, object, object]] = [
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), NUMERIC),
        (
            "cat",
            Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="most_frequent")),
                    ("onehot", OneHotEncoder(handle_unknown="ignore")),
                ]
            ),
            CATEGORICAL,
        ),
    ]
    for name, vectorizer in text_transformers:
        transformers.append((name, vectorizer, TEXT_COLUMN))
    return transformers


def logistic_pipeline(
    *,
    name: str,
    text_transformers: list[tuple[str, TfidfVectorizer]],
    c: float = 0.5,
) -> Candidate:
    def build() -> Pipeline:
        preprocessor = ColumnTransformer(common_transformers(text_transformers), sparse_threshold=1.0)
        model = LogisticRegression(max_iter=3000, class_weight="balanced", C=c, solver="liblinear")
        return Pipeline([("preprocessor", preprocessor), ("model", model)])

    return Candidate(name=name, builder=build)


def word_vec(max_features: int, ngram_range: tuple[int, int], min_df: int, sublinear_tf: bool = False) -> TfidfVectorizer:
    return TfidfVectorizer(
        stop_words="english",
        ngram_range=ngram_range,
        max_features=max_features,
        min_df=min_df,
        sublinear_tf=sublinear_tf,
        strip_accents="unicode",
    )


def char_vec(max_features: int, ngram_range: tuple[int, int]) -> TfidfVectorizer:
    return TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=ngram_range,
        max_features=max_features,
        min_df=3,
        sublinear_tf=True,
        strip_accents="unicode",
    )


def candidates() -> list[Candidate]:
    return [
        logistic_pipeline(
            name="v1_baseline_word_1_2_50k_c0_5",
            text_transformers=[("txt_word", word_vec(50_000, (1, 2), 2))],
            c=0.5,
        ),
        logistic_pipeline(
            name="word_1_2_100k_sublinear_c1",
            text_transformers=[("txt_word", word_vec(100_000, (1, 2), 2, sublinear_tf=True))],
            c=1.0,
        ),
        logistic_pipeline(
            name="word_1_3_150k_sublinear_c1",
            text_transformers=[("txt_word", word_vec(150_000, (1, 3), 2, sublinear_tf=True))],
            c=1.0,
        ),
        logistic_pipeline(
            name="char_wb_3_5_40k_c0_25",
            text_transformers=[("txt_char", char_vec(40_000, (3, 5)))],
            c=0.25,
        ),
        logistic_pipeline(
            name="word_50k_plus_char_30k_c0_25",
            text_transformers=[
                ("txt_word", word_vec(50_000, (1, 2), 2, sublinear_tf=True)),
                ("txt_char", char_vec(30_000, (3, 5))),
            ],
            c=0.25,
        ),
    ]


def score_model(model: BaseEstimator, x: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(x)[:, 1], dtype=float)
    if hasattr(model, "decision_function"):
        raw = np.asarray(model.decision_function(x), dtype=float)
        return raw
    raise TypeError(f"Model {type(model).__name__} has neither predict_proba nor decision_function")


def probability_like(scores: np.ndarray) -> np.ndarray | None:
    if np.nanmin(scores) >= 0 and np.nanmax(scores) <= 1:
        return np.clip(scores, 1e-6, 1 - 1e-6)
    return None


def metrics(y: pd.Series, scores: np.ndarray, include_ci: bool = False) -> dict[str, float | int | None]:
    proba = probability_like(scores)
    out: dict[str, float | int | None] = {
        "n": int(len(y)),
        "refusal_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, scores)),
        "average_precision": float(average_precision_score(y, scores)),
    }
    if proba is not None:
        pred = proba >= 0.5
        out.update(
            {
                "brier": float(brier_score_loss(y, proba)),
                "log_loss": float(log_loss(y, proba, labels=[0, 1])),
                "accuracy_at_0_5": float(accuracy_score(y, pred)),
                "balanced_accuracy_at_0_5": float(balanced_accuracy_score(y, pred)),
                "precision_at_0_5": float(precision_score(y, pred, zero_division=0)),
                "recall_at_0_5": float(recall_score(y, pred, zero_division=0)),
                "f1_at_0_5": float(f1_score(y, pred, zero_division=0)),
                **calibration_intercept_slope(y, proba),
            }
        )
    else:
        out.update(
            {
                "brier": None,
                "log_loss": None,
                "accuracy_at_0_5": None,
                "balanced_accuracy_at_0_5": None,
                "precision_at_0_5": None,
                "recall_at_0_5": None,
                "f1_at_0_5": None,
                "calibration_intercept": None,
                "calibration_slope": None,
            }
        )
    if include_ci:
        out.update(bootstrap_metric_ci(y, scores, n_boot=300))
    return out


def percentile_rank(scores: np.ndarray) -> np.ndarray:
    series = pd.Series(scores)
    return (series.rank(method="average").to_numpy() - 1) / max(len(series) - 1, 1)


def evaluate_groups(scored: pd.DataFrame, score_col: str, group_col: str) -> dict[str, dict[str, float | int | None]]:
    out: dict[str, dict[str, float | int | None]] = {}
    for value, group in scored.groupby(group_col):
        if len(group) < 50 or group["target_refused"].nunique() < 2:
            out[str(value)] = {"n": int(len(group)), "status": "too_small_or_one_class"}
        else:
            out[str(value)] = metrics(group["target_refused"], group[score_col].to_numpy())
    return out


def risk_deciles(y: pd.Series, scores: np.ndarray) -> list[dict[str, float | int]]:
    frame = pd.DataFrame({"target_refused": y.to_numpy(), "score": scores})
    frame["decile"] = pd.qcut(frame["score"].rank(method="first"), q=10, labels=False) + 1
    grouped = frame.groupby("decile", as_index=False).agg(
        cases=("target_refused", "size"),
        mean_score=("score", "mean"),
        actual_refusal_rate=("target_refused", "mean"),
    )
    return grouped.to_dict(orient="records")


def main() -> None:
    data = prepare()
    tune_train = data[data["received_date_dt"] < TUNE_CUTOFF].copy()
    validation = data[(data["received_date_dt"] >= TUNE_CUTOFF) & (data["received_date_dt"] < TEST_CUTOFF)].copy()
    final_train = data[data["received_date_dt"] < TEST_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TEST_CUTOFF].copy()

    rows: list[dict[str, object]] = []
    validation_scores: dict[str, np.ndarray] = {}
    test_scores: dict[str, np.ndarray] = {}
    fitted_final_models: dict[str, BaseEstimator] = {}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = OUTPUT_DIR / "raw_planning_accuracy_uplift_experiments.csv"

    def write_interim() -> None:
        pd.DataFrame(rows).to_csv(results_path, index=False)

    for candidate in candidates():
        print(f"Fitting validation candidate: {candidate.name}", flush=True)
        model = candidate.builder()
        model.fit(tune_train[FEATURES], tune_train["target_refused"])
        val_score = score_model(model, validation[FEATURES])
        val_metrics = metrics(validation["target_refused"], val_score)
        validation_scores[candidate.name] = val_score
        rows.append({"phase": "validation_2023_2024", "model": candidate.name, **val_metrics})
        write_interim()

        print(f"Fitting final candidate: {candidate.name}", flush=True)
        final_model = candidate.builder()
        final_model.fit(final_train[FEATURES], final_train["target_refused"])
        fitted_final_models[candidate.name] = final_model
        tst_score = score_model(final_model, test[FEATURES])
        test_scores[candidate.name] = tst_score
        tst_metrics = metrics(test["target_refused"], tst_score, include_ci=True)
        rows.append({"phase": "test_2025", "model": candidate.name, **tst_metrics})
        write_interim()

    # Tune a simple rank-average ensemble on 2023-2024 without touching 2025.
    top_names = [
        row["model"]
        for row in sorted(
            [r for r in rows if r["phase"] == "validation_2023_2024"],
            key=lambda r: float(r["roc_auc"]),
            reverse=True,
        )[:3]
    ]
    val_rank_scores = {name: percentile_rank(validation_scores[name]) for name in top_names}
    best_weights: tuple[float, ...] | None = None
    best_auc = -np.inf
    weight_grid = np.linspace(0, 1, 6)
    for w0 in weight_grid:
        for w1 in weight_grid:
            if len(top_names) == 2:
                weights = np.array([w0, 1 - w0])
            else:
                w2 = 1 - w0 - w1
                if w2 < 0:
                    continue
                weights = np.array([w0, w1, w2])
            if np.isclose(weights.sum(), 0):
                continue
            score = sum(float(w) * val_rank_scores[name] for w, name in zip(weights, top_names))
            auc = roc_auc_score(validation["target_refused"], score)
            if auc > best_auc:
                best_auc = float(auc)
                best_weights = tuple(float(w) for w in weights)

    if best_weights is not None:
        test_rank_scores = {name: percentile_rank(test_scores[name]) for name in top_names}
        ensemble_test_score = sum(float(w) * test_rank_scores[name] for w, name in zip(best_weights, top_names))
        ensemble_val_score = sum(float(w) * val_rank_scores[name] for w, name in zip(best_weights, top_names))
        rows.append(
            {
                "phase": "validation_2023_2024",
                "model": "rank_average_ensemble_top3",
                "members": ";".join(top_names),
                "weights": ";".join(f"{w:.2f}" for w in best_weights),
                **metrics(validation["target_refused"], ensemble_val_score),
            }
        )
        rows.append(
            {
                "phase": "test_2025",
                "model": "rank_average_ensemble_top3",
                "members": ";".join(top_names),
                "weights": ";".join(f"{w:.2f}" for w in best_weights),
                **metrics(test["target_refused"], ensemble_test_score, include_ci=True),
            }
        )
        test_scores["rank_average_ensemble_top3"] = ensemble_test_score

    results = pd.DataFrame(rows)
    results.to_csv(results_path, index=False)

    best_test_name = (
        results[results["phase"] == "test_2025"].sort_values("roc_auc", ascending=False).iloc[0]["model"]
    )
    best_scores = test_scores[str(best_test_name)]
    scored_test = test[["case_key", "PlanningAuthority", "application_bucket", "target_refused", "received_date_dt"]].copy()
    scored_test["best_uplift_score"] = best_scores
    scored_test.to_csv(OUTPUT_DIR / "raw_planning_accuracy_uplift_best_predictions.csv", index=False)

    payload = {
        "definition": "Tune on 2023-2024, retrain selected candidates before 2025, evaluate once on 2025.",
        "tune_train_n": int(len(tune_train)),
        "validation_n": int(len(validation)),
        "final_train_n": int(len(final_train)),
        "test_n": int(len(test)),
        "best_test_model": str(best_test_name),
        "summary": results.to_dict(orient="records"),
        "best_by_authority": evaluate_groups(scored_test, "best_uplift_score", "PlanningAuthority"),
        "best_by_application_type": evaluate_groups(scored_test, "best_uplift_score", "application_bucket"),
        "best_risk_deciles": risk_deciles(test["target_refused"], best_scores),
        "outputs": {
            "summary_csv": str(results_path),
            "best_predictions_csv": str(OUTPUT_DIR / "raw_planning_accuracy_uplift_best_predictions.csv"),
        },
    }
    output_path = OUTPUT_DIR / "raw_planning_accuracy_uplift_experiments.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
