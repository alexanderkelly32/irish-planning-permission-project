#!/usr/bin/env python3
"""Test submission-time historical/spatial features on the national model.

No external downloads are required. Features are derived only from prior
planning-register records, so they are available at submission time:

- recent national and authority refusal environments
- prior applications/refusals on the same SiteId
- prior applications/refusals within 1km and 3km in the same authority
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.neighbors import KDTree
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
OUTPUT_DIR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(SCRIPT_DIR))
from build_dublin_submission_model import (  # noqa: E402
    bootstrap_metric_ci,
    build_simple_pipeline,
    calibration_intercept_slope,
)
from build_prospective_calibration_backtest import FEATURES, prepare  # noqa: E402


TEST_CUTOFF = pd.Timestamp("2025-01-01", tz="UTC")
RAW_HISTORY_NUMERIC = [
    "received_year",
    "national_prior_24m_count",
    "national_prior_24m_refusal_rate",
    "authority_prior_12m_count",
    "authority_prior_12m_refusal_rate",
    "authority_prior_24m_count",
    "authority_prior_24m_refusal_rate",
    "same_site_prior_count",
    "same_site_prior_refusal_rate",
    "nearby_1km_prior_24m_count",
    "nearby_1km_prior_24m_refusal_rate",
    "nearby_3km_prior_24m_count",
    "nearby_3km_prior_24m_refusal_rate",
]
BASE_NUMERIC = ["received_year"]
CATEGORICAL = ["PlanningAuthority", "application_bucket"]


def _date_days(series: pd.Series) -> np.ndarray:
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    return (series - epoch).dt.days.to_numpy(dtype=np.int64)


def add_prior_window_features(
    df: pd.DataFrame,
    *,
    group_col: str | None,
    prefix: str,
    windows_days: list[int],
) -> pd.DataFrame:
    out = df.copy()
    for window in windows_days:
        out[f"{prefix}_prior_{window // 30}m_count"] = 0.0
        out[f"{prefix}_prior_{window // 30}m_refusal_rate"] = np.nan

    groups = [(None, out)] if group_col is None else out.groupby(group_col, sort=False)
    for _, group in groups:
        idx = group.index.to_numpy()
        dates = _date_days(group["received_date_dt"])
        y = group["target_refused"].to_numpy(dtype=float)
        order = np.argsort(dates, kind="mergesort")
        sorted_idx = idx[order]
        sorted_dates = dates[order]
        sorted_y = y[order]
        cumulative_refusals = np.concatenate([[0.0], np.cumsum(sorted_y)])
        for window in windows_days:
            right = np.searchsorted(sorted_dates, sorted_dates, side="left")
            left = np.searchsorted(sorted_dates, sorted_dates - window, side="left")
            counts = right - left
            refusals = cumulative_refusals[right] - cumulative_refusals[left]
            rates = np.divide(refusals, counts, out=np.full_like(refusals, np.nan, dtype=float), where=counts > 0)
            out.loc[sorted_idx, f"{prefix}_prior_{window // 30}m_count"] = counts.astype(float)
            out.loc[sorted_idx, f"{prefix}_prior_{window // 30}m_refusal_rate"] = rates
    return out


def add_same_site_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["same_site_prior_count"] = 0.0
    out["same_site_prior_refusal_rate"] = np.nan
    if "SiteId" not in out.columns:
        return out
    valid = out["SiteId"].notna() & out["SiteId"].astype(str).str.strip().ne("")
    for _, group in out[valid].groupby("SiteId", sort=False):
        idx = group.index.to_numpy()
        dates = _date_days(group["received_date_dt"])
        y = group["target_refused"].to_numpy(dtype=float)
        order = np.argsort(dates, kind="mergesort")
        sorted_idx = idx[order]
        sorted_dates = dates[order]
        sorted_y = y[order]
        prior_count = np.searchsorted(sorted_dates, sorted_dates, side="left").astype(float)
        prior_refusals = np.concatenate([[0.0], np.cumsum(sorted_y)])[prior_count.astype(int)]
        prior_rate = np.divide(
            prior_refusals,
            prior_count,
            out=np.full_like(prior_refusals, np.nan, dtype=float),
            where=prior_count > 0,
        )
        out.loc[sorted_idx, "same_site_prior_count"] = prior_count
        out.loc[sorted_idx, "same_site_prior_refusal_rate"] = prior_rate
    return out


def add_nearby_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    radii = [1000.0, 3000.0]
    for radius in radii:
        km = int(radius // 1000)
        out[f"nearby_{km}km_prior_24m_count"] = 0.0
        out[f"nearby_{km}km_prior_24m_refusal_rate"] = np.nan

    for authority, group in out.groupby("PlanningAuthority", sort=False):
        coords = group[["ITMEasting", "ITMNorthing"]].to_numpy(dtype=float)
        if len(group) < 2 or not np.isfinite(coords).all():
            continue
        idx = group.index.to_numpy()
        dates = _date_days(group["received_date_dt"])
        y = group["target_refused"].to_numpy(dtype=float)
        tree = KDTree(coords, metric="euclidean")
        print(f"Spatial history: {authority} ({len(group)} rows)", flush=True)
        for radius in radii:
            km = int(radius // 1000)
            counts = np.zeros(len(group), dtype=float)
            refusals = np.zeros(len(group), dtype=float)
            neighbours = tree.query_radius(coords, r=radius, return_distance=False)
            for i, neighbour_idx in enumerate(neighbours):
                prior = neighbour_idx[(dates[neighbour_idx] < dates[i]) & (dates[neighbour_idx] >= dates[i] - 730)]
                counts[i] = len(prior)
                refusals[i] = y[prior].sum() if len(prior) else 0.0
            rates = np.divide(refusals, counts, out=np.full_like(refusals, np.nan, dtype=float), where=counts > 0)
            out.loc[idx, f"nearby_{km}km_prior_24m_count"] = counts
            out.loc[idx, f"nearby_{km}km_prior_24m_refusal_rate"] = rates
    return out


def add_history_features(data: pd.DataFrame) -> pd.DataFrame:
    out = data.sort_values(["received_date_dt", "case_key"]).copy()
    out = add_prior_window_features(out, group_col=None, prefix="national", windows_days=[730])
    out = add_prior_window_features(out, group_col="PlanningAuthority", prefix="authority", windows_days=[365, 730])
    out = add_same_site_features(out)
    out = add_nearby_features(out)
    return out


def metrics(y: pd.Series, proba: np.ndarray, *, include_ci: bool = False) -> dict[str, float | int]:
    out = {
        "n": int(len(y)),
        "refusal_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, proba)),
        "average_precision": float(average_precision_score(y, proba)),
        "brier": float(brier_score_loss(y, np.clip(proba, 1e-6, 1 - 1e-6))),
        "log_loss": float(log_loss(y, np.clip(proba, 1e-6, 1 - 1e-6), labels=[0, 1])),
    }
    out.update(calibration_intercept_slope(y, proba))
    if include_ci:
        out.update(bootstrap_metric_ci(y, proba, n_boot=300))
    return out


def build_scaled_pipeline(numeric: list[str]) -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
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
            (
                "txt",
                TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=50000, min_df=2),
                "description_stripped",
            ),
        ],
        sparse_threshold=1.0,
    )
    model = LogisticRegression(max_iter=3000, class_weight="balanced", C=0.5, solver="liblinear")
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def fit_score(train: pd.DataFrame, test: pd.DataFrame, numeric: list[str]) -> tuple[dict[str, float | int], np.ndarray]:
    model = build_scaled_pipeline(numeric)
    features = ["PlanningAuthority", "application_bucket", "description_stripped"] + numeric
    model.fit(train[features], train["target_refused"])
    proba = model.predict_proba(test[features])[:, 1]
    return metrics(test["target_refused"], proba, include_ci=True), proba


def main() -> None:
    data = prepare()
    data = add_history_features(data)
    count_cols = [column for column in RAW_HISTORY_NUMERIC if column.endswith("_count")]
    rate_cols = [column for column in RAW_HISTORY_NUMERIC if column.endswith("_refusal_rate")]
    for column in count_cols:
        data[f"log_{column}"] = np.log1p(pd.to_numeric(data[column], errors="coerce").fillna(0))
    log_count_cols = [f"log_{column}" for column in count_cols]
    train = data[data["received_date_dt"] < TEST_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TEST_CUTOFF].copy()

    results: dict[str, object] = {
        "definition": "Pre-2025 training, 2025 prospective-style test; history features use only applications received earlier than the scored case.",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "models": {},
    }
    model_specs = {
        "scaled_baseline_text_authority_type_year": BASE_NUMERIC,
        "scaled_history_rates_only_plus_text": BASE_NUMERIC + rate_cols,
        "scaled_history_log_counts_only_plus_text": BASE_NUMERIC + log_count_cols,
        "scaled_history_log_counts_and_rates_plus_text": BASE_NUMERIC + log_count_cols + rate_cols,
    }
    scores: dict[str, np.ndarray] = {}
    for name, numeric in model_specs.items():
        model_metrics, model_proba = fit_score(train, test, numeric)
        results["models"][name] = model_metrics
        scores[name] = model_proba
    baseline_metrics = results["models"]["scaled_baseline_text_authority_type_year"]
    best_name = max(results["models"], key=lambda name: results["models"][name]["roc_auc"])
    best_metrics = results["models"][best_name]
    results["best_model"] = best_name
    results["delta_best_minus_baseline"] = {
        key: float(best_metrics[key] - baseline_metrics[key])
        for key in ["roc_auc", "average_precision", "brier", "log_loss"]
    }

    feature_frame = data[["case_key"] + RAW_HISTORY_NUMERIC + log_count_cols].copy()
    feature_frame.to_parquet(OUTPUT_DIR / "raw_planning_history_features.parquet", index=False)
    scored = test[["case_key", "PlanningAuthority", "application_bucket", "target_refused", "received_date_dt"]].copy()
    for name, proba in scores.items():
        scored[name] = proba
    scored.to_csv(OUTPUT_DIR / "raw_planning_history_feature_predictions.csv", index=False)
    out_path = OUTPUT_DIR / "raw_planning_history_feature_experiment.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
