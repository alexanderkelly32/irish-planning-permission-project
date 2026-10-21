"""Runner: commencement smooth CDF v2 - adds constraint + history features.

v1 (scheme features only) showed perfect quantile calibration but no
discrimination (td-AUC ~0.5). v2 adds submission-time-safe constraint
proximity (flood, NIAH, WWTP, traffic, Natura) + prior activation rates.
Same split (grant < 2020 train, >= 2020 test) for like-for-like comparison.
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
from run_commencement_smooth import HORIZONS, QUANTILE_GRID  # noqa: E402

RNG = 7

if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite"]], on="case_key", how="inner")
    frame = frame.merge(constraints, on="case_key", how="left")
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
    print(f"train={len(train)}, test={len(test)}", flush=True)

    structured_cols = ["log_units", "log_site_area", "density", "units_missing", "site_missing",
                       "grant_year", "grant_month", "covid_era", "type_house", "type_apartment"]
    constraint_cols = ["fluvial_hit_any", "coastal_hit_any", "coastal_min_logdist", "fluvial_min_logdist",
                       "flood_depth__ncfhm__rp100__m", "niah_min_dist", "niah_count_500m", "wwtp_min_dist",
                       "traffic_min_dist", "natura_min_dist", "prior_auth_activation_rate", "prior_local_activation_rate"]

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    base_train = train[structured_cols + constraint_cols].fillna(0.0).values
    base_test = test[structured_cols + constraint_cols].fillna(0.0).values
    X_train = np.hstack([base_train, text_train])
    X_test = np.hstack([base_test, text_test])

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

    report = {"model": "commencement_smooth_cdf_v2", "n": {"train": int(len(train)), "test": int(len(test))},
              "added_features": constraint_cols}

    coverage_devs = []
    for row_idx, q in enumerate(QUANTILE_GRID):
        predicted = quantile_matrix[row_idx, :]
        coverage_devs.append(float(np.mean(y_test <= predicted)) - q)
    coverage_devs = np.array(coverage_devs)
    report["coverage_calibration"] = {
        "mean_abs_dev_pp": round(float(np.mean(np.abs(coverage_devs)) * 100), 1),
        "max_abs_dev_pp": round(float(np.max(np.abs(coverage_devs)) * 100), 1),
    }

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

    (settings.SILVER_DIR / "commencement_smooth_cdf_v2.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
