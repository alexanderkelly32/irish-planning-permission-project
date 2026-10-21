"""Runner: appeal model v2 - history features + stronger learner.

v1: full GE10 register, logistic, structured+TF-IDF, AUC 0.659 (no history
features, no density). v2: adds time-safe authority/local prior appeal rates,
density/site features, and a GBM learner option; folds in the 4Dublin pipeline
appeal labels. Same split (train <2021, holdout >=2021) so comparison to v1 is
like-for-like. Writes appeal_model_v2_card.json + appeal_model_v2.joblib.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, calibration_slope_intercept, evaluate  # noqa: E402

RNG = 7


def build_frame() -> pd.DataFrame:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    v2 = pd.read_csv(settings.SILVER_DIR / "fi_appeal_labels_v2.csv")
    v2 = v2[["case_key", "appeal_submitted_v2"]]
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    frame = register[units.ge(10)].copy()
    frame = frame.merge(v2, on="case_key", how="left")
    frame["appeal_flag"] = frame["appeal_submitted_v2"].astype(int)
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["received_year"] = frame["received_dt"].dt.year
    frame["received_month"] = frame["received_dt"].dt.month
    frame["log_units"] = np.log1p(units.fillna(0))
    frame["site_area"] = pd.to_numeric(frame["AreaofSite"], errors="coerce")
    frame["log_site_area"] = np.log1p(frame["site_area"].fillna(0))
    frame["density"] = units / frame["site_area"] * 10000.0
    frame["density"] = frame["density"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    frame["units_missing"] = units.isna().astype(int)
    frame["site_missing"] = frame["site_area"].isna().astype(int)
    frame["covid_era"] = frame["received_year"].between(2020, 2021).astype(int)
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)
    frame["type_house"] = (description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)).astype(int)
    frame["description_lower"] = description.str.lower()
    return frame.dropna(subset=["received_dt"])


def add_appeal_history(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.sort_values("received_dt").reset_index(drop=True)
    easting = pd.to_numeric(data["ITMEasting"], errors="coerce").to_numpy()
    northing = pd.to_numeric(data["ITMNorthing"], errors="coerce").to_numpy()
    received = data["received_dt"].to_numpy()
    authority = data["PlanningAuthority"].astype(str).to_numpy()
    y_appeal = data["appeal_flag"].astype(int).to_numpy()
    auth_n = np.zeros(len(data))
    auth_rate = np.zeros(len(data))
    local_n = np.zeros(len(data))
    local_rate = np.zeros(len(data))
    for i in range(len(data)):
        prior = received < received[i]
        auth_mask = prior & (authority == authority[i])
        if auth_mask.any():
            auth_n[i] = auth_mask.sum()
            auth_rate[i] = y_appeal[auth_mask].mean()
        if not np.isnan(easting[i]) and not np.isnan(northing[i]):
            local_mask = prior & (np.hypot(easting - easting[i], northing - northing[i]) <= 5000.0)
            if local_mask.any():
                local_n[i] = local_mask.sum()
                local_rate[i] = y_appeal[local_mask].mean()
    data["auth_prior_n"] = np.log1p(auth_n)
    data["auth_prior_appeal_rate"] = auth_rate
    data["local_prior_n"] = np.log1p(local_n)
    data["local_prior_appeal_rate"] = local_rate
    return data


STRUCTURED = [
    "log_units", "log_site_area", "units_missing", "site_missing", "density",
    "received_year", "received_month", "covid_era", "type_apartment", "type_house",
    "auth_prior_n", "auth_prior_appeal_rate", "local_prior_n", "local_prior_appeal_rate",
]


if __name__ == "__main__":
    from sklearn.feature_extraction.text import TfidfVectorizer

    frame = add_appeal_history(build_frame())
    train = frame[frame["received_year"] < 2019]
    val = frame[frame["received_year"].isin([2019, 2020])]
    test = frame[frame["received_year"] >= 2021]
    print(f"train={len(train)} (pos {train['appeal_flag'].sum()}), val={len(val)}, test={len(test)} (pos {test['appeal_flag'].sum()})", flush=True)

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_val = tfidf.transform(val["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()

    X_train = np.hstack([train[STRUCTURED].fillna(0.0).values, text_train])
    X_val = np.hstack([val[STRUCTURED].fillna(0.0).values, text_val])
    X_test = np.hstack([test[STRUCTURED].fillna(0.0).values, text_test])
    y_train = train["appeal_flag"].to_numpy()
    y_val = val["appeal_flag"].to_numpy()
    y_test = test["appeal_flag"].to_numpy()

    candidates = {}
    for C in (0.1, 0.5, 1.0):
        clf = LogisticRegression(C=C, max_iter=2000, solver="liblinear")
        clf.fit(X_train, y_train)
        candidates[f"lr_C{C}"] = clf.predict_proba(X_val)[:, 1]
    for depth, lr in ((2, 0.05), (3, 0.05)):
        gbm = GradientBoostingClassifier(n_estimators=250, max_depth=depth, learning_rate=lr, subsample=0.8, min_samples_leaf=20, random_state=RNG)
        gbm.fit(X_train, y_train)
        candidates[f"gbm_d{depth}"] = gbm.predict_proba(X_val)[:, 1]

    best_name = max(candidates, key=lambda name: roc_auc_score(y_val, candidates[name]))
    print(f"best learner on val: {best_name} (auc {roc_auc_score(y_val, candidates[best_name]):.4f})", flush=True)

    if best_name.startswith("lr"):
        clf = LogisticRegression(C=float(best_name.split("C")[1]), max_iter=2000, solver="liblinear").fit(X_train, y_train)
    else:
        depth = int(best_name[-1])
        clf = GradientBoostingClassifier(n_estimators=250, max_depth=depth, learning_rate=0.05, subsample=0.8, min_samples_leaf=20, random_state=RNG).fit(X_train, y_train)
    raw_test_p = clf.predict_proba(X_test)[:, 1]

    card = {
        "model": "appeal_submission_time_v2",
        "target": "applicant appeal lodged (register + 4Dublin pipeline Appeal_Submitted)",
        "prediction_time": "immediately before submission",
        "split": "train received < 2019, learner tuned on 2019-2020, holdout >= 2021 (no authority dummies)",
        "learner": best_name,
        "validation_auc": round(float(roc_auc_score(y_val, candidates[best_name])), 4),
        "holdout": evaluate(y_test, raw_test_p),
        "note": "adds density/site/covid + time-safe authority/local prior appeal rates + GBM option over v1",
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

    (settings.SILVER_DIR / "appeal_model_v2_card.json").write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
    print(json.dumps(card, indent=2, default=str))

    import joblib

    artifact = {
        "model_version": "appeal_submission_time_v2",
        "learner_name": best_name,
        "tfidf": tfidf,
        "structured_columns": STRUCTURED,
        "clf": clf,
    }
    path = settings.GOLD_DIR / "appeal_model_v2.joblib"
    joblib.dump(artifact, path)
    print(f"persisted -> {path}")
