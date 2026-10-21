#!/usr/bin/env python3
"""V5 theme-classifier experiment: predict the primary refusal theme of a
large residential scheme from submission-time features only.

Framing (honest): this is a CONDITIONAL model - given that a scheme is
refused, which grounds are most likely? Trained on refused GE10 schemes with
an extracted primary theme, split on the same 80/20 regime boundary as
v4-full (train received < 2024-01-01, test 2024-2025).

Features (submission-time only, identical families to v4-full):
  description TF-IDF (1,2) + numeric features + council + scheme bucket.
Refusal themes are labels only, never features.

Baselines on the same test set:
  - global majority theme
  - per-council majority theme
  - the product's precedent-transfer engine (time-safe matched refusals)

Candidate only - v4-full remains the promoted artifact.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from scipy.sparse import csr_matrix

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "05_policy" / "current" / "model_v5_theme"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CUTOFF = pd.Timestamp("2024-01-01", tz="UTC")

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_8020_regime_experiment import build_data  # noqa: E402

FROZEN = ROOT / "05_policy" / "current" / "model_v4" / "comparable_reference.joblib"
CANONICAL = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
GE10_REFUSALS = ROOT / "03_refusal" / "current" / "greater_than_10_units_with_refusal_reasons_master.csv"
LLM_NEW = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_llm_new.csv"

TOP_K = 10
WEIGHTS = {"text": 0.45, "units": 0.20, "density": 0.10, "recency": 0.15, "council": 0.10}


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def load_themes() -> pd.DataFrame:
    sources = []
    for path, priority, council_col, app_col in (
        (CANONICAL, 1, "council", "application_number"),
        (GE10_REFUSALS, 2, "PlanningAuthority", "ApplicationNumber"),
        (LLM_NEW, 3, "council", "application_number"),
    ):
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        frame["_join"] = frame[council_col].map(_norm) + "__" + frame[app_col].map(_norm)
        frame["priority"] = priority
        sources.append(frame[["_join", "case_top_primary_tag", "priority"]])
    themes = pd.concat(sources, ignore_index=True)
    themes["case_top_primary_tag"] = themes["case_top_primary_tag"].fillna("").astype(str).str.strip()
    themes = themes[themes["case_top_primary_tag"].ne("")]
    return themes.sort_values("priority").drop_duplicates("_join", keep="first")


def top_k_accuracy(y_true: np.ndarray, proba: np.ndarray, classes: np.ndarray, k: int) -> float:
    top = classes[np.argsort(-proba, axis=1)[:, :k]]
    hits = sum(1 for i, true in enumerate(y_true) if true in top[i])
    return hits / len(y_true)


def transfer_baseline(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Recompute the product's precedent-transfer theme predictions on the same test set."""
    frozen = joblib.load(FROZEN)
    vectorizer = frozen["vectorizer"]
    pool = train[train["case_top_primary_tag"].notna() & (train["target_refused"] == 1)].copy()
    pool_matrix = vectorizer.transform(pool["description_stripped"].fillna("").astype(str))

    test = test.reset_index(drop=True)
    results = []
    for _, row in test.iterrows():
        eligible = pool["received_date_dt"] < row["received_date_dt"]
        if not eligible.any():
            results.append(None)
            continue
        indices = pool.index[eligible]
        query_vec = vectorizer.transform([str(row["description_stripped"]) or ""])
        from sklearn.metrics.pairwise import cosine_similarity

        text_sims = np.asarray(cosine_similarity(query_vec, pool_matrix)).ravel()
        units_row = pool["units"].astype(float)
        query_units = float(row["units"]) if pd.notna(row["units"]) else np.nan
        if not np.isnan(query_units):
            known = ~np.isnan(units_row) & (units_row > 0)
            unit_close = np.where(known, np.exp(-0.6 * np.abs(np.log1p(np.where(known, units_row, 1.0)) - np.log1p(query_units))), 0.5)
        else:
            unit_close = np.full(len(text_sims), 0.5)
        site_row = pool["AreaofSite"].astype(float) * 10000.0
        query_site = float(row["AreaofSite"]) * 10000.0 if pd.notna(row["AreaofSite"]) else np.nan
        density_close = np.full(len(text_sims), 0.5)
        if not np.isnan(query_units) and not np.isnan(query_site) and query_site > 0:
            query_density = np.log(query_units / query_site)
            known_d = ~np.isnan(site_row) & (site_row > 0) & ~np.isnan(units_row) & (units_row > 0)
            density_close = np.where(known_d, np.exp(-0.6 * np.abs(np.log(np.where(known_d, units_row / np.where(known_d, site_row, 1.0), 1.0)) - query_density)), 0.5)
        age = np.clip(row["received_date_dt"].year - pool["received_date_dt"].dt.year.to_numpy(), 0, 5)
        recency = np.exp(-age / 2.5)
        council_boost = (pool["PlanningAuthority"] == row["PlanningAuthority"]).astype(float).to_numpy()
        combined = (WEIGHTS["text"] * text_sims + WEIGHTS["units"] * unit_close
                    + WEIGHTS["density"] * density_close + WEIGHTS["recency"] * recency
                    + WEIGHTS["council"] * council_boost) * eligible.to_numpy()
        order = np.argsort(-combined)
        votes: dict[str, float] = {}
        chosen = 0
        for candidate in order:
            if chosen >= TOP_K or combined[candidate] <= 0:
                break
            chosen += 1
            theme = str(pool.iloc[candidate]["case_top_primary_tag"])
            votes[theme] = votes.get(theme, 0.0) + combined[candidate]
        if not votes:
            results.append(None)
            continue
        ranked = sorted(votes.items(), key=lambda pair: -pair[1])
        results.append([theme for theme, _ in ranked[:3]])
    return results


