#!/usr/bin/env python3
"""Compare known-council, unseen-council, and council-specific performance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from scipy.sparse import csr_matrix, hstack

from build_raw_planning_benchmarks import add_raw_features, metrics

ROOT = Path(__file__).resolve().parents[2]
RAW_DATA = ROOT / "old_original_attempt" / "first_attempt_messy" / "irish_planning_dataset_clean_model.parquet"
OUTPUT_DIR = ROOT / "05_policy" / "current"
FEATURES = ["received_year", "PlanningAuthority", "application_bucket", "description_stripped"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=RAW_DATA)
    parser.add_argument("--min-council-cases", type=int, default=100)
    parser.add_argument("--councils", nargs="*", help="Optional council names to benchmark")
    parser.add_argument("--common-start", default="2023-01-01")
    parser.add_argument("--common-end", default="2026-01-01")
    parser.add_argument("--matched-only", action="store_true")
    parser.add_argument("--leave-one-out-only", action="store_true")
    return parser.parse_args()


def build_matrix(data: pd.DataFrame):
    """Build the fixed cross-fold feature matrix once."""
    text = HashingVectorizer(stop_words="english", ngram_range=(1, 2), n_features=2**14, alternate_sign=False).transform(
        data["description_stripped"].fillna("").astype(str)
    )
    categories = pd.get_dummies(data[["PlanningAuthority", "application_bucket"]].fillna("missing").astype(str), dtype=float)
    year = pd.to_numeric(data["received_year"], errors="coerce").fillna(data["received_year"].median()).to_numpy(dtype=float)
    year = csr_matrix(((year - 2015.0) / 10.0).reshape(-1, 1))
    return hstack([text, csr_matrix(categories.to_numpy()), year], format="csr")


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, matrix) -> np.ndarray:
    # The linear-loss SGD fit is used only for fold speed.
    train_rows = train["_row_id"].to_numpy(dtype=int)
    test_rows = test["_row_id"].to_numpy(dtype=int)
    model = SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=30, tol=1e-3, class_weight="balanced", random_state=42)
    model.fit(matrix[train_rows], train["target_refused"])
    return model.predict_proba(matrix[test_rows])[:, 1]


def evaluate(label: str, train: pd.DataFrame, test: pd.DataFrame, matrix, extra: dict[str, object] | None = None) -> dict[str, object]:
    if len(train) < 100 or len(test) < 20 or train["target_refused"].nunique() < 2 or test["target_refused"].nunique() < 2:
        return {"model": label, "status": "skipped", "train_n": int(len(train)), "test_n": int(len(test)), **(extra or {})}
    proba = fit_predict(train, test, matrix)
    out = {"model": label, "status": "fit", "train_n": int(len(train)), "test_n": int(len(test)), **metrics(test["target_refused"], proba), **(extra or {})}
    return out


def main() -> None:
    args = parse_args()
    data = add_raw_features(pd.read_parquet(args.input))
    units = pd.to_numeric(data["NumResidentialUnits"], errors="coerce")
    residential_terms = r"\b(?:apartment|apartments|dwelling|dwellings|house|houses|residential|home|extension|retention|change of use|one-off|one off)\b"
    residential = units.gt(0) | data["OneOffHouse"].fillna("").astype(str).str.strip().str.lower().isin({"y", "yes", "one", "single house"})
    residential |= data["DevelopmentDescription"].fillna("").astype(str).str.contains(residential_terms, case=False, regex=True)
    data = data[residential & data["target_refused"].notna() & data["received_date_dt"].notna()].copy()
    data = data.drop_duplicates("case_key").sort_values(["received_date_dt", "case_key"])
    data = data.reset_index(drop=True)
    data["_row_id"] = np.arange(len(data))
    matrix = build_matrix(data)

    rows: list[dict[str, object]] = []
    eligible_councils = [c for c, group in data.groupby("PlanningAuthority") if len(group) >= args.min_council_cases and group["target_refused"].nunique() == 2]
    if args.councils:
        eligible_councils = [c for c in eligible_councils if c in set(args.councils)]

    if not args.matched_only:
        # Leave-one-council-out: the held-out council is absent from training.
        for council in eligible_councils:
            test = data[data["PlanningAuthority"] == council].copy()
            train = data[data["PlanningAuthority"] != council].copy()
            rows.append(evaluate("leave_one_council_out", train, test, matrix, {"council": council, "test_refusal_rate": float(test["target_refused"].mean())}))

    if not args.matched_only and not args.leave_one_out_only:
        # Council-specific: chronological 80/20 split within each council.
        for council in eligible_councils:
            group = data[data["PlanningAuthority"] == council].sort_values("received_date_dt")
            split = max(1, int(len(group) * 0.8))
            train, test = group.iloc[:split].copy(), group.iloc[split:].copy()
            rows.append(evaluate("council_specific", train, test, matrix, {"council": council, "test_refusal_rate": float(test["target_refused"].mean()), "test_start": str(test["received_date_dt"].min())}))

    # Matched future window: all three regimes predict the same council cases
    # in the same period, removing the per-council time confound.
    common_start = pd.Timestamp(args.common_start, tz="UTC")
    common_end = pd.Timestamp(args.common_end, tz="UTC")
    if not args.leave_one_out_only:
      for council in eligible_councils:
          council_cases = data[data["PlanningAuthority"] == council]
          test = council_cases[(council_cases["received_date_dt"] >= common_start) & (council_cases["received_date_dt"] < common_end)].copy()
          historical = data[data["received_date_dt"] < common_start].copy()
          known_train = historical.copy()
          unseen_train = historical[historical["PlanningAuthority"] != council].copy()
          local_train = historical[historical["PlanningAuthority"] == council].copy()
          extra = {"council": council, "test_refusal_rate": float(test["target_refused"].mean()) if len(test) else np.nan, "test_start": str(common_start), "test_end": str(common_end)}
          rows.append(evaluate("matched_known_council", known_train, test, matrix, extra))
          rows.append(evaluate("matched_unseen_council", unseen_train, test, matrix, extra))
          rows.append(evaluate("matched_council_specific", local_train, test, matrix, extra))

    out = pd.DataFrame(rows)
    output_stem = "raw_planning_matched_2023_2026" if args.matched_only else "raw_planning_council_generalisation"
    out.to_csv(OUTPUT_DIR / f"{output_stem}.csv", index=False)
    summary = {
        "source": str(args.input),
        "eligible_n": int(len(data)),
        "eligible_councils": eligible_councils,
        "min_council_cases": args.min_council_cases,
        "representation": "fixed HashingVectorizer 16,384 features + logistic-loss SGD for cross-council folds",
        "matched_period": [args.common_start, args.common_end],
        "results_path": str(OUTPUT_DIR / f"{output_stem}.csv"),
        "results": rows,
    }
    (OUTPUT_DIR / f"{output_stem}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
