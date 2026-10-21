"""Runner: completion models v2 - features + ablations (plan's 'easiest win').

Targets: commencement -> first CCC / 25% / 50% / final CCC, with feature
families ablated (morphology -> +developer -> +site). Corrected survival
evaluation (fixed-grid IPCW dynAUC, integrated Brier), Weibull AFT and
quantile GBM on observed durations.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import weibull_min  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.survival import dynamic_auc, integrated_brier, kaplan_meier  # noqa: E402
from run_completion_models import GRID, HORIZONS, MAX_TIME, build_frame  # noqa: E402

CENSOR = pd.Timestamp("2026-09-27", tz="UTC")


def observed(series: pd.Series, censor_days: pd.Series):
    y_obs = series.where(series.notna(), censor_days).clip(lower=0).to_numpy()
    censored = series.isna().to_numpy()
    return y_obs, censored


def hazard_scores(frame: pd.DataFrame, target: str, features: list[str]) -> dict[float, np.ndarray]:
    from sklearn.linear_model import LogisticRegression

    y_obs, censored = observed(frame[target], frame["censor_days"])
    persons = []
    for i in range(len(frame)):
        duration = min(float(y_obs[i]), MAX_TIME)
        for start in GRID:
            if start >= duration:
                break
            persons.append({"row": i, "interval_start": start,
                            "y": int((not censored[i]) and y_obs[i] <= start + 30.0)})
    pp = pd.DataFrame(persons)
    pp["t_years"] = pp["interval_start"] / 365.0
    pp = pp.merge(frame.reset_index().rename(columns={"index": "row"})[["row"] + features], on="row", how="left")
    model = LogisticRegression(C=0.5, max_iter=2000)
    model.fit(pp[["t_years"] + features].fillna(0.0), pp["y"])
    grid_frame = pd.DataFrame({
        "row": np.repeat(np.arange(len(frame)), len(GRID)),
        "interval_start": np.tile(GRID, len(frame)),
    })
    grid_frame["t_years"] = grid_frame["interval_start"] / 365.0
    grid_frame = grid_frame.merge(frame.reset_index().rename(columns={"index": "row"})[["row"] + features], on="row", how="left")
    grid_frame["hazard"] = model.predict_proba(grid_frame[["t_years"] + features].fillna(0.0))[:, 1]
    scores = {}
    for horizon in HORIZONS:
        intervals = int(np.ceil(horizon / 30.0))
        wide = grid_frame.pivot_table(index="row", columns="interval_start", values="hazard", aggfunc="first")
        wide = wide[sorted(wide.columns)[:intervals]]
        scores[horizon] = np.clip(1.0 - np.prod(1.0 - wide.to_numpy(), axis=1), 0.0, 1.0)
    return scores


def evaluate(frame: pd.DataFrame, target: str, features: list[str]) -> dict:
    y_obs, censored = observed(frame[target], frame["censor_days"])
    scores = hazard_scores(frame, target, features)
    out = {
        "n": int(len(frame)), "events": int((~censored).sum()),
        "dyn_auc": {str(h): round(dynamic_auc(y_obs, censored, scores[h], h), 3) for h in HORIZONS},
        "ibs": round(integrated_brier(y_obs, censored, scores), 4),
    }
    observed_part = frame[frame[target].notna()]
    if len(observed_part) >= 30 and features:
        y = observed_part[target].to_numpy()
        shape, loc, scale = weibull_min.fit(y, floc=0)
        out["weibull_mae_constant"] = round(float(np.mean(np.abs(y - weibull_min.median(shape, loc=loc, scale=scale)))), 0)
        X = observed_part[features].fillna(0.0).to_numpy()
        gbm = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=200, max_depth=3,
                                        learning_rate=0.05, min_samples_leaf=10, random_state=7)
        gbm.fit(X, y)
        pred = np.maximum(gbm.predict(X), 1.0)
        out["gbm_in_sample_mae"] = round(float(np.mean(np.abs(y - pred))), 0)
    elif len(observed_part) >= 30:
        y = observed_part[target].to_numpy()
        shape, loc, scale = weibull_min.fit(y, floc=0)
        out["weibull_mae_constant"] = round(float(np.mean(np.abs(y - weibull_min.median(shape, loc=loc, scale=scale)))), 0)
    return out


if __name__ == "__main__":
    base = build_frame()
    base = base[base["censor_days"].between(0, 4000)]
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    register_map = register[["case_key", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    frame = base.merge(register_map, left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    frame = frame.merge(applicants, left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    frame = frame.merge(constraints, left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["log_units"] = np.log1p(units.fillna(0))
    frame["band"] = pd.cut(units, bins=[0, 29, 99, np.inf], labels=["10-29", "30-99", "100+"]).astype(str)
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_house"] = description.str.contains(r"\b(?:house|houses|dwelling)\b", case=False, regex=True).astype(int)
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)

    morphology = ["log_units", "type_house", "type_apartment", "n_phases"]
    developer = ["applicant_prior_n", "applicant_prior_grant_rate", "applicant_prior_median_activation", "has_applicant"]
    site = ["fluvial_hit_any", "coastal_hit_any", "niah_min_dist", "natura_min_dist"]

    report = {"n_schemes": int(len(frame))}
    for family_name, features in (("time_only", []), ("morphology", morphology),
                                  ("morphology+developer", morphology + developer),
                                  ("all_families", morphology + developer + site)):
        report[family_name] = {}
        for target in ("t_first_ccc", "t_final_ccc"):
            report[family_name][target] = evaluate(frame, target, features)

    out = settings.SILVER_DIR / "completion_models_v2.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
