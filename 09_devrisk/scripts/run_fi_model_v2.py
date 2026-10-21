"""Runner: FI model v2 - full GE10 register + stronger learner.

v1 used the pain pool (~1.3k mature schemes, holdout n=363, AUC 0.688).
v2 trains on ALL GE10 register rows with FI labels (2,170 positives), adds
GradientBoosting as learner choice, and folds in the 4Dublin pipeline FI
labels. Same temporal split (train <2020, tune 2020, holdout >=2021).
Writes fi_model_v2_card.json + fi_model_v2.joblib - v1 artifacts untouched.
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
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, evaluate  # noqa: E402

RNG = 7
HOUSES_RE = r"\b(?:house|houses|dwelling|dwellings)\b"
APARTMENTS_RE = r"\b(?:apartment|apartments|duplex|apartment-led)\b"


def build_frame() -> pd.DataFrame:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    v2 = pd.read_csv(settings.SILVER_DIR / "fi_appeal_labels_v2.csv")
    v2 = v2[["case_key", "fi_requested_v2", "fi_source"]]
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    frame = register[units.ge(10)].copy()
    frame = frame.merge(v2, on="case_key", how="left")
    frame["fi_requested"] = frame["fi_requested_v2"].astype(int)
    frame["received_date_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["received_year"] = frame["received_date_dt"].dt.year
    frame["received_month"] = frame["received_date_dt"].dt.month
    frame["units"] = units
    frame["site_area"] = pd.to_numeric(frame["AreaofSite"], errors="coerce")
    frame["density"] = frame["units"] / frame["site_area"] * 10000.0
    frame["density"] = frame["density"].replace([np.inf, -np.inf], np.nan)
    frame["log_units"] = np.log1p(frame["units"].fillna(0))
    frame["log_site_area"] = np.log1p(frame["site_area"].fillna(0))
    frame["units_missing"] = frame["units"].isna().astype(int)
    frame["site_missing"] = frame["site_area"].isna().astype(int)
    frame["covid_era"] = frame["received_year"].between(2020, 2021).astype(int)
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_house"] = description.str.contains(HOUSES_RE, case=False, regex=True) & ~description.str.contains("apartment", case=False)
    frame["type_apartment"] = description.str.contains(APARTMENTS_RE, case=False, regex=True)
    frame["description_lower"] = description.str.lower()
    return frame.dropna(subset=["received_date_dt"])


def add_fi_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Time-safe authority + 5km-local prior FI rates from the register alone."""
    data = frame.sort_values("received_date_dt").reset_index(drop=True)
    easting = pd.to_numeric(data["ITMEasting"], errors="coerce").to_numpy()
    northing = pd.to_numeric(data["ITMNorthing"], errors="coerce").to_numpy()
    received = data["received_date_dt"].to_numpy()
    authority = data["PlanningAuthority"].astype(str).to_numpy()
    y_fi = data["fi_requested"].astype(int).to_numpy()
    auth_n = np.zeros(len(data))
    auth_rate = np.zeros(len(data))
    local_n = np.zeros(len(data))
    local_rate = np.zeros(len(data))
    for i in range(len(data)):
        prior = received < received[i]
        auth_mask = prior & (authority == authority[i])
        if auth_mask.any():
            auth_n[i] = auth_mask.sum()
            auth_rate[i] = y_fi[auth_mask].mean()
        if not np.isnan(easting[i]) and not np.isnan(northing[i]):
            local_mask = prior & (np.hypot(easting - easting[i], northing - northing[i]) <= 5000.0)
            if local_mask.any():
                local_n[i] = local_mask.sum()
                local_rate[i] = y_fi[local_mask].mean()
    data["auth_prior_n"] = np.log1p(auth_n)
    data["auth_prior_fi_rate"] = auth_rate
    data["local_prior_n"] = np.log1p(local_n)
    data["local_prior_fi_rate"] = local_rate
    return data


STRUCTURED = [
    "log_units", "log_site_area", "units_missing", "site_missing", "density",
    "received_year", "received_month", "covid_era", "type_house", "type_apartment",
    "auth_prior_n", "auth_prior_fi_rate", "local_prior_n", "local_prior_fi_rate",
]


