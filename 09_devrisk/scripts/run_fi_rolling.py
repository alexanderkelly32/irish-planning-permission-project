"""Runner: rolling-origin evaluation of the FI model (drift evidence).

For each origin year O in 2018..2022: train on received < O (with C tuned on
the immediately preceding year where available), predict year O. Reports
per-origin AUC, AP, prevalence, mean predicted, calibration slope/intercept
and Brier. This is the time-safe evidence base for production drift
monitoring (brief 16.8); the frozen single-fit model card remains the
reference, this table documents regime drift.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, calibration_slope_intercept, load_cohort  # noqa: E402
from scripts.run_pain_components import add_history_features, build_matrix, fit_predict  # noqa: E402

ORIGINS = (2018, 2019, 2020, 2021, 2022)


if __name__ == "__main__":
    frame = load_cohort()
    frame = add_history_features(frame)

    rows = []
    for origin in ORIGINS:
        train = frame[frame["received_year"] < origin]
        calib = frame[frame["received_year"] == origin - 1]
        target = frame[frame["received_year"] == origin]
        if len(train) < 150 or len(target) < 40:
            rows.append({"origin": origin, "status": "skipped_insufficient_data"})
            continue

        train_matrix, tfidf, cols = build_matrix(train)
        target_matrix, _, _ = build_matrix(target, tfidf)

        best = None
        for C in (0.1, 0.5, 1.0, 5.0):
            if len(calib) >= 30:
                calib_matrix, _, _ = build_matrix(calib, tfidf)
                p = fit_predict(train_matrix, train["fi_requested"].to_numpy(), calib_matrix, C)
                auc = roc_auc_score(calib["fi_requested"], p)
            else:
                auc = None
            if best is None or (auc is not None and auc > best[0]):
                best = (auc if auc is not None else -1, C)

        chosen_C = best[1]
        raw_p = fit_predict(train_matrix, train["fi_requested"].to_numpy(), target_matrix, chosen_C)
        y = target["fi_requested"].to_numpy()
        p = raw_p
        if len(calib) >= 30:
            calib_matrix, _, _ = build_matrix(calib, tfidf)
            calib_p = fit_predict(train_matrix, train["fi_requested"].to_numpy(), calib_matrix, chosen_C)
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(calib_p, calib["fi_requested"])
            p = np.clip(iso.predict(raw_p), 1e-6, 1 - 1e-6)

        lo, hi = bootstrap_auc(y, p, seed=0)
        row = {
            "origin": origin,
            "train_n": int(len(train)),
            "n": int(len(target)),
            "prevalence": round(float(y.mean()), 4),
            "mean_predicted": round(float(p.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y, p)), 4),
            "auc_ci_low": round(lo, 4),
            "auc_ci_high": round(hi, 4),
            "average_precision": round(float(average_precision_score(y, p)), 4),
            "brier": round(float(brier_score_loss(y, p)), 4),
        }
        row.update(calibration_slope_intercept(y, p))
        rows.append(row)
        print(json.dumps(row, default=str), flush=True)

    out = settings.SILVER_DIR / "fi_model_rolling_origins.json"
    out.write_text(json.dumps({"rows": rows}, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"rows": rows}, indent=2, default=str))
