"""Runner: stacking-lite - use predicted FI as a feature for the other targets.

Lighter alternative to the shared trunk: out-of-fold FI predictions (from the
single-task model) added as a feature to appeal/refusal/duration models.
Tests whether correlated common targets transfer signal without a shared
representation (small-n friendly).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression, Ridge  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402

from devrisk import settings  # noqa: E402
from scripts.run_multitask_experiment import build_frame  # noqa: E402

RNG = 7
np.random.seed(RNG)


if __name__ == "__main__":
    from run_multitask_experiment import build_frame as bf

    frame = bf()
    frame["refusal"] = frame["Decision"].fillna("").astype(str).str.upper().str.contains("REFUS").astype(int)
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    register["fi_dt"] = pd.to_datetime(register[["FIRequestDate", "FIRecDate"]].min(axis=1), utc=True, errors="coerce")
    frame = frame.merge(register[["case_key", "fi_dt"]], on="case_key", how="left")
    frame["fi_flag"] = frame["fi_dt"].notna().astype(int)
    frame = frame.dropna(subset=["received_dt"])
    frame["log_duration"] = np.log1p((pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce") - frame["received_dt"]).dt.days.clip(lower=1))
    frame = frame.dropna(subset=["log_duration"])

    train = frame[frame["received_year"] < 2021].reset_index(drop=True)
    test = frame[frame["received_year"] >= 2021].reset_index(drop=True)

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    structured_cols = ["log_units", "type_apartment", "type_house", "received_year", "received_month"]

    def features(part: pd.DataFrame, text: np.ndarray, auth_columns) -> np.ndarray:
        auth = pd.get_dummies(part["PlanningAuthority"]).reindex(columns=auth_columns, fill_value=0).values
        return np.hstack([part[structured_cols].fillna(0.0).values, auth, text]).astype(np.float32)

    auth_columns = pd.get_dummies(train["PlanningAuthority"]).columns
    X_train = features(train, text_train, auth_columns)
    X_test = features(test, text_test, auth_columns)

    # Out-of-fold FI predictions for train; full-train model for test.
    fi_oof = np.zeros(len(train))
    skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=RNG)
    for tr_idx, va_idx in skf.split(X_train, train["fi_flag"]):
        clf = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        clf.fit(X_train[tr_idx], train["fi_flag"].iloc[tr_idx])
        fi_oof[va_idx] = clf.predict_proba(X_train[va_idx])[:, 1]
    clf_full = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
    clf_full.fit(X_train, train["fi_flag"])
    fi_test = clf_full.predict_proba(X_test)[:, 1]

    X_train_aug = np.hstack([X_train, fi_oof.reshape(-1, 1)])
    X_test_aug = np.hstack([X_test, fi_test.reshape(-1, 1)])

    report = {}
    for name, key in (("refusal", "refusal"), ("appeal", "appeal_flag")):
        base = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear").fit(X_train, train[key])
        aug = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear").fit(X_train_aug, train[key])
        report[f"{name}_base"] = round(roc_auc_score(test[key], base.predict_proba(X_test)[:, 1]), 4)
        report[f"{name}_with_fi_score"] = round(roc_auc_score(test[key], aug.predict_proba(X_test_aug)[:, 1]), 4)

    base = Ridge(alpha=1.0).fit(X_train, train["log_duration"])
    aug = Ridge(alpha=1.0).fit(X_train_aug, train["log_duration"])
    y_dur = np.expm1(test["log_duration"].to_numpy())
    report["duration_base_mae"] = round(float(np.mean(np.abs(y_dur - np.expm1(base.predict(X_test))))), 1)
    report["duration_with_fi_mae"] = round(float(np.mean(np.abs(y_dur - np.expm1(aug.predict(X_test_aug))))), 1)

    out = settings.SILVER_DIR / "stacking_lite_fi.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
