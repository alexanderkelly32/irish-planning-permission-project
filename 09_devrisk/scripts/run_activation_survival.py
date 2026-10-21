"""Runner: activation survival baselines + discrete-time hazard model.

Snapshot: final grant (brief section 6). Durations: final grant -> first
confirmed commencement; unlinked schemes right-censored at censor date.
Baselines: KM overall / by size band / by COVID regime exposure; then a
discrete-time logistic hazard with scheme features, interval index and
time-varying COVID regime flags; optional final-grant friction features
(FI/appeal/planning duration) for the Sprint 7 ablation question.

Split by grant year: train < 2020, test >= 2021. Reports c-index, IPCW Brier
at 12/24/36m, time-dependent AUC at 24m, and calibration of P(commence by 24m).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.labels.activation import _parse_date, days_between  # noqa: E402
from devrisk.models.hazard import (  # noqa: E402
    REGIME_INTERVALS,
    brier_ipcw,
    build_person_periods,
    concordance_index,
    fit_hazard,
    predict_horizon_probabilities,
    time_dependent_auc,
)
from devrisk.models.survival import kaplan_meier, km_probability_by, median_survival_time  # noqa: E402

CENSOR_DATE = "2026-09-27"
HORIZONS = (365, 730, 1096)


def regime_flag_for_interval(start: pd.Timestamp, end: pd.Timestamp) -> str:
    date = start.date()
    for name, regime_start, regime_end in REGIME_INTERVALS:
        if regime_start <= date <= regime_end:
            return name
    return "none"


if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv")
    labels = labels.rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    cohort = register[["case_key", "PlanningAuthority", "NumResidentialUnits", "AreaofSite", "DevelopmentDescription", "GrantDate"]].copy()
    frame = labels.merge(cohort, on="case_key", how="inner").drop_duplicates("case_key").copy()
    frame["grant_date_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["censor_dt"] = pd.Timestamp(CENSOR_DATE, tz="UTC")
    frame["duration_days"] = np.where(
        frame["activation_linked"].astype(bool),
        frame["activation_days"],
        (frame["censor_dt"] - frame["grant_date_dt"]).dt.days,
    ).astype(float)
    frame = frame.dropna(subset=["grant_date_dt"])
    frame["event"] = frame["activation_linked"].astype(int)
    negative_durations = int((frame["duration_days"] < 0).sum())
    frame["commencement_before_grant"] = (frame["duration_days"] < 0).astype(int)
    frame["duration_days"] = frame["duration_days"].clip(lower=0.0)
    print(f"exceptional commencements before grant (clipped to 0): {negative_durations}", flush=True)

    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    area = pd.to_numeric(frame["AreaofSite"], errors="coerce")
    frame["log_units"] = np.log1p(units.fillna(0))
    frame["density"] = (units / area * 10000.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)
    frame["type_house"] = (description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)).astype(int)
    frame["grant_year"] = frame["grant_date_dt"].dt.year.astype(float)
    frame["covid_exposed_grant"] = frame["grant_year"].between(2019, 2021).astype(int)
    frame["fi_at_grant"] = frame["fi_requested"].fillna(False).astype(int)
    frame["appeal_at_grant"] = frame["appeal_submitted"].fillna(False).astype(int)
    frame["planning_duration"] = frame["planning_duration_days"].fillna(0.0)

    baseline_cols = ["log_units", "density", "type_apartment", "type_house", "grant_year",
                     "covid_exposed_grant", "fi_at_grant", "appeal_at_grant", "planning_duration"]
    frame = frame.dropna(subset=baseline_cols + ["duration_days"])

    train = frame[frame["grant_date_dt"] < pd.Timestamp("2020-01-01", tz="UTC")]
    test = frame[frame["grant_date_dt"] >= pd.Timestamp("2021-01-01", tz="UTC")]
    print(f"train={len(train)}, test={len(test)}, events train={train['event'].sum()}, test={test['event'].sum()}", flush=True)

    report: dict[str, object] = {"split": "grant < 2020 train, grant >= 2021 test",
                                 "n": {"train": int(len(train)), "test": int(len(test))}}

    for name, part in [("train", train), ("test", test)]:
        km = kaplan_meier(part["duration_days"].to_numpy(), part["event"].to_numpy())
        report[f"km_{name}"] = {
            "median_days": median_survival_time(km),
            "p_by_12m": round(km_probability_by(km, 365), 3),
            "p_by_24m": round(km_probability_by(km, 730), 3),
            "p_by_36m": round(km_probability_by(km, 1096), 3),
        }
    strata = {}
    for band, part in frame.groupby(pd.cut(units, bins=[-np.inf, 29, 99, 249, np.inf], labels=["10-29", "30-99", "100-249", "250+"]), observed=False):
        km = kaplan_meier(part["duration_days"].to_numpy(), part["event"].to_numpy())
        strata.setdefault("size_band", {})[str(band)] = round(km_probability_by(km, 730), 3)
    report["km_strata"] = strata

    feature_cols = ["interval_index", "t_start", "broad_closure", "phased_reopening"] + baseline_cols
    pp_train = build_person_periods(train["duration_days"].to_numpy(), train["event"].to_numpy(),
                                    start_dates=train["grant_date_dt"].to_numpy(), features=train[baseline_cols].reset_index(drop=True))
    pp_test = build_person_periods(test["duration_days"].to_numpy(), test["event"].to_numpy(),
                                   start_dates=test["grant_date_dt"].to_numpy(), features=test[baseline_cols].reset_index(drop=True))
    model = fit_hazard(pp_train, feature_cols, C=0.5)
    print(f"person-periods train={len(pp_train)}, test={len(pp_test)}", flush=True)

    risk_train = model.predict_proba(pp_train[feature_cols])[:, 1]
    risk_test = model.predict_proba(pp_test[feature_cols])[:, 1]
    # subject-level risk = max interval hazard (proxy)
    train_risk = pp_train.groupby("unit")[pp_train.columns[-1]].max().reindex(range(len(train))).fillna(0).to_numpy() if False else None
    interval_col = model.predict_proba(pp_test[feature_cols])[:, 1]
    test_risk_by_unit = pd.Series(interval_col).groupby(pp_test["unit"]).max().reindex(range(len(test))).fillna(0).to_numpy()
    train_risk_by_unit = pd.Series(risk_train).groupby(pp_train["unit"]).max().reindex(range(len(train))).fillna(0).to_numpy()

    report["concordance_train"] = round(concordance_index(train["duration_days"].to_numpy(), train["event"].to_numpy(), train_risk_by_unit), 4)
    report["concordance_test"] = round(concordance_index(test["duration_days"].to_numpy(), test["event"].to_numpy(), test_risk_by_unit), 4)

    probs_test = predict_horizon_probabilities(model, test[baseline_cols].reset_index(drop=True),
                                               feature_columns=feature_cols,
                                               origins=test["grant_date_dt"].to_numpy(), horizons=HORIZONS)
    for idx, horizon in enumerate(HORIZONS):
        surv = 1.0 - probs_test[:, idx]
        report[f"brier_ipcw_{horizon}d"] = round(brier_ipcw(test["duration_days"].to_numpy(), test["event"].to_numpy(), surv, horizon), 4)
    report["td_auc_730d"] = round(time_dependent_auc(test["duration_days"].to_numpy(), test["event"].to_numpy(), test_risk_by_unit, 730.0), 4)

    # calibration of P(commence by 24m) vs observed KM within predicted terciles
    test_scored = test.copy()
    test_scored["p_24m"] = probs_test[:, 1]
    km_overall_24m = km_probability_by(kaplan_meier(test["duration_days"].to_numpy(), test["event"].to_numpy()), 730)
    cal_rows = []
    for tercile, part in test_scored.groupby(pd.qcut(test_scored["p_24m"].rank(method="first"), 3, labels=False), observed=False):
        km = kaplan_meier(part["duration_days"].to_numpy(), part["event"].to_numpy())
        cal_rows.append({
            "tercile": int(tercile), "n": int(len(part)),
            "mean_predicted_p24m": round(float(part["p_24m"].mean()), 3),
            "observed_p24m": round(km_probability_by(km, 730), 3),
        })
    report["calibration_terciles_24m"] = cal_rows
    report["km_overall_test_p24m"] = round(km_overall_24m, 3)
    report["mean_predicted_p24m_test"] = round(float(test_scored["p_24m"].mean()), 3)

    out = settings.SILVER_DIR / "activation_survival_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
