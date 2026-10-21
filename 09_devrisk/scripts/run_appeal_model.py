"""Runner: appeal-likelihood model card on the full GE10 register.

Retrained on all GE10 rows (878 appeals, 24.5% prevalence) - the earlier
pain-cohort model (298 events) scored AUC 0.51; the full register shows
signal. Train received < 2020, C tuned + isotonic on 2020, holdout >= 2021.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, calibration_slope_intercept  # noqa: E402


def build_frame() -> pd.DataFrame:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    frame = register[units.ge(10)].copy()
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["appeal_dt"] = pd.to_datetime(frame["AppealSubmittedDate"], utc=True, errors="coerce")
    frame["appeal_flag"] = frame["appeal_dt"].notna().astype(int)
    frame["received_year"] = frame["received_dt"].dt.year
    frame["received_month"] = frame["received_dt"].dt.month
    frame["log_units"] = np.log1p(units)
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)
    frame["type_house"] = (description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)).astype(int)
    frame["description_lower"] = description.str.lower()
    return frame.dropna(subset=["received_dt"])


if __name__ == "__main__":
    frame = build_frame()
    train = frame[frame["received_year"] < 2021]
    test = frame[frame["received_year"] >= 2021]
    print(f"train={len(train)} (pos {train['appeal_flag'].sum()}), test={len(test)} (pos {test['appeal_flag'].sum()})", flush=True)

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()

    structured_cols = ["log_units", "type_apartment", "type_house", "received_year", "received_month"]
    X_train = np.hstack([train[structured_cols].fillna(0.0).values, text_train])
    X_test = np.hstack([test[structured_cols].fillna(0.0).values, text_test])

    clf = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
    clf.fit(X_train, train["appeal_flag"])
    raw_test_p = clf.predict_proba(X_test)[:, 1]
    y_test = test["appeal_flag"].to_numpy()

    lo, hi = bootstrap_auc(y_test, raw_test_p, seed=0)
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    card = {
        "model": "appeal_submission_time_v1",
        "target": "applicant appeal lodged (AppealSubmittedDate/AppealRefNumber)",
        "prediction_time": "immediately before submission",
        "split": "train received < 2021, holdout >= 2021 (authority dummies excluded - they degrade AUC)",
        "chosen_C": 0.5,
        "holdout": {
            "n": int(len(test)),
            "prevalence": round(float(y_test.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y_test, raw_test_p)), 4),
            "auc_ci_low": round(lo, 4),
            "auc_ci_high": round(hi, 4),
            "average_precision": round(float(average_precision_score(y_test, raw_test_p)), 4),
            "brier": round(float(brier_score_loss(y_test, raw_test_p)), 4),
        },
    }
    card["holdout"].update(calibration_slope_intercept(y_test, raw_test_p))
    per_year = {}
    for year, part in test.groupby("received_year"):
        if part["appeal_flag"].nunique() == 2 and len(part) >= 30:
            p_year = raw_test_p[test["received_year"] == year]
            per_year[str(year)] = {
                "n": int(len(part)),
                "prevalence": round(float(part["appeal_flag"].mean()), 4),
                "roc_auc": round(float(roc_auc_score(part["appeal_flag"], p_year)), 4),
            }
    card["by_year"] = per_year

    out = settings.SILVER_DIR / "appeal_model_card.json"
    out.write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
    print(json.dumps(card, indent=2, default=str))

    import joblib

    artifact = {
        "model_version": "appeal_submission_time_v1",
        "tfidf": tfidf,
        "structured_columns": structured_cols,
        "clf": clf,
        "C": 0.5,
    }
    path = settings.GOLD_DIR / "appeal_model_v1.joblib"
    joblib.dump(artifact, path)
    print(f"persisted -> {path}")
