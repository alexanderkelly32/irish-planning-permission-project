"""Runner: where does pain signal live? (component models + time-safe history)

For each pain_v1 component (FI, appeal, slow activation, no-completion, slow
completion) and the composite, fit submission-time models with:
  - structured features (units, site, density, type, year, covid era);
  - description TF-IDF (vocab fit on train only);
  - time-safe history features: for the same authority and within 5 km, rates
    computed ONLY from applications received earlier than the target row
    (prior FI rate, prior appeal rate, prior pain rate, prior counts).

Same temporal split as run_pain_model.py. Reports a comparison table; honest
about small n and regime drift.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.sparse import hstack as sparse_hstack  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, load_cohort  # noqa: E402

COMPONENTS = [
    "fi_requested",
    "appeal_submitted",
    "slow_activation_24m",
    "no_completion_matured",
    "slow_completion_36m",
    "slow_exit_24m",
    "pain_high_binary",
]


def add_history_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Time-safe authority and 5km-local history features."""
    data = frame.sort_values("received_date_dt").reset_index(drop=True)
    easting = pd.to_numeric(data["ITMEasting"], errors="coerce").to_numpy()
    northing = pd.to_numeric(data["ITMNorthing"], errors="coerce").to_numpy()
    received = data["received_date_dt"].to_numpy()
    authority = data["PlanningAuthority"].astype(str).to_numpy()
    y_fi = data["fi_requested"].astype(int).to_numpy()
    y_appeal = data["appeal_submitted"].astype(int).to_numpy()
    y_pain = data["pain_high_binary"].astype(int).to_numpy()

    features = {
        "auth_prior_n": np.zeros(len(data)),
        "auth_prior_fi_rate": np.zeros(len(data)),
        "auth_prior_appeal_rate": np.zeros(len(data)),
        "auth_prior_pain_rate": np.zeros(len(data)),
        "local_prior_n": np.zeros(len(data)),
        "local_prior_fi_rate": np.zeros(len(data)),
        "local_prior_pain_rate": np.zeros(len(data)),
    }
    for i in range(len(data)):
        prior = received < received[i]
        same_auth = authority == authority[i]
        auth_mask = prior & same_auth
        auth_n = int(auth_mask.sum())
        features["auth_prior_n"][i] = auth_n
        if auth_n:
            features["auth_prior_fi_rate"][i] = y_fi[auth_mask].mean()
            features["auth_prior_appeal_rate"][i] = y_appeal[auth_mask].mean()
            features["auth_prior_pain_rate"][i] = y_pain[auth_mask].mean()
        if not np.isnan(easting[i]) and not np.isnan(northing[i]):
            dist = np.hypot(easting - easting[i], northing - northing[i])
            local_mask = prior & (dist <= 5000.0)
            local_n = int(local_mask.sum())
            features["local_prior_n"][i] = local_n
            if local_n:
                features["local_prior_fi_rate"][i] = y_fi[local_mask].mean()
                features["local_prior_pain_rate"][i] = y_pain[local_mask].mean()
    for name, values in features.items():
        data[name] = values
    return data


def build_matrix(frame: pd.DataFrame, tfidf: TfidfVectorizer | None = None):
    structured = frame[
        [
            "log_units", "log_site_area", "units_missing", "site_missing", "density",
            "received_year", "covid_era", "type_house", "type_apartment",
            "auth_prior_n", "auth_prior_fi_rate", "auth_prior_appeal_rate",
            "auth_prior_pain_rate", "local_prior_n", "local_prior_fi_rate",
            "local_prior_pain_rate",
        ]
    ].fillna(0.0).astype(float)
    structured = structured.copy()
    structured["auth_prior_n"] = np.log1p(structured["auth_prior_n"])
    structured["local_prior_n"] = np.log1p(structured["local_prior_n"])
    fresh = tfidf is None
    tfidf = tfidf or TfidfVectorizer(ngram_range=(1, 2), max_features=20000, sublinear_tf=True, stop_words="english", min_df=3)
    text = tfidf.fit_transform(frame["description_lower"]) if fresh else tfidf.transform(frame["description_lower"])
    return sparse_hstack([structured.to_numpy(), text]).tocsr(), tfidf, list(structured.columns)


