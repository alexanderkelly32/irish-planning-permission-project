#!/usr/bin/env python3
"""Time-safe comparable-case feature experiment.

For each application, retrieve text-similar prior residential applications in
the same broad application bucket, then add aggregate precedent-outcome signals
to the v2 model features. The target application never sees later cases.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.neighbors import NearestNeighbors

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
OUTPUT_DIR = ROOT / "05_policy" / "current"
COMPARABLE_FEATURES_PATH = OUTPUT_DIR / "raw_planning_comparable_features.parquet"
REFERENCE_LOOKBACK_YEARS = 8

sys.path.insert(0, str(SCRIPT_DIR))
from build_dublin_submission_model import bootstrap_metric_ci, calibration_intercept_slope  # noqa: E402
from build_national_residential_model_v2 import (  # noqa: E402
    TRAIN_CUTOFF as TEST_CUTOFF,
    V2_NUMERIC,
    build_scaled_pipeline,
    load_data_with_history,
)


COMPARABLE_NUMERIC = [
    "comp_top5_refusal_rate",
    "comp_top10_refusal_rate",
    "comp_top20_refusal_rate",
    "comp_top20_mean_similarity",
    "comp_top20_max_refused_similarity",
    "comp_top20_max_granted_similarity",
    "comp_top20_refused_similarity_gap",
    "comp_top20_same_authority_share",
    "comp_top20_same_authority_refusal_rate",
    "comp_top20_count",
]
V3_NUMERIC = V2_NUMERIC + COMPARABLE_NUMERIC
V3_FEATURES = ["PlanningAuthority", "application_bucket", "description_stripped"] + V3_NUMERIC


def metrics(y: pd.Series, proba: np.ndarray, *, include_ci: bool = False) -> dict[str, float | int]:
    clipped = np.clip(proba, 1e-6, 1 - 1e-6)
    out = {
        "n": int(len(y)),
        "refusal_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, proba)),
        "average_precision": float(average_precision_score(y, proba)),
        "brier": float(brier_score_loss(y, clipped)),
        "log_loss": float(log_loss(y, clipped, labels=[0, 1])),
    }
    out.update(calibration_intercept_slope(y, clipped))
    if include_ci:
        out.update(bootstrap_metric_ci(y, proba, n_boot=300))
    return out


def initialise_feature_frame(data: pd.DataFrame) -> pd.DataFrame:
    features = pd.DataFrame({"case_key": data["case_key"].to_numpy()})
    for column in COMPARABLE_NUMERIC:
        features[column] = np.nan
    features["comp_top20_count"] = 0.0
    return features


def summarise_neighbours(
    *,
    query_authority: np.ndarray,
    ref_authority: np.ndarray,
    ref_target: np.ndarray,
    distances: np.ndarray,
    neighbour_indices: np.ndarray,
) -> dict[str, np.ndarray]:
    sims = np.clip(1.0 - distances, 0.0, 1.0)
    out: dict[str, np.ndarray] = {}
    for k in [5, 10, 20]:
        kk = min(k, sims.shape[1])
        targets = ref_target[neighbour_indices[:, :kk]]
        out[f"comp_top{k}_refusal_rate"] = targets.mean(axis=1)
    kk = min(20, sims.shape[1])
    top_sims = sims[:, :kk]
    top_targets = ref_target[neighbour_indices[:, :kk]]
    top_authority = ref_authority[neighbour_indices[:, :kk]]
    same_authority = top_authority == query_authority[:, None]
    refused_sim = np.where(top_targets == 1, top_sims, np.nan)
    granted_sim = np.where(top_targets == 0, top_sims, np.nan)
    same_auth_targets = np.where(same_authority, top_targets, np.nan)
    out["comp_top20_mean_similarity"] = top_sims.mean(axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        out["comp_top20_max_refused_similarity"] = np.nanmax(refused_sim, axis=1)
        out["comp_top20_max_granted_similarity"] = np.nanmax(granted_sim, axis=1)
        out["comp_top20_same_authority_refusal_rate"] = np.nanmean(same_auth_targets, axis=1)
    out["comp_top20_refused_similarity_gap"] = out["comp_top20_max_refused_similarity"] - out["comp_top20_max_granted_similarity"]
    out["comp_top20_same_authority_share"] = same_authority.mean(axis=1)
    out["comp_top20_count"] = np.full(len(query_authority), float(kk))
    for key, values in out.items():
        out[key] = np.where(np.isfinite(values), values, np.nan)
    return out


def build_comparable_features(data: pd.DataFrame) -> pd.DataFrame:
    if COMPARABLE_FEATURES_PATH.exists():
        return pd.read_parquet(COMPARABLE_FEATURES_PATH)

    features = initialise_feature_frame(data)
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=80_000,
        min_df=2,
        sublinear_tf=True,
        strip_accents="unicode",
    )
    vectorizer.fit(data.loc[data["received_date_dt"] < TEST_CUTOFF, "description_stripped"].fillna("").astype(str))

    for bucket, bucket_frame in data.groupby("application_bucket", sort=False):
        bucket_frame = bucket_frame.sort_values(["received_date_dt", "case_key"]).copy()
        if len(bucket_frame) < 100:
            continue
        print(f"Comparable features: {bucket} ({len(bucket_frame)} rows)", flush=True)
        x_bucket = vectorizer.transform(bucket_frame["description_stripped"].fillna("").astype(str))
        years = bucket_frame["received_date_dt"].dt.year.to_numpy()
        targets = bucket_frame["target_refused"].to_numpy(dtype=int)
        authorities = bucket_frame["PlanningAuthority"].fillna("").astype(str).to_numpy()
        index_values = bucket_frame.index.to_numpy()
        for year in sorted(set(years)):
            ref_pos = np.flatnonzero((years < year) & (years >= year - REFERENCE_LOOKBACK_YEARS))
            query_pos = np.flatnonzero(years == year)
            if len(ref_pos) < 50 or len(query_pos) == 0:
                continue
            k = min(50, len(ref_pos))
            nn = NearestNeighbors(n_neighbors=k, metric="cosine", algorithm="brute", n_jobs=1)
            nn.fit(x_bucket[ref_pos])
            distances, local_indices = nn.kneighbors(x_bucket[query_pos], return_distance=True)
            neighbour_pos = ref_pos[local_indices]
            values = summarise_neighbours(
                query_authority=authorities[query_pos],
                ref_authority=authorities,
                ref_target=targets,
                distances=distances,
                neighbour_indices=neighbour_pos,
            )
            target_index = index_values[query_pos]
            for column, column_values in values.items():
                features.loc[target_index, column] = column_values

    features.to_parquet(COMPARABLE_FEATURES_PATH, index=False)
    return features


def fit_score(train: pd.DataFrame, test: pd.DataFrame, numeric: list[str]) -> tuple[dict[str, float | int], np.ndarray]:
    model = build_scaled_pipeline(numeric)
    features = ["PlanningAuthority", "application_bucket", "description_stripped"] + numeric
    model.fit(train[features], train["target_refused"])
    proba = model.predict_proba(test[features])[:, 1]
    return metrics(test["target_refused"], proba, include_ci=True), proba


def main() -> None:
    data = load_data_with_history().reset_index(drop=True)
    comparable = build_comparable_features(data)
    data = data.merge(comparable, on="case_key", how="left")
    train = data[data["received_date_dt"] < TEST_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TEST_CUTOFF].copy()

    v2_metrics, v2_proba = fit_score(train, test, V2_NUMERIC)
    v3_metrics, v3_proba = fit_score(train, test, V3_NUMERIC)
    results = {
        "definition": "Comparable-case features use text-similar earlier applications from the same residential bucket.",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "v2_reproduced": v2_metrics,
        "v3_comparable_features": v3_metrics,
        "delta_v3_minus_v2": {
            key: float(v3_metrics[key] - v2_metrics[key])
            for key in ["roc_auc", "average_precision", "brier", "log_loss"]
        },
        "comparable_features": COMPARABLE_NUMERIC,
    }
    scored = test[["case_key", "PlanningAuthority", "application_bucket", "target_refused", "received_date_dt"]].copy()
    scored["v2_score"] = v2_proba
    scored["v3_comparable_score"] = v3_proba
    scored.to_csv(OUTPUT_DIR / "raw_planning_comparable_feature_predictions.csv", index=False)
    (OUTPUT_DIR / "raw_planning_comparable_feature_experiment.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
