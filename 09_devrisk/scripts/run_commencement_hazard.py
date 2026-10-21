"""Runner: censoring-aware discrete-time hazard for commencement timing.

Continuous alternative to the conditional quantile CDF: person-period
logistic hazard over the FULL mature pool - commenced schemes are events at
activation_days, unlinked schemes right-censored at the censor date. Produces
P(T <= t) for any horizon including the never/slow-start mass the conditional
model discards. Evaluated with time-dependent AUC + Brier vs KM baseline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.survival import kaplan_meier, km_probability_by  # noqa: E402

CENSOR = pd.Timestamp("2026-09-27", tz="UTC")
INTERVAL = 30.0
MAX_TIME = 2000.0
HORIZONS = [365, 548, 730, 913, 1096, 1461, 1826]


def build_person_periods(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, scheme in frame.iterrows():
        t_event = scheme["activation"]
        grant = scheme["grant_dt"]
        censor_t = (CENSOR - grant).days
        observed = not pd.isna(t_event)
        duration = min(float(t_event) if observed else float(censor_t), MAX_TIME)
        if duration <= 0:
            continue
        for start in np.arange(0.0, duration, INTERVAL):
            end = min(start + INTERVAL, duration)
            if end <= start:
                break
            y = int(observed and t_event <= start + INTERVAL)
            rows.append({
                "scheme_id": scheme["scheme_id"],
                "interval_start": start,
                "y": y,
            })
            if y:
                break
    return pd.DataFrame(rows)


if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite"]], on="case_key", how="inner")
    frame["scheme_id"] = frame["case_key"].astype(str)
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    frame = frame.dropna(subset=["grant_dt"]).copy()
    frame = frame[frame["grant_dt"] < CENSOR - pd.Timedelta(days=180)].copy()

    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    site = pd.to_numeric(frame["AreaofSite"], errors="coerce")
    frame["log_units"] = np.log1p(units.fillna(0))
    frame["log_site_area"] = np.log1p(site.fillna(0))
    frame["density"] = (units / site * 10000.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    frame["grant_year"] = frame["grant_dt"].dt.year
    frame["covid_era"] = frame["grant_year"].between(2020, 2021).astype(int)
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_house"] = description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True)

    train = frame[frame["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC")].reset_index(drop=True)
    test = frame[frame["grant_dt"] >= pd.Timestamp("2020-01-01", tz="UTC")].reset_index(drop=True)
    print(f"pool: train={len(train)} (events {train['activation'].notna().sum()}), test={len(test)} (events {test['activation'].notna().sum()})", flush=True)

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=4000, sublinear_tf=True, stop_words="english", min_df=3)
    tfidf.fit(description.str.lower())

    structured_cols = ["log_units", "log_site_area", "density", "grant_year", "covid_era", "type_house", "type_apartment"]

    pp_train = build_person_periods(train)
    pp_test = build_person_periods(test)
    pp_train = pp_train.merge(train[["scheme_id"] + structured_cols], on="scheme_id", how="left")
    pp_test = pp_test.merge(test[["scheme_id"] + structured_cols], on="scheme_id", how="left")
    pp_train = pp_train.merge(train[["scheme_id", "PlanningAuthority"]], on="scheme_id", how="left")
    pp_test = pp_test.merge(test[["scheme_id", "PlanningAuthority"]], on="scheme_id", how="left")
    pp_train["t_years"] = pp_train["interval_start"] / 365.0
    pp_test["t_years"] = pp_test["interval_start"] / 365.0

    X_train = pd.get_dummies(pp_train[["log_units", "log_site_area", "density", "grant_year", "covid_era",
                                       "type_house", "type_apartment", "t_years", "PlanningAuthority"]],
                             columns=["PlanningAuthority"], dummy_na=False)
    X_test = pp_test[["log_units", "log_site_area", "density", "grant_year", "covid_era",
                      "type_house", "type_apartment", "t_years", "PlanningAuthority"]]
    X_test = pd.get_dummies(X_test, columns=["PlanningAuthority"], dummy_na=False).reindex(columns=X_train.columns, fill_value=0)
    y_train_pp = pp_train["y"].to_numpy()
    y_test_pp = pp_test["y"].to_numpy()

    model = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
    model.fit(X_train, y_train_pp)
    pp_test = pp_test.copy()
    pp_test["hazard"] = model.predict_proba(X_test)[:, 1]
    print(f"person-periods: train {len(pp_train)}, test {len(pp_test)}", flush=True)

    # Per-scheme P(T <= horizon): accumulate hazard only over intervals below
    # the horizon (standard discrete-time horizon probability).
    def scheme_probability(group: pd.DataFrame, horizon: float) -> float:
        ordered = group.sort_values("interval_start")
        incidence = 0.0
        survival = 1.0
        for _, row in ordered.iterrows():
            if row["interval_start"] >= horizon:
                break
            incidence += survival * row["hazard"]
            survival *= (1.0 - row["hazard"])
        return float(incidence)

    pp_test = pp_test.copy()
    km_durations = train["activation"].copy()
    km_durations = km_durations.mask(km_durations.isna(), (CENSOR - train["grant_dt"]).dt.days)
    km = kaplan_meier(km_durations.to_numpy(), train["activation"].notna().astype(int).to_numpy())

    report = {"model": "commencement_discrete_hazard_v2", "n": {"train": int(len(train)), "test": int(len(test))},
              "person_periods": {"train": int(len(pp_train)), "test": int(len(pp_test))}}
    report["td_auc"] = {}
    report["brier"] = {}
    for horizon in HORIZONS:
        incidence = pp_test.groupby("scheme_id").apply(lambda g, h=horizon: scheme_probability(g, h), include_groups=False)
        test["incidence"] = test["scheme_id"].map(incidence).fillna(0.0)
        y_h = test["activation"].le(horizon).astype(int)
        km_p = km_probability_by(km, horizon)
        p = test["incidence"].clip(1e-6, 1 - 1e-6)
        report["td_auc"][str(horizon)] = round(float(roc_auc_score(y_h, test["incidence"])), 4) if y_h.nunique() == 2 else None
        report["brier"][str(horizon)] = {
            "prevalence": round(float(y_h.mean()), 4),
            "mean_predicted": round(float(test["incidence"].mean()), 4),
            "brier_hazard": round(float(brier_score_loss(y_h, p)), 4),
            "brier_km": round(float(brier_score_loss(y_h, np.full(len(y_h), km_p))), 4),
        }
    (settings.SILVER_DIR / "commencement_hazard_v2.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