def fit_predict(train_matrix, y: np.ndarray, test_matrix, C: float) -> np.ndarray:
    scaler = StandardScaler(with_mean=False)
    X_train = scaler.fit_transform(train_matrix)
    X_test = scaler.transform(test_matrix)
    model = LogisticRegression(C=C, max_iter=2000, solver="liblinear")
    model.fit(X_train, y)
    return model.predict_proba(X_test)[:, 1]


if __name__ == "__main__":
    frame = load_cohort()
    frame = add_history_features(frame)

    train = frame[frame["received_year"] < 2020]
    test = frame[frame["received_year"] >= 2021]
    print(f"train={len(train)}, test={len(test)}", flush=True)

    train_matrix, tfidf, structured_cols = build_matrix(train)
    test_matrix, _, _ = build_matrix(test, tfidf)

    history_idx = [i for i, col in enumerate(structured_cols) if col.startswith(("auth_prior", "local_prior"))]
    structured_idx = list(range(len(structured_cols)))
    no_history_idx = [i for i in structured_idx if i not in history_idx]
    all_idx = list(range(train_matrix.shape[1]))
    all_no_history_idx = [i for i in all_idx if i not in history_idx]

    results = {}
    for component in COMPONENTS:
        y_train = pd.to_numeric(train[component], errors="coerce").to_numpy()
        y_test = pd.to_numeric(test[component], errors="coerce").to_numpy()
        train_mask = ~np.isnan(y_train)
        test_mask = ~np.isnan(y_test)
        y_train = y_train[train_mask]
        y_test = y_test[test_mask]
        if train_mask.sum() < 20 or y_train.sum() < 20:
            results[component] = {"status": "skipped_train_too_few_positives",
                                  "train_n_defined": int(train_mask.sum()),
                                  "test_n_defined": int(test_mask.sum())}
            continue
        p = fit_predict(train_matrix[train_mask], y_train, test_matrix[test_mask], C=0.5)
        p_clipped = np.clip(p, 1e-6, 1 - 1e-6)
        lo, hi = bootstrap_auc(y_test, p, seed=0)
        results[component] = {
            "train_prevalence": round(float(y_train.mean()), 4),
            "train_n_defined": int(len(y_train)),
            "test_n": int(len(y_test)),
            "test_prevalence": round(float(y_test.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y_test, p)), 4),
            "auc_ci_low": round(lo, 4),
            "auc_ci_high": round(hi, 4),
            "average_precision": round(float(average_precision_score(y_test, p)), 4),
            "brier": round(float(brier_score_loss(y_test, p)), 4),
            "log_loss": round(float(log_loss(y_test, p_clipped, labels=[0, 1])), 4),
        }
        print(f"{component}: auc={results[component]['roc_auc']} "
              f"(ci {results[component]['auc_ci_low']}-{results[component]['auc_ci_high']}), "
              f"prevalence {results[component]['test_prevalence']}", flush=True)

    out = settings.SILVER_DIR / "pain_component_model_report.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2), flush=True)

    ablations = {}
    variants = {
        "structured_only": structured_idx,
        "structured_history": structured_idx,
        "structured_text": all_no_history_idx,
        "all": all_idx,
    }
    for component in ("fi_requested", "pain_high_binary"):
        y_train = train[component].to_numpy()
        y_test = test[component].to_numpy()
        for name, columns in variants.items():
            if name == "structured_only":
                columns = no_history_idx
            p = fit_predict(train_matrix[:, columns], y_train, test_matrix[:, columns], C=0.5)
            ablations.setdefault(component, {})[name] = round(float(roc_auc_score(y_test, p)), 4)
            print(f"ablation {component}/{name}: auc={ablations[component][name]}", flush=True)
    ablations_path = settings.SILVER_DIR / "pain_component_ablation.json"
    ablations_path.write_text(json.dumps(ablations, indent=2), encoding="utf-8")
    print(json.dumps(ablations, indent=2))