def main() -> None:
    data, train, _test, _y = build_data()
    themes = load_themes()
    data["_join"] = data["PlanningAuthority"].map(_norm) + "__" + data["ApplicationNumber"].map(_norm)
    data = data.merge(themes[["_join", "case_top_primary_tag"]], on="_join", how="left")

    cohort = data[(data["units"] >= 10) & (data["target_refused"] == 1) & data["case_top_primary_tag"].notna()].copy()
    train_frame = cohort[cohort["received_date_dt"] < CUTOFF].copy()
    test_frame = cohort[cohort["received_date_dt"] >= CUTOFF].copy().reset_index(drop=True)

    manifest = json.loads((ROOT / "05_policy" / "current" / "model_v4" / "manifest.json").read_text(encoding="utf-8"))
    feature_columns = manifest["feature_columns"]
    numeric_cols = [c for c in feature_columns if c not in ("PlanningAuthority", "description_stripped", "application_bucket")]

    classes = np.array(sorted(train_frame["case_top_primary_tag"].unique()))
    y_train = train_frame["case_top_primary_tag"].to_numpy()
    y_test = test_frame["case_top_primary_tag"].to_numpy()

    preprocessor = ColumnTransformer([
        ("txt", TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=80_000,
                                min_df=2, sublinear_tf=True, strip_accents="unicode"), "description_stripped"),
        ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric_cols),
        ("auth", OneHotEncoder(handle_unknown="ignore"), ["PlanningAuthority"]),
        ("bucket", OneHotEncoder(handle_unknown="ignore"), ["application_bucket"]),
    ])
    variants = {
        "logreg_c1": LogisticRegression(C=1.0, solver="lbfgs", max_iter=3000, n_jobs=-1),
        "logreg_c1_balanced": LogisticRegression(C=1.0, solver="lbfgs", max_iter=3000, n_jobs=-1, class_weight="balanced"),
        "logreg_c03": LogisticRegression(C=0.3, solver="lbfgs", max_iter=3000, n_jobs=-1),
    }
    model = Pipeline([("pre", preprocessor), ("clf", variants["logreg_c1"])])
    model.fit(train_frame, y_train)
    proba = model.predict_proba(test_frame)
    class_order = model.named_steps["clf"].classes_

    variant_metrics = {}
    for name, estimator in variants.items():
        candidate = Pipeline([("pre", preprocessor), ("clf", estimator)])
        candidate.fit(train_frame, y_train)
        p = candidate.predict_proba(test_frame)
        variant_metrics[name] = {
            "top1": round(float(accuracy_score(y_test, candidate.predict(test_frame))), 3),
            "top2": round(top_k_accuracy(y_test, p, class_order, 2), 3),
            "top3": round(top_k_accuracy(y_test, p, class_order, 3), 3),
            "macro_f1": round(float(f1_score(y_test, candidate.predict(test_frame), average="macro", zero_division=0)), 3),
        }

    majority_global = train_frame["case_top_primary_tag"].mode().iloc[0]
    council_majority = {}
    for council, group in train_frame.groupby("PlanningAuthority"):
        council_majority[council] = group["case_top_primary_tag"].mode().iloc[0]

    majority_hits = sum(1 for true in y_test if true == majority_global)
    council_hits = 0
    council_evaluable = 0
    for _, row in test_frame.iterrows():
        predicted = council_majority.get(row["PlanningAuthority"], majority_global)
        if predicted == row["case_top_primary_tag"]:
            council_hits += 1
        council_evaluable += 1

    transfer = transfer_baseline(train_frame, test_frame)
    transfer_top1 = transfer_top2 = transfer_top3 = 0
    transfer_n = 0
    for prediction, true in zip(transfer, y_test):
        if prediction is None:
            continue
        transfer_n += 1
        if prediction[0] == true:
            transfer_top1 += 1
        if true in prediction[:2]:
            transfer_top2 += 1
        if true in prediction[:3]:
            transfer_top3 += 1

    precision, recall, f1, support = precision_recall_fscore_support(y_test, model.predict(test_frame), labels=class_order, zero_division=0)
    per_class = [
        {"theme": str(cls), "n_test": int(s), "precision": round(float(p), 3), "recall": round(float(r), 3), "f1": round(float(f), 3)}
        for cls, p, r, f, s in zip(class_order, precision, recall, f1, support)
    ]

    results = {
        "candidate": "v5_theme_classifier",
        "framing": "conditional: given refusal, most likely primary grounds; submission-time features only",
        "protocol": "80/20 regime split; train received < 2024-01-01, test 2024-2025; refused GE10 with extracted theme",
        "cohort": {"train_n": int(len(train_frame)), "test_n": int(len(test_frame)),
                   "train_class_balance": train_frame["case_top_primary_tag"].value_counts().to_dict(),
                   "test_class_balance": test_frame["case_top_primary_tag"].value_counts().to_dict()},
        "model": {"estimator": "LogisticRegression(multinomial) variants", "features": "v4 numeric set + TF-IDF(1,2) text + council OHE + bucket OHE"},
        "variants": variant_metrics,
        "metrics": {
            "classifier_top1": round(float(accuracy_score(y_test, model.predict(test_frame))), 3),
            "classifier_top2": round(top_k_accuracy(y_test, proba, class_order, 2), 3),
            "classifier_top3": round(top_k_accuracy(y_test, proba, class_order, 3), 3),
            "classifier_macro_f1": round(float(f1_score(y_test, model.predict(test_frame), average="macro", zero_division=0)), 3),
            "classifier_weighted_f1": round(float(f1_score(y_test, model.predict(test_frame), average="weighted", zero_division=0)), 3),
            "majority_baseline_top1": round(majority_hits / len(y_test), 3),
            "council_majority_baseline_top1": round(council_hits / council_evaluable, 3),
            "transfer_engine_top1": round(transfer_top1 / transfer_n, 3) if transfer_n else None,
            "transfer_engine_top2": round(transfer_top2 / transfer_n, 3) if transfer_n else None,
            "transfer_engine_top3": round(transfer_top3 / transfer_n, 3) if transfer_n else None,
            "transfer_engine_evaluable": transfer_n,
        },
        "per_class": per_class,
        "caveats": [
            "Conditional model: it assumes refusal and predicts grounds - not refusal probability.",
            "Labels are primary themes from inspector documents (multi-theme cases reduced to one).",
            "n_test is small (81) - wide confidence; candidate only, v4-full remains promoted.",
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    joblib.dump({"pipeline": model, "classes": class_order, "feature_columns": feature_columns,
                 "numeric_cols": numeric_cols}, OUT_DIR / "theme_classifier_v5.joblib")
    (ROOT / "05_policy" / "current" / "raw_planning_v5_theme_experiment.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results["metrics"], indent=2))
    print(json.dumps(results["per_class"], indent=1))
    print("saved ->", OUT_DIR)


if __name__ == "__main__":
    main()
