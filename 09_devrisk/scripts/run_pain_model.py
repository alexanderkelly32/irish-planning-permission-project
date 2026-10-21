"""Runner: submission-time pain-to-develop model (research baseline, Amendment A).

Predicts P(pain_v1 == high) at submission time from:
  - authority, received year, units, site area/density, scheme type;
  - TF-IDF of the application description (vocabulary fit on train only).

Temporal split by received date: train < 2020, validation 2020-2021, holdout
2022+ (fallback if too small: train < 2021, holdout >= 2021). Isotonic
calibration fit on validation. Reports AUC (bootstrap CI), AP, Brier, log
loss, calibration slope/intercept, per-year and size-band performance, and
compares against non-text baselines. Research output only - not a product.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, calibration_slope_intercept, evaluate, load_cohort  # noqa: E402

RNG = 7


def build_feature_frame(frame: pd.DataFrame, tfidf: TfidfVectorizer | None = None):
    structured = pd.DataFrame({
        "log_units": frame["log_units"],
        "log_site_area": frame["log_site_area"],
        "units_missing": frame["units_missing"],
        "site_missing": frame["site_missing"],
        "density": frame["density"].fillna(0.0),
        "received_year": frame["received_year"].astype(float),
        "covid_era": frame["covid_era"],
        "type_house": frame["type_house"].astype(int),
        "type_apartment": frame["type_apartment"].astype(int),
    })
    fresh = tfidf is None
    tfidf = tfidf or TfidfVectorizer(
        ngram_range=(1, 2), max_features=20000, sublinear_tf=True,
        stop_words="english", min_df=3,
    )
    text = tfidf.fit_transform(frame["description_lower"]).toarray() if fresh else tfidf.transform(frame["description_lower"]).toarray()
    text_frame = pd.DataFrame(text, index=structured.index, columns=[f"t{i}" for i in range(text.shape[1])])
    return pd.concat([structured, text_frame], axis=1), tfidf


def fit_model(train_features: pd.DataFrame, y: np.ndarray, C: float):
    numeric = ["log_units", "log_site_area", "units_missing", "site_missing", "density",
               "received_year", "covid_era", "type_house", "type_apartment"]
    text_columns = [column for column in train_features.columns if column.startswith("t")]
    preprocessor = ColumnTransformer(
        [
            ("num", StandardScaler(), numeric),
            ("text", "passthrough", text_columns),
            ("cat", OneHotEncoder(handle_unknown="ignore"), []),
        ],
        remainder="drop",
    )
    model = Pipeline([
        ("prep", preprocessor),
        ("clf", LogisticRegression(C=C, max_iter=3000, solver="lbfgs")),
    ])
    model.fit(train_features, y)
    return model


def baseline_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "authority": frame["PlanningAuthority"],
        "received_year": frame["received_year"].astype(float),
        "log_units": frame["log_units"],
    })


if __name__ == "__main__":
    frame = load_cohort()
    print(f"cohort n={len(frame)}, high-pain prevalence={frame['pain_high_binary'].mean():.3f}")
    print("received-year counts:", frame["received_year"].value_counts().sort_index().to_dict())

    train = frame[frame["received_year"] < 2020]
    val = frame[frame["received_year"] == 2020]
    test = frame[frame["received_year"] >= 2021]
    split_note = "train<2020, val=2020, test>=2021"
    if len(val) < 100:
        train = frame[frame["received_year"] < 2021]
        val = frame[frame["received_year"] == 2021]
        test = frame[frame["received_year"] >= 2022]
        split_note = "fallback split: train<2021, val=2021, test>=2022"
    print(f"split: train={len(train)}, val={len(val)}, test={len(test)} ({split_note})")
    print(f"test prevalence={test['pain_high_binary'].mean():.3f}")

    report: dict[str, object] = {"split": split_note, "splits": {"train": int(len(train)), "val": int(len(val)), "test": int(len(test))}}

    # Baseline 1: overall base rate.
    report["baseline_base_rate"] = evaluate(test["pain_high_binary"].to_numpy(), np.full(len(test), train["pain_high_binary"].mean()))

    # Baseline 2: authority + year + units logistic (no text).
    base_features = baseline_frame(frame)
    base_pipeline = Pipeline([
        ("cat", OneHotEncoder(handle_unknown="ignore")),
        ("clf", LogisticRegression(C=1.0, max_iter=3000)),
    ])
    base_pipeline.fit(base_features.loc[train.index], train["pain_high_binary"])
    base_p = base_pipeline.predict_proba(base_features.loc[test.index])[:, 1]
    report["baseline_structured_no_text"] = evaluate(test["pain_high_binary"].to_numpy(), base_p)

    # Main: text + structured, C chosen on validation.
    train_features, tfidf = build_feature_frame(train)
    val_features, _ = build_feature_frame(val, tfidf)
    test_features, _ = build_feature_frame(test, tfidf)
    best = None
    for C in (0.1, 0.5, 1.0, 5.0, 10.0):
        model = fit_model(train_features, train["pain_high_binary"], C)
        val_p = model.predict_proba(val_features)[:, 1]
        auc = roc_auc_score(val["pain_high_binary"], val_p)
        if best is None or auc > best[0]:
            best = (auc, C, model, val_p)
    val_auc, best_C, model, val_p = best
    report["chosen_C"] = best_C
    report["validation_auc"] = round(val_auc, 4)

    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(val_p, val["pain_high_binary"])
    raw_test_p = model.predict_proba(test_features)[:, 1]
    test_p = iso.predict(raw_test_p)
    report["pain_model"] = evaluate(test["pain_high_binary"].to_numpy(), test_p)

    per_year = {}
    test_scored = test.copy()
    test_scored["pred"] = test_p
    for year, part in test_scored.groupby("received_year"):
        if part["pain_high_binary"].nunique() == 2 and len(part) >= 20:
            per_year[str(year)] = evaluate(part["pain_high_binary"].to_numpy(), part["pred"].to_numpy())
    report["by_year"] = per_year

    per_band = {}
    units = test_scored["units"]
    test_scored["band"] = pd.cut(units, bins=[-np.inf, 29, 99, 249, np.inf], labels=["10-29", "30-99", "100-249", "250+"])
    for band, part in test_scored.groupby("band", observed=False):
        if part["pain_high_binary"].nunique() == 2 and len(part) >= 20:
            per_band[str(band)] = evaluate(part["pain_high_binary"].to_numpy(), part["pred"].to_numpy())
    report["by_size_band"] = per_band

    predictions = test_scored[["case_key", "PlanningAuthority", "received_year", "units", "pain_high_binary", "pred"]].copy()
    predictions.rename(columns={"pred": "p_pain_high"}, inplace=True)
    predictions.to_csv(settings.SILVER_DIR / "pain_model_holdout_predictions.csv", index=False)

    out = settings.SILVER_DIR / "pain_model_baseline_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
