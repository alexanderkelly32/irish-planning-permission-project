"""Runner: calibrated submission-time FI-request model (strongest pain leg).

Train received < 2020, tune C on 2020, isotonic calibration on 2020,
evaluate 2021+ holdout. Produces a model card JSON and holdout predictions.
Research-grade: small cohort, regime drift documented, not a product.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, calibration_slope_intercept, evaluate, load_cohort  # noqa: E402
from scripts.run_pain_components import add_history_features, build_matrix, fit_predict  # noqa: E402

if __name__ == "__main__":
    frame = load_cohort()
    frame = add_history_features(frame)

    train = frame[frame["received_year"] < 2020]
    val = frame[frame["received_year"] == 2020]
    test = frame[frame["received_year"] >= 2021]
    print(f"train={len(train)}, val={len(val)}, test={len(test)}", flush=True)

    train_matrix, tfidf, cols = build_matrix(train)
    val_matrix, _, _ = build_matrix(val, tfidf)
    test_matrix, _, _ = build_matrix(test, tfidf)

    y_train = train["fi_requested"].to_numpy()
    y_val = val["fi_requested"].to_numpy()
    y_test = test["fi_requested"].to_numpy()

    best = None
    for C in (0.1, 0.5, 1.0, 5.0, 10.0):
        p = fit_predict(train_matrix, y_train, val_matrix, C)
        auc = roc_auc_score(y_val, p)
        if best is None or auc > best[0]:
            best = (auc, C, p)
    val_auc, best_C, val_p = best
    print(f"chosen C={best_C}, val auc={round(val_auc, 4)}", flush=True)

    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(val_p, y_val)

    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler(with_mean=False)
    X_train = scaler.fit_transform(train_matrix)
    X_test = scaler.transform(test_matrix)
    clf = LogisticRegression(C=best_C, max_iter=2000, solver="liblinear")
    clf.fit(X_train, y_train)
    raw_test_p = clf.predict_proba(X_test)[:, 1]
    test_p = np.clip(iso.predict(raw_test_p), 1e-6, 1 - 1e-6)

    card = {
        "model": "fi_requested_submission_time_v1",
        "target": "at least one formal FI request before decision (register FIRequestDate/FIRecDate)",
        "prediction_time": "immediately before submission",
        "split": "train received < 2020, C tuned + isotonic on 2020, holdout received >= 2021",
        "chosen_C": best_C,
        "validation_auc": round(val_auc, 4),
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

    per_year = {}
    test_scored = test.copy()
    test_scored["p_fi"] = test_p
    for year, part in test_scored.groupby("received_year"):
        if part["fi_requested"].nunique() == 2:
            per_year[str(year)] = evaluate(part["fi_requested"].to_numpy(), part["p_fi"].to_numpy())
    card["by_year"] = per_year

    predictions = test_scored[["case_key", "PlanningAuthority", "received_year", "units", "fi_requested", "p_fi"]].copy()
    predictions.to_csv(settings.SILVER_DIR / "fi_model_holdout_predictions.csv", index=False)

    out = settings.SILVER_DIR / "fi_model_card.json"
    out.write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
    print(json.dumps(card, indent=2, default=str))

    # Persist the fitted pipeline for prototype reporting (gold layer).
    import joblib

    artifact = {
        "model_version": "fi_requested_submission_time_v1",
        "target": card["target"],
        "prediction_time": card["prediction_time"],
        "C": best_C,
        "tfidf": tfidf,
        "structured_columns": cols,
        "scaler": scaler,
        "clf": clf,
        "iso": iso,
        "training_cutoff_exclusive": str(int(train["received_year"].max()) + 1),
        "calibration_year": 2020,
        "holdout": card["holdout"],
    }
    artifact_path = settings.GOLD_DIR / "fi_model_v1.joblib"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, artifact_path)
    print(f"persisted -> {artifact_path}")
