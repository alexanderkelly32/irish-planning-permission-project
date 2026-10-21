"""Runner: timing models v3 - applicant track-record features added.

Adds time-safe applicant features (prior n, grant rate, refusal rate, median
activation, median time-to-sale) to the commencement and sale smooth quantile
models; reports interval width + coverage + td-AUC against v2 baselines.
Run after run_applicant_features.py (needs applicant_track_record_features.csv).
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
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from run_commencement_smooth import HORIZONS, QUANTILE_GRID  # noqa: E402
from run_sale_timing_model import build_frame as sale_build_frame  # noqa: E402
from run_sale_timing_model import county_name, market_context  # noqa: E402
from run_sale_timing_smooth import monotone_cdf  # noqa: E402

RNG = 7

APPLICANT_COLS = ["applicant_prior_n", "applicant_prior_grant_rate", "applicant_prior_refusal_rate",
                  "applicant_prior_median_activation", "applicant_prior_median_tfs", "has_applicant"]


def fit_smooth(X_train: np.ndarray, y_train: np.ndarray, X_test: np.ndarray,
               min_samples_leaf: int) -> np.ndarray:
    predictions = []
    for q in QUANTILE_GRID:
        model = GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=min_samples_leaf, random_state=RNG)
        model.fit(X_train, y_train)
        predictions.append(np.maximum(model.predict(X_test), 1.0))
    return np.maximum.accumulate(np.vstack(predictions), axis=0)


def evaluate(y_test: np.ndarray, matrix: np.ndarray) -> dict:
    med = matrix[9, :]
    lo, hi = matrix[1, :], matrix[17, :]
    coverage = float(np.mean((y_test >= lo) & (y_test <= hi)))
    width = float(np.mean(hi - lo))
    td_auc = {}
    for horizon in HORIZONS:
        prob = monotone_cdf(matrix, QUANTILE_GRID, horizon)
        y_h = (y_test <= horizon).astype(int)
        td_auc[str(horizon)] = round(float(roc_auc_score(y_h, prob)), 4) if y_h.mean() not in (0.0, 1.0) else None
    return {
        "mean_80pct_width_days": round(width, 0),
        "coverage_80pct": round(coverage, 3),
        "mae_median_days": round(float(np.mean(np.abs(y_test - med))), 1),
        "time_dependent_auc": td_auc,
    }


def commencement_v3() -> dict:
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    frame = labels.merge(register[["case_key", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite"]], on="case_key", how="inner")
    frame = frame.merge(constraints, on="case_key", how="left").merge(applicants, on="case_key", how="left")
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    comm = frame[frame["activation_linked"].astype(bool)].dropna(subset=["activation", "grant_dt"]).sort_values("grant_dt").reset_index(drop=True)
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
    y_test = test["activation"].to_numpy()

    structured = ["log_units", "log_site_area", "density", "units_missing", "site_missing",
                  "grant_year", "grant_month", "covid_era", "type_house", "type_apartment"]
    constraint_cols = ["fluvial_hit_any", "coastal_hit_any", "coastal_min_logdist", "fluvial_min_logdist",
                       "flood_depth__ncfhm__rp100__m", "niah_min_dist", "niah_count_500m", "wwtp_min_dist",
                       "traffic_min_dist", "natura_min_dist", "prior_auth_activation_rate", "prior_local_activation_rate"]
    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    X_train = np.hstack([train[structured + constraint_cols + APPLICANT_COLS].fillna(0.0).values, text_train])
    X_test = np.hstack([test[structured + constraint_cols + APPLICANT_COLS].fillna(0.0).values, text_test])

    matrix = fit_smooth(X_train, train["activation"].to_numpy(), X_test, min_samples_leaf=15)
    report = evaluate(y_test, matrix)
    report["n"] = {"train": int(len(train)), "test": int(len(test))}
    report["baseline_v2"] = {"mean_80pct_width_days": 1135.0, "coverage_80pct": 0.832}
    return report


def sale_v3() -> dict:
    frame = sale_build_frame()
    frame["county_ppr"] = frame["PlanningAuthority"].map(county_name)
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    context = market_context(frame, ppr)
    frame = pd.concat([frame, context], axis=1)
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    frame = frame.merge(constraints, on="case_key", how="left").merge(applicants, on="case_key", how="left")

    train = frame[frame["grant_year"] < 2021]
    test = frame[frame["grant_year"] >= 2021]
    y_test = test["sale_days"].to_numpy()

    structured = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month",
                  "covid_era", "price_level", "volume_12m", "momentum"]
    constraint_cols = ["fluvial_hit_any", "coastal_hit_any", "coastal_min_logdist", "fluvial_min_logdist",
                       "flood_depth__ncfhm__rp100__m", "niah_min_dist", "niah_count_500m", "wwtp_min_dist",
                       "traffic_min_dist", "natura_min_dist"]
    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    X_train = np.hstack([train[structured + constraint_cols + APPLICANT_COLS].fillna(0.0).values, text_train])
    X_test = np.hstack([test[structured + constraint_cols + APPLICANT_COLS].fillna(0.0).values, text_test])

    matrix = fit_smooth(X_train, train["sale_days"].to_numpy(), X_test, min_samples_leaf=10)
    report = evaluate(y_test, matrix)
    report["n"] = {"train": int(len(train)), "test": int(len(test))}
    report["baseline_v2"] = {"mean_80pct_width_days": 1485.0, "coverage_80pct": 0.835}
    return report


if __name__ == "__main__":
    report = {"commencement_v3": commencement_v3(), "sale_v3": sale_v3()}
    out = settings.SILVER_DIR / "applicant_timing_v3.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