if __name__ == "__main__":
    from sklearn.feature_extraction.text import TfidfVectorizer

    frame = add_fi_history(build_frame())
    train = frame[frame["received_year"] < 2020]
    val = frame[frame["received_year"] == 2020]
    test = frame[frame["received_year"] >= 2021]
    print(f"train={len(train)} (pos {train['fi_requested'].sum()}), val={len(val)}, test={len(test)} (pos {test['fi_requested'].sum()})", flush=True)

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=20000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"])
    text_val = tfidf.transform(val["description_lower"])
    text_test = tfidf.transform(test["description_lower"])

    X_train = np.hstack([train[STRUCTURED].fillna(0.0).astype(float).values, pd.DataFrame.sparse.from_spmatrix(text_train).sparse.to_dense().astype("float32").values])
    X_val = np.hstack([val[STRUCTURED].fillna(0.0).astype(float).values, pd.DataFrame.sparse.from_spmatrix(text_val).sparse.to_dense().astype("float32").values])
    X_test = np.hstack([test[STRUCTURED].fillna(0.0).astype(float).values, pd.DataFrame.sparse.from_spmatrix(text_test).sparse.to_dense().astype("float32").values])
    y_train = train["fi_requested"].to_numpy()
    y_val = val["fi_requested"].to_numpy()
    y_test = test["fi_requested"].to_numpy()

    candidates = {}
    for C in (0.05, 0.1, 0.5):
        clf = LogisticRegression(C=C, max_iter=2000, solver="liblinear")
        clf.fit(X_train, y_train)
        candidates[f"lr_C{C}"] = clf.predict_proba(X_val)[:, 1]
    for depth, lr in ((2, 0.05), (3, 0.05)):
        gbm = GradientBoostingClassifier(n_estimators=200, max_depth=depth, learning_rate=lr, subsample=0.8, min_samples_leaf=10, random_state=RNG)
        gbm.fit(X_train, y_train)
        candidates[f"gbm_d{depth}"] = gbm.predict_proba(X_val)[:, 1]

    best_name = max(candidates, key=lambda name: roc_auc_score(y_val, candidates[name]))
    print(f"best learner on val: {best_name} (auc {roc_auc_score(y_val, candidates[best_name]):.4f})", flush=True)

    if best_name.startswith("lr"):
        C = float(best_name.split("C")[1])
        clf = LogisticRegression(C=C, max_iter=2000, solver="liblinear")
        clf.fit(X_train, y_train)
        raw_test_p = clf.predict_proba(X_test)[:, 1]
        artifact_learner = {"name": best_name, "clf": clf}
    else:
        depth = int(best_name[-1])
        clf = GradientBoostingClassifier(n_estimators=200, max_depth=depth, learning_rate=0.05, subsample=0.8, min_samples_leaf=10, random_state=RNG)
        clf.fit(X_train, y_train)
        raw_test_p = clf.predict_proba(X_test)[:, 1]
        artifact_learner = {"name": best_name, "clf": clf}

    val_p = candidates[best_name]
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(val_p, y_val)
    test_p = np.clip(iso.predict(raw_test_p), 1e-6, 1 - 1e-6)

    card = {
        "model": "fi_requested_submission_time_v2",
        "target": "at least one formal FI request before decision (register + 4Dublin pipeline FI_Request)",
        "prediction_time": "immediately before submission",
        "cohort": "full GE10 register (v1 used the ~1.3k pain pool; holdout n=363)",
        "split": "train received < 2020, learner tuned on 2020, holdout >= 2021",
        "learner": best_name,
        "validation_auc": round(float(roc_auc_score(y_val, val_p)), 4),
        "holdout": evaluate(y_test, test_p),
        "raw_holdout_auc_before_calibration": round(float(roc_auc_score(y_test, raw_test_p)), 4),
    }
    lo, hi = bootstrap_auc(y_test, test_p, seed=0)
    card["holdout"]["auc_ci_low"] = round(lo, 4)
    card["holdout"]["auc_ci_high"] = round(hi, 4)

    reliability = pd.DataFrame({"y": y_test, "p": test_p})
    reliability["bin"] = pd.qcut(reliability["p"].rank(method="first"), q=10, labels=False)
    table = reliability.groupby("bin").agg(n=("y", "size"), mean_predicted=("p", "mean"), observed_rate=("y", "mean"))
    card["reliability_10_bins"] = [
        {"bin": int(idx), "n": int(row["n"]), "mean_predicted": round(float(row["mean_predicted"]), 4),
         "observed_rate": round(float(row["observed_rate"]), 4)}
        for idx, row in table.iterrows()
    ]

    test_scored = test.copy()
    test_scored["p_fi"] = test_p
    per_year = {}
    for year, part in test_scored.groupby("received_year"):
        if part["fi_requested"].nunique() == 2:
            per_year[str(year)] = evaluate(part["fi_requested"].to_numpy(), part["p_fi"].to_numpy())
    card["by_year"] = per_year

    (settings.SILVER_DIR / "fi_model_v2_card.json").write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
    print(json.dumps(card, indent=2, default=str))

    import joblib

    artifact = {
        "model_version": "fi_requested_submission_time_v2",
        "learner": artifact_learner,
        "tfidf": tfidf,
        "structured_columns": STRUCTURED,
        "iso": iso,
        "training_cutoff_exclusive": int(train["received_year"].max()) + 1,
        "calibration_year": 2020,
        "holdout": card["holdout"],
    }
    artifact_path = settings.GOLD_DIR / "fi_model_v2.joblib"
    joblib.dump(artifact, artifact_path)
    print(f"persisted -> {artifact_path}")
