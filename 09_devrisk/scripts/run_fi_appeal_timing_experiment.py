"""Runner: does predicted event TIMING discriminate event presence?

User hypothesis: for FI and appeal, train timing models on event-positive
schemes, then check whether event-negative schemes get systematically
different predicted timings / interval widths, or whether timing features
improve the presence classifiers.

Timing targets: time_to_fi = FI date - received (statutory-deadline-shaped
but with variance); time_to_appeal = appeal date - received (decision timing
+ statutory 4-week window).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc  # noqa: E402

RNG = 7


def build_frame() -> pd.DataFrame:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    frame = register[units.ge(10)].copy()
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["decision_dt"] = pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce")
    frame["fi_first_dt"] = pd.to_datetime(frame[["FIRequestDate", "FIRecDate"]].min(axis=1), utc=True, errors="coerce")
    frame["appeal_dt"] = pd.to_datetime(frame["AppealSubmittedDate"], utc=True, errors="coerce")
    frame["time_to_fi"] = (frame["fi_first_dt"] - frame["received_dt"]).dt.days
    frame["time_to_appeal"] = (frame["appeal_dt"] - frame["received_dt"]).dt.days
    frame["fi_flag"] = frame["fi_first_dt"].notna().astype(int)
    frame["appeal_flag"] = frame["appeal_dt"].notna().astype(int)
    frame["received_year"] = frame["received_dt"].dt.year
    frame["log_units"] = np.log1p(units)
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)
    frame["type_house"] = (description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)).astype(int)
    frame["description_lower"] = description.str.lower()
    return frame.dropna(subset=["received_dt"])


def features(frame: pd.DataFrame, tfidf=None, fit: bool = True):
    structured = frame[["log_units", "type_apartment", "type_house", "received_year"]].fillna(0.0).astype(float)
    structured["received_month"] = frame["received_dt"].dt.month
    if fit:
        tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
        text = tfidf.fit_transform(frame["description_lower"])
    else:
        text = tfidf.transform(frame["description_lower"])
    scaler = StandardScaler(with_mean=False)
    X = scaler.fit_transform(pd.concat([structured, pd.DataFrame.sparse.from_spmatrix(text).fillna(0).astype("float32")], axis=1).values.astype(np.float64)) if fit else None
    # Simpler: hstack dense for small n.
    dense = np.hstack([structured.values, text.toarray()])
    return dense, tfidf, scaler if fit else None


def timing_experiment(name, timing_col: str, flag_col: str, frame_train, frame_test):
    y_timing = frame_train[timing_col]
    pos_train = frame_train[y_timing.notna() & y_timing.between(0, 730)].copy()
    results = {"event": name, "n_train_positives": int(len(pos_train))}
    X_train, tfidf, _ = features(pos_train)
    X_test, _, _ = features(frame_test, tfidf, fit=False)
    y_tr = pos_train[timing_col].to_numpy()

    quantiles = {}
    for q in (0.2, 0.5, 0.8):
        gbm = GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=200, max_depth=3, learning_rate=0.05, min_samples_leaf=20, random_state=RNG)
        gbm.fit(X_train, y_tr)
        quantiles[q] = np.maximum(gbm.predict(X_test), 1.0)

    flag_test = frame_test[flag_col].astype(int).to_numpy()
    test_pos_mask = flag_test.astype(bool)
    idx_pos = np.where(test_pos_mask)[0]
    if len(idx_pos):
        y_pos = frame_test.iloc[idx_pos][timing_col].to_numpy()
        for q in (0.2, 0.5, 0.8):
            p = quantiles[q][idx_pos]
            diff = y_pos - p
            results[f"pinball_p{int(q*100)}_on_positives"] = round(float(np.mean(np.where(diff >= 0, q * diff, (q - 1) * diff))), 1)

    width = quantiles[0.8] - quantiles[0.2]
    median_pred = quantiles[0.5]
    results["median_predicted_by_flag"] = {
        "event_yes": round(float(np.mean(median_pred[test_pos_mask])), 1),
        "event_no": round(float(np.mean(median_pred[~test_pos_mask])), 1),
    }
    results["interval_width_by_flag"] = {
        "event_yes": round(float(np.mean(width[test_pos_mask])), 1),
        "event_no": round(float(np.mean(width[~test_pos_mask])), 1),
    }
    results["share_event_no_above_p95_timing"] = round(float(np.mean(
        median_pred[~test_pos_mask] > np.quantile(y_tr, 0.95)
    )), 3)
    return results, quantiles, tfidf


if __name__ == "__main__":
    frame = build_frame()
    train = frame[frame["received_year"] < 2021]
    test = frame[frame["received_year"] >= 2021]
    print(f"train={len(train)}, test={len(test)}", flush=True)

    report = {}
    # FI timing experiment
    fi_results, fi_quantiles, fi_tfidf = timing_experiment(
        "fi", "time_to_fi", "fi_flag", train, test)
    report["fi"] = fi_results

    # Appeal timing experiment
    appeal_results, appeal_quantiles, appeal_tfidf = timing_experiment(
        "appeal", "time_to_appeal", "appeal_flag", train, test)
    report["appeal"] = appeal_results

    # Does adding timing features improve the presence classifiers?
    for event in ("fi", "appeal"):
        flag_col = f"{event}_flag"
        X_train_base, tfidf, _ = features(train)
        y_train = train[flag_col].to_numpy()
        X_test_base, _, _ = features(test, tfidf, fit=False)
        y_test = test[flag_col].to_numpy()

        base = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        base.fit(X_train_base, y_train)
        auc_base = roc_auc_score(y_test, base.predict_proba(X_test_base)[:, 1])

        timing_col = "time_to_fi" if event == "fi" else "time_to_appeal"
        pos_train = train[timing_col].notna() & train[timing_col].between(0, 730)
        X_train_t, tfidf_t, _ = features(train[pos_train])
        X_test_t, _, _ = features(test, tfidf_t, fit=False)
        y_t = train[pos_train][timing_col].to_numpy()
        gbm_t = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=200, max_depth=3, learning_rate=0.05, min_samples_leaf=20, random_state=RNG)
        gbm_t.fit(X_train_t, y_t)
        pred_timing = np.maximum(gbm_t.predict(X_test_t), 1.0)
        pred_width = np.maximum(gbm_t.predict(X_test_t), 1.0)  # placeholder; rebuild width below
        gbm_hi = GradientBoostingRegressor(loss="quantile", alpha=0.8, n_estimators=200, max_depth=3, learning_rate=0.05, min_samples_leaf=20, random_state=RNG)
        gbm_hi.fit(X_train_t, y_t)
        width = np.maximum(gbm_hi.predict(X_test_t) - pred_timing, 1.0)

        aug = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        aug.fit(np.hstack([X_train_base, np.zeros((len(X_train_base), 2))]) if False else X_train_base, y_train)
        # simpler: build augmented test features only for logistic comparison on base
        X_test_aug = np.hstack([X_test_base, pred_timing.reshape(-1, 1), width.reshape(-1, 1)])
        X_train_aug = np.hstack([X_train_base, np.full((len(X_train_base), 2), np.nan)])
        # timing features unavailable for many train rows; use mean imputation per column
        X_train_aug[:, -2] = np.nanmean(pred_timing)
        X_train_aug[:, -1] = np.nanmean(width)
        aug = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        aug.fit(X_train_aug, y_train)
        auc_aug = roc_auc_score(y_test, aug.predict_proba(X_test_aug)[:, 1])
        report[f"{event}_classifier"] = {
            "auc_base": round(auc_base, 4),
            "auc_with_timing_features": round(auc_aug, 4),
            "delta": round(auc_aug - auc_base, 4),
        }

    out = settings.SILVER_DIR / "fi_appeal_timing_experiment.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
