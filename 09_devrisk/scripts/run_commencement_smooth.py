"""Runner: smooth conditional CDF for grant->commencement timing (bin-free).

19-quantile GBMs + monotone interpolation -> P(T <= t) for any horizon, for
schemes that do commence (conditional framing, consistent with the strata
baselines). Continuous evaluation: time-dependent AUC curve across horizons
and bin-free quantile coverage. Split: grant < 2020 train, >= 2020 test
(matches the era-recalibration protocol).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from run_sale_timing_smooth import monotone_cdf  # noqa: E402

RNG = 7
QUANTILE_GRID = np.arange(0.05, 1.0, 0.05)
HORIZONS = [365, 548, 730, 913, 1096, 1461, 1826]


if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite", "ITMEasting", "ITMNorthing"]],
                         on="case_key", how="inner")
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    comm = frame[frame["activation_linked"].astype(bool)].dropna(subset=["activation", "grant_dt"]).copy()
    comm = comm.sort_values("grant_dt").reset_index(drop=True)

    units = pd.to_numeric(comm["NumResidentialUnits"], errors="coerce")
    site = pd.to_numeric(comm["AreaofSite"], errors="coerce")
    comm["log_units"] = np.log1p(units.fillna(0))
    comm["log_site_area"] = np.log1p(site.fillna(0))
    comm["density"] = (units / site * 10000.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    comm["units_missing"] = units.isna().astype(int)
    comm["site_missing"] = site.isna().astype(int)
    comm["grant_year"] = comm["grant_dt"].dt.year
    comm["grant_month"] = comm["grant_dt"].dt.month
    comm["covid_era"] = comm["grant_year"].between(2020, 2021).astype(int)
    description = comm["DevelopmentDescription"].fillna("")
    comm["type_house"] = description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)
    comm["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True)
    comm["description_lower"] = description.str.lower()

    train = comm[comm["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2020-01-01", tz="UTC")]
    y_train = train["activation"].to_numpy()
    y_test = test["activation"].to_numpy()
    print(f"train={len(train)}, test={len(test)}, test median {np.median(y_test):.0f}d", flush=True)

    structured_cols = ["log_units", "log_site_area", "density", "units_missing", "site_missing",
                       "grant_year", "grant_month", "covid_era", "type_house", "type_apartment"]
    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    X_train = np.hstack([train[structured_cols].fillna(0.0).values, text_train])
    X_test = np.hstack([test[structured_cols].fillna(0.0).values, text_test])

    models = {}
    quantile_predictions = []
    for q in QUANTILE_GRID:
        model = GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=RNG)
        model.fit(X_train, y_train)
        models[round(float(q), 2)] = model
        quantile_predictions.append(np.maximum(model.predict(X_test), 1.0))
        print(f"fit q={q:.2f}", flush=True)

    quantile_matrix = np.maximum.accumulate(np.vstack(quantile_predictions), axis=0)

    report = {"model": "commencement_smooth_cdf_v1", "n": {"train": int(len(train)), "test": int(len(test))},
              "test_median_days": round(float(np.median(y_test)), 1)}

    coverage_devs = []
    for row_idx, q in enumerate(QUANTILE_GRID):
        predicted = quantile_matrix[row_idx, :]
        coverage_devs.append(float(np.mean(y_test <= predicted)) - q)
    coverage_devs = np.array(coverage_devs)
    report["coverage_calibration"] = {
        "mean_abs_dev_pp": round(float(np.mean(np.abs(coverage_devs)) * 100), 1),
        "max_abs_dev_pp": round(float(np.max(np.abs(coverage_devs)) * 100), 1),
    }

    interval_80 = quantile_matrix[17, :] - quantile_matrix[1, :]
    report["interval_80_mean_width_days"] = round(float(np.mean(interval_80)), 1)

    report["time_dependent_auc"] = {}
    report["brier_by_horizon"] = {}
    for horizon in HORIZONS:
        prob_before = monotone_cdf(quantile_matrix, QUANTILE_GRID, horizon)
        y_h = (y_test <= horizon).astype(int)
        auc = roc_auc_score(y_h, prob_before) if y_h.mean() not in (0.0, 1.0) else None
        report["time_dependent_auc"][str(horizon)] = round(float(auc), 4) if auc is not None else None
        report["brier_by_horizon"][str(horizon)] = {
            "prevalence": round(float(y_h.mean()), 4),
            "brier_smooth": round(float(brier_score_loss(y_h, np.clip(prob_before, 1e-6, 1 - 1e-6))), 4),
            "brier_base": round(float(brier_score_loss(y_h, np.full(len(y_h), y_h.mean()))), 4),
        }

    (settings.SILVER_DIR / "commencement_smooth_cdf.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    import joblib

    artifact = {
        "model_version": "commencement_smooth_cdf_v1",
        "quantile_grid": QUANTILE_GRID.tolist(),
        "models": models,
        "structured_columns": structured_cols,
        "tfidf": tfidf,
        "horizons": HORIZONS,
    }
    path = settings.GOLD_DIR / "commencement_smooth_v1.joblib"
    joblib.dump(artifact, path)
    print(f"persisted -> {path}")
