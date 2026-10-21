#!/usr/bin/env python3
"""Save the comparable-case reference pack for query-time scoring.

Reproduces the training-time comparable features exactly: TF-IDF (1,2) 80k
sublinear fitted on pre-2024 rows; per-bucket reference = all pre-2024 rows in
that bucket. A new (2026+) query can only ever reference pre-2024 rows, so the
reference is inherently time-safe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current" / "model_v4" / "comparable_reference.joblib"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402


def main() -> None:
    data, train, test, y = build_data()
    reference = train.sort_values(["received_date_dt", "case_key"]).copy()
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=80_000,
        min_df=2,
        sublinear_tf=True,
        strip_accents="unicode",
    )
    vectorizer.fit(reference["description_stripped"].fillna("").astype(str))
    buckets: dict[str, dict] = {}
    for bucket, frame in reference.groupby("application_bucket", sort=False):
        if len(frame) < 100:
            continue
        matrix = vectorizer.transform(frame["description_stripped"].fillna("").astype(str))
        buckets[str(bucket)] = {
            "authorities": frame["PlanningAuthority"].fillna("").astype(str).to_numpy(),
            "targets": frame["target_refused"].to_numpy(dtype=int),
            "years": frame["received_date_dt"].dt.year.to_numpy(),
            "matrix": matrix,
        }
    joblib.dump({"vectorizer": vectorizer, "buckets": buckets, "lookback_years": 8}, OUT)
    print("saved comparable_reference:", OUT, "| buckets:", list(buckets.keys()), flush=True)


if __name__ == "__main__":
    main()
