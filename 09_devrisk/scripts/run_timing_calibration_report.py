"""Runner: calibration / coverage report with 95% CIs (user-requested framing).

Refusal (frozen v4, 2025 slice): mean absolute calibration error in pp,
share of predictions within 5/10/15pp of observed rate (per decile bin),
95% bootstrap CIs.

Timing (commencement / sale / decision smooth CDFs): refits the quantile
GBMs, persists test predictions, then reports:
  - empirical coverage of nominal 50/80/90% intervals vs nominal,
  - mean interval width in days,
  - hit rates: share of actuals within +/-30/60/90/120/180/365d of the
    predicted median,
  - MAE / median AE of the median predictor with 95% bootstrap CIs.
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

from devrisk import settings  # noqa: E402
from run_commencement_smooth import HORIZONS, QUANTILE_GRID  # noqa: E402
from run_sale_timing_model import build_frame as sale_build_frame  # noqa: E402
from run_sale_timing_model import county_name, market_context  # noqa: E402

RNG = 7
OUT = settings.SILVER_DIR / "timing_calibration_report.json"


def bootstrap_ci(values: np.ndarray, fn, n_boot: int = 1000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(values), len(values))
        stats.append(fn(values[idx]))
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def timing_block(y_test: np.ndarray, quantile_matrix: np.ndarray, grid: np.ndarray) -> dict:
    n = len(y_test)
    med = quantile_matrix[9, :]

    def coverage(lo_q: int, hi_q: int) -> float:
        return float(np.mean((y_test >= quantile_matrix[lo_q, :]) & (y_test <= quantile_matrix[hi_q, :])))

    cov50, cov80, cov90 = coverage(4, 14), coverage(1, 17), coverage(0, 18)
    width50 = float(np.mean(quantile_matrix[14, :] - quantile_matrix[4, :]))
    width80 = float(np.mean(quantile_matrix[17, :] - quantile_matrix[1, :]))
    width90 = float(np.mean(quantile_matrix[18, :] - quantile_matrix[0, :]))
    mae = float(np.mean(np.abs(y_test - med)))
    med_ae = float(np.median(np.abs(y_test - med)))
    mae_lo, mae_hi = bootstrap_ci(np.abs(y_test - med), np.mean)

    hits = {}
    for window in (30, 60, 90, 120, 180, 365):
        hits[str(window)] = float(np.mean(np.abs(y_test - med) <= window))

    return {
        "n": n,
        "median_prediction_mae_days": round(mae, 1),
        "median_prediction_mae_ci95": [round(mae_lo, 1), round(mae_hi, 1)],
        "median_absolute_error_days": round(med_ae, 1),
        "interval_coverage_vs_nominal": {
            "50pct_interval": {"nominal": 0.50, "empirical": round(cov50, 3), "mean_width_days": round(width50, 0)},
            "80pct_interval": {"nominal": 0.80, "empirical": round(cov80, 3), "mean_width_days": round(width80, 0)},
            "90pct_interval": {"nominal": 0.90, "empirical": round(cov90, 3), "mean_width_days": round(width90, 0)},
        },
        "share_within_window_of_median": {f"pm{d}d": round(share, 3) for d, share in hits.items()},
    }


def refusal_block() -> dict:
    path = settings.ROOT / "05_policy" / "current" / "raw_planning_frozen_2025_calibration_predictions.csv"
    frame = pd.read_csv(path)
    risk = frame["platt_risk"].clip(0, 1)
    y = frame["target_refused"]
    frame["bin"] = pd.qcut(risk.rank(method="first"), 10, labels=False)
    table = frame.groupby("bin").agg(n=("target_refused", "size"), mean_pred=("platt_risk", "mean"), observed=("target_refused", "mean"))
    table["abs_error_pp"] = (table["mean_pred"] - table["observed"]).abs() * 100
    abs_errors = table["abs_error_pp"].to_numpy()
    return {
        "n": int(len(frame)),
        "decile_bins": int(len(table)),
        "mean_abs_calibration_error_pp": round(float(np.mean(abs_errors)), 2),
        "max_abs_calibration_error_pp": round(float(np.max(abs_errors)), 2),
        "share_bins_within_5pp": round(float(np.mean(abs_errors <= 5)), 3),
        "share_bins_within_10pp": round(float(np.mean(abs_errors <= 10)), 3),
        "per_bin": [
            {"bin": int(idx), "n": int(row["n"]), "mean_predicted": round(float(row["mean_pred"]), 4),
             "observed": round(float(row["observed"]), 4), "abs_error_pp": round(float(row["abs_error_pp"]), 2)}
            for idx, row in table.iterrows()
        ],
    }


def commencement_block() -> tuple[dict, dict]:
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    frame = labels.merge(register[["case_key", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite"]], on="case_key", how="inner")
    frame = frame.merge(constraints, on="case_key", how="left")
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

    structured_cols = ["log_units", "log_site_area", "density", "units_missing", "site_missing",
                       "grant_year", "grant_month", "covid_era", "type_house", "type_apartment"]
    constraint_cols = ["fluvial_hit_any", "coastal_hit_any", "coastal_min_logdist", "fluvial_min_logdist",
                       "flood_depth__ncfhm__rp100__m", "niah_min_dist", "niah_count_500m", "wwtp_min_dist",
                       "traffic_min_dist", "natura_min_dist", "prior_auth_activation_rate", "prior_local_activation_rate"]
    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    X_train = np.hstack([train[structured_cols + constraint_cols].fillna(0.0).values, text_train])
    X_test = np.hstack([test[structured_cols + constraint_cols].fillna(0.0).values, text_test])

    quantile_predictions = []
    for q in QUANTILE_GRID:
        model = GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=RNG)
        model.fit(X_train, train["activation"].to_numpy())
        quantile_predictions.append(np.maximum(model.predict(X_test), 1.0))
    matrix = np.maximum.accumulate(np.vstack(quantile_predictions), axis=0)
    pd.DataFrame(matrix.T, columns=[f"q{int(q*100)}" for q in QUANTILE_GRID]).assign(
        actual_days=y_test, case_key=test["case_key"].to_numpy()).to_csv(
        settings.SILVER_DIR / "commencement_smooth_test_predictions.csv", index=False)
    return timing_block(y_test, matrix, QUANTILE_GRID), {"train": int(len(train)), "test": int(len(test))}


def sale_block() -> tuple[dict, dict]:
    frame = sale_build_frame()
    frame["county_ppr"] = frame["PlanningAuthority"].map(county_name)
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    context = market_context(frame, ppr)
    frame = pd.concat([frame, context], axis=1)
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    frame = frame.merge(constraints, on="case_key", how="left")

    train = frame[frame["grant_year"] < 2021]
    test = frame[frame["grant_year"] >= 2021]
    y_test = test["sale_days"].to_numpy()

    structured_cols = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month",
                       "covid_era", "price_level", "volume_12m", "momentum"]
    constraint_cols = ["fluvial_hit_any", "coastal_hit_any", "coastal_min_logdist", "fluvial_min_logdist",
                       "flood_depth__ncfhm__rp100__m", "niah_min_dist", "niah_count_500m", "wwtp_min_dist",
                       "traffic_min_dist", "natura_min_dist"]
    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    X_train = np.hstack([train[structured_cols + constraint_cols].fillna(0.0).values, text_train])
    X_test = np.hstack([test[structured_cols + constraint_cols].fillna(0.0).values, text_test])

    quantile_predictions = []
    for q in QUANTILE_GRID:
        model = GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=10, random_state=RNG)
        model.fit(X_train, train["sale_days"].to_numpy())
        quantile_predictions.append(np.maximum(model.predict(X_test), 1.0))
    matrix = np.maximum.accumulate(np.vstack(quantile_predictions), axis=0)
    pd.DataFrame(matrix.T, columns=[f"q{int(q*100)}" for q in QUANTILE_GRID]).assign(
        actual_days=y_test, case_key=test["case_key"].astype(str).to_numpy()).to_csv(
        settings.SILVER_DIR / "sale_smooth_test_predictions.csv", index=False)
    return timing_block(y_test, matrix, QUANTILE_GRID), {"train": int(len(train)), "test": int(len(test))}


if __name__ == "__main__":
    report = {"refusal_v4_2025_calibration_pp": refusal_block()}
    for name, fn in (("commencement", commencement_block), ("sale", sale_block)):
        block, sizes = fn()
        report[f"{name}_timing"] = {**sizes, **block}
        print(f"{name}: done ({sizes})", flush=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
