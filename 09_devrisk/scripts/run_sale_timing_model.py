"""Runner: time-to-sale model - grant -> first confirmed PPR sale.

Sold schemes only (conditional-on-sold; unlinked = unknown, never "slow").
Features at final grant (time-safe): scheme scale/type/description + county
market context from PPR history BEFORE the grant date (price level, 12-month
volume, price momentum) + grant vintage. Split: grant < 2021 train, >= 2021
holdout. Baselines: constant, authority-year strata; candidates: ridge on
log-days, GBM quantiles. Horizon classifier: P(first sale within 24m).
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
from sklearn.linear_model import LogisticRegression, Ridge  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc, calibration_slope_intercept  # noqa: E402

RNG = 7


def pinball(y, pred, tau):
    diff = y - pred
    return float(np.mean(np.where(diff >= 0, tau * diff, (tau - 1) * diff)))


def build_frame() -> pd.DataFrame:
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    frame = cohort.merge(exit_labels[["case_key", "first_sale_date", "time_to_first_sale_from_grant_days", "sales_linked"]],
                         on="case_key", how="inner")
    frame = frame[frame["first_sale_date"].notna()].copy()
    frame["sale_days"] = pd.to_numeric(frame["time_to_first_sale_from_grant_days"], errors="coerce")
    frame = frame[frame["sale_days"].between(0, 2200)]
    frame["grant_date_dt"] = pd.to_datetime(frame["grant_date_dt"], utc=True, errors="coerce")
    frame["grant_year"] = frame["grant_date_dt"].dt.year
    frame["grant_month"] = frame["grant_date_dt"].dt.month
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["log_units"] = np.log1p(units.fillna(0))
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)
    frame["type_house"] = (description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)).astype(int)
    frame["description_lower"] = description.str.lower()
    frame["covid_era"] = frame["grant_year"].between(2020, 2021).astype(int)
    return frame.reset_index(drop=True)


def market_context(frame: pd.DataFrame, ppr: pd.DataFrame) -> pd.DataFrame:
    """County market state at grant date, computed from earlier PPR rows only."""
    ppr = ppr.copy()
    ppr["sale_date"] = pd.to_datetime(ppr["sale_date_dt"], utc=True, errors="coerce")
    ppr = ppr.dropna(subset=["sale_date", "price_num"])
    rows = []
    for _, scheme in frame.iterrows():
        grant = pd.Timestamp(scheme["grant_date_dt"])
        county = scheme["county_ppr"] if "county_ppr" in scheme.index else ""
        county_frame = ppr[ppr["county_norm"] == county]
        pre = county_frame[county_frame["sale_date"] < grant]
        recent = pre[pre["sale_date"] >= grant - pd.Timedelta(days=365)]
        older = pre[(pre["sale_date"] < grant - pd.Timedelta(days=180)) & (pre["sale_date"] >= grant - pd.Timedelta(days=365))]
        recent2 = pre[pre["sale_date"] >= grant - pd.Timedelta(days=180)]
        price_level = float(recent["price_num"].median()) if len(recent) >= 10 else np.nan
        volume = float(len(recent))
        momentum = (float(recent2["price_num"].median()) / float(older["price_num"].median()) - 1.0) if len(recent2) >= 10 and len(older) >= 10 else np.nan
        rows.append({"price_level": price_level, "volume_12m": volume, "momentum": momentum})
    context = pd.DataFrame(rows, index=frame.index)
    for column in context.columns:
        context[column] = context[column].fillna(context[column].median())
    return context


def county_name(authority: str) -> str:
    text = str(authority or "").lower()
    for county in ("carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
                   "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
                   "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
                   "waterford", "westmeath", "wexford", "wicklow"):
        if county in text:
            return county
    return ""


if __name__ == "__main__":
    frame = build_frame()
    frame["county_ppr"] = frame["PlanningAuthority"].map(county_name)
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    context = market_context(frame, ppr)
    frame = pd.concat([frame, context], axis=1)
    print(f"sold schemes with market context: {len(frame)}", flush=True)

    train = frame[frame["grant_year"] < 2021]
    test = frame[frame["grant_year"] >= 2021]
    print(f"train={len(train)}, test={len(test)}", flush=True)
    y_train = train["sale_days"].to_numpy()
    y_test = test["sale_days"].to_numpy()

    structured_cols = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month",
                       "covid_era", "price_level", "volume_12m", "momentum"]

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    X_train = np.hstack([train[structured_cols].fillna(0.0).values, text_train])
    X_test = np.hstack([test[structured_cols].fillna(0.0).values, text_test])

    report = {"split": "grant < 2021 train, >= 2021 holdout",
              "n": {"train": int(len(train)), "test": int(len(test))},
              "test_median_days": round(float(np.median(y_test)), 1)}

    for tau in (0.2, 0.5, 0.8):
        report[f"pinball_constant_p{int(tau * 100)}"] = round(pinball(y_test, np.full(len(y_test), np.quantile(y_train, tau)), tau), 1)

    strata = train.groupby(["PlanningAuthority", "grant_year"])["sale_days"].quantile([0.2, 0.5, 0.8]).unstack()
    strata.columns = ["q20", "q50", "q80"]
    strata_auth = train.groupby("PlanningAuthority")["sale_days"].quantile([0.2, 0.5, 0.8]).unstack()
    strata_auth.columns = ["q20a", "q50a", "q80a"]
    test = test.merge(strata.reset_index(), on=["PlanningAuthority", "grant_year"], how="left")
    test = test.merge(strata_auth.reset_index(), on="PlanningAuthority", how="left")
    for q, suffix in (("20", ""), ("50", ""), ("80", "")):
        test[f"strata_q{q}"] = test[f"q{q}"].fillna(test[f"q{q}a"]).fillna(np.quantile(y_train, float(q) / 100))
    for tau, q in ((0.2, "20"), (0.5, "50"), (0.8, "80")):
        report[f"pinball_strata_p{int(tau * 100)}"] = round(pinball(y_test, test[f"strata_q{q}"].to_numpy(), tau), 1)

    # Ridge on log-days with residual quantiles.
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train, np.log1p(y_train))
    log_pred = ridge.predict(X_test)
    residuals = np.log1p(y_train) - ridge.predict(X_train)
    for tau in (0.2, 0.5, 0.8):
        pred = np.maximum(np.expm1(log_pred + np.quantile(residuals, tau)), 1.0)
        report[f"pinball_ridge_p{int(tau * 100)}"] = round(pinball(y_test, pred, tau), 1)
        if tau == 0.5:
            report["ridge_mae"] = round(float(np.mean(np.abs(y_test - pred))), 1)

    # GBM quantiles with market context.
    gbm_preds = {}
    for tau in (0.2, 0.5, 0.8):
        gbm = GradientBoostingRegressor(loss="quantile", alpha=tau, n_estimators=250, max_depth=3,
                                        learning_rate=0.05, min_samples_leaf=10, random_state=RNG)
        gbm.fit(X_train, y_train)
        pred = np.maximum(gbm.predict(X_test), 1.0)
        gbm_preds[tau] = pred
        report[f"pinball_gbm_p{int(tau * 100)}"] = round(pinball(y_test, pred, tau), 1)
        if tau == 0.5:
            report["gbm_mae"] = round(float(np.mean(np.abs(y_test - pred))), 1)

    # Ablation: GBM without market context.
    for tau in (0.5,):
        gbm_no = GradientBoostingRegressor(loss="quantile", alpha=tau, n_estimators=250, max_depth=3,
                                           learning_rate=0.05, min_samples_leaf=10, random_state=RNG)
        cols_no_market = structured_cols[:6]
        gbm_no.fit(X_train[:, :6], y_train)
        pred_no = np.maximum(gbm_no.predict(X_test[:, :6]), 1.0)
        report["pinball_gbm_no_market_p50"] = round(pinball(y_test, pred_no, tau), 1)

    # Horizon classifier: P(sale within 24m), sold schemes only.
    y_train_h = (y_train > 730).astype(int)
    y_test_h = (y_test > 730).astype(int)
    clf = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
    clf.fit(X_train, y_train_h)
    p = np.clip(clf.predict_proba(X_test)[:, 1], 1e-6, 1 - 1e-6)
    lo, hi = bootstrap_auc(y_test_h, p, seed=0)
    report["horizon_730d"] = {
        "train_prevalence": round(float(y_train_h.mean()), 4),
        "test_prevalence": round(float(y_test_h.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y_test_h, p)), 4),
        "auc_ci_low": round(lo, 4),
        "auc_ci_high": round(hi, 4),
        "brier": round(float(brier_score_loss(y_test_h, p)), 4),
    }
    report["horizon_730d"].update(calibration_slope_intercept(y_test_h, p))

    out = settings.SILVER_DIR / "sale_timing_model_card.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
