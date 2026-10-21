"""Runner: appeals split + FI label-maturity check (todo 7).

Appeals: applicant appeals (lodged after REFUSED) vs third-party appeals
(lodged after GRANT) are different processes; fit each separately on the
full GE10 register with the same protocol as appeal v1 (train received
<2021, holdout >=2021, logistic + structured + TF-IDF, no authority dummies).

FI: label maturity - FI rate by received year; if 2024-25 rates collapse
while 2021-22 were stable, recent FI dates may simply not be recorded yet
rather than genuinely falling.
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
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc  # noqa: E402
from run_appeal_model import build_frame  # noqa: E402

if __name__ == "__main__":
    frame = build_frame()
    frame["decision_refused"] = frame["Decision"].fillna("").astype(str).str.upper().str.contains("REFUS")
    frame["applicant_appeal"] = frame["appeal_flag"] & frame["decision_refused"]
    frame["third_party_appeal"] = frame["appeal_flag"] & ~frame["decision_refused"]
    train = frame[frame["received_year"] < 2021]
    test = frame[frame["received_year"] >= 2021]

    structured_cols = ["log_units", "type_apartment", "type_house", "received_year", "received_month"]
    report = {"prevalence": {
        "all_appeals_test": round(float(test["appeal_flag"].mean()), 4),
        "applicant_appeals_test": round(float(test["applicant_appeal"].mean()), 4),
        "third_party_appeals_test": round(float(test["third_party_appeal"].mean()), 4),
    }}

    for name, flag in (("applicant_appeal", "applicant_appeal"), ("third_party_appeal", "third_party_appeal")):
        y_train = train[flag].to_numpy()
        y_test = test[flag].to_numpy()
        if y_train.sum() < 30 or y_test.sum() < 10:
            report[name] = {"skipped": "too few events", "train_pos": int(y_train.sum()), "test_pos": int(y_test.sum())}
            continue
        tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
        text_train = tfidf.fit_transform(train["description_lower"]).toarray()
        text_test = tfidf.transform(test["description_lower"]).toarray()
        X_train = np.hstack([train[structured_cols].fillna(0.0).values, text_train])
        X_test = np.hstack([test[structured_cols].fillna(0.0).values, text_test])
        model = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        model.fit(X_train, y_train)
        p = model.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, p)
        lo, hi = bootstrap_auc(y_test, p, seed=0)
        report[name] = {
            "train_pos": int(y_train.sum()), "test_pos": int(y_test.sum()),
            "auc": round(float(auc), 4), "auc_ci95": [round(lo, 4), round(hi, 4)],
        }
        # Compare vs the combined v1 appeal model's discrimination on the same subset.
        if name == "applicant_appeal":
            subset = y_test.astype(bool)
            if test.loc[subset, "appeal_flag"].mean() > 0:
                pass

    # FI label maturity.
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    ge10 = register[units.ge(10)].copy()
    ge10["received_dt"] = pd.to_datetime(ge10["ReceivedDate"], utc=True, errors="coerce")
    ge10["fi_dt"] = pd.to_datetime(ge10[["FIRequestDate", "FIRecDate"]].min(axis=1), utc=True, errors="coerce")
    ge10["fi"] = ge10["fi_dt"].notna().astype(int)
    ge10["year"] = ge10["received_dt"].dt.year
    fi_by_year = ge10.groupby("year").agg(n=("fi", "size"), fi_rate=("fi", "mean"))
    report["fi_by_received_year"] = {str(y): {"n": int(row["n"]), "fi_rate": round(float(row["fi_rate"]), 4)}
                                     for y, row in fi_by_year.iterrows() if y >= 2016}
    # Decision-date maturity: rows whose decision is after 2024 may not have FI
    # fields populated yet even if FI happened - count recent rows without any
    # FI date but with a decision date.
    ge10["decision_dt"] = pd.to_datetime(ge10["DecisionDate"], utc=True, errors="coerce")
    recent = ge10[ge10["decision_dt"] >= pd.Timestamp("2024-01-01", tz="UTC")]
    report["fi_maturity_2024_25"] = {
        "rows": int(len(recent)),
        "with_decision_date": int(recent["decision_dt"].notna().sum()),
        "fi_rate_2024_25": round(float(recent["fi"].mean()), 4),
    }

    out = settings.SILVER_DIR / "appeal_split_fi_maturity.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
