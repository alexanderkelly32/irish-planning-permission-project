"""Runner: temporal-split validation of the completion-model feature gain.

The v2 hazard dynAUC gains (12m 0.478->0.611 with morphology) were
in-sample. Confirm out-of-sample: train commencement <2020, test >=2020,
same feature families, corrected evaluation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.survival import dynamic_auc, integrated_brier  # noqa: E402
from run_completion_models import GRID, HORIZONS, MAX_TIME, build_frame  # noqa: E402


def split_hazard(train: pd.DataFrame, test: pd.DataFrame, target: str, features: list[str]):
    def person_periods(part: pd.DataFrame):
        rows = []
        for i, scheme in part.iterrows():
            duration = min(float(scheme["y_obs"]), MAX_TIME)
            for start in GRID:
                if start >= duration:
                    break
                rows.append({"row": i, "interval_start": start,
                             "y": int((not scheme["censored"]) and scheme["y_obs"] <= start + 30.0)})
        return pd.DataFrame(rows)

    def obs(part: pd.DataFrame):
        y = part[target].where(part[target].notna(), part["censor_days"]).clip(lower=0)
        censored = part[target].isna()
        part = part.copy()
        part["y_obs"] = y.to_numpy()
        part["censored"] = censored.to_numpy()
        return part

    train = obs(train)
    test = obs(test)
    pp_train = person_periods(train)
    pp_train["t_years"] = pp_train["interval_start"] / 365.0
    pp_train = pp_train.merge(train.reset_index().rename(columns={"index": "row"})[["row"] + features], on="row", how="left")
    pp_test_frame = person_periods(test)
    pp_test_frame["t_years"] = pp_test_frame["interval_start"] / 365.0
    pp_test_frame = pp_test_frame.merge(test.reset_index().rename(columns={"index": "row"})[["row"] + features], on="row", how="left")

    model = LogisticRegression(C=0.5, max_iter=2000)
    model.fit(pp_train[["t_years"] + features].fillna(0.0), pp_train["y"])

    grid_frame = pd.DataFrame({
        "row": np.repeat(np.arange(len(test)), len(GRID)),
        "interval_start": np.tile(GRID, len(test)),
    })
    grid_frame["t_years"] = grid_frame["interval_start"] / 365.0
    grid_frame = grid_frame.merge(test.reset_index().rename(columns={"index": "row"})[["row"] + features], on="row", how="left")
    grid_frame["hazard"] = model.predict_proba(grid_frame[["t_years"] + features].fillna(0.0))[:, 1]
    scores = {}
    for horizon in HORIZONS:
        intervals = int(np.ceil(horizon / 30.0))
        wide = grid_frame.pivot_table(index="row", columns="interval_start", values="hazard", aggfunc="first")
        wide = wide[sorted(wide.columns)[:intervals]]
        scores[horizon] = np.clip(1.0 - np.prod(1.0 - wide.to_numpy(), axis=1), 0.0, 1.0)
    y_obs = test["y_obs"].to_numpy()
    censored = test["censored"].to_numpy(dtype=bool)
    return {
        "dyn_auc": {str(h): round(dynamic_auc(y_obs, censored, scores[h], h), 3) for h in HORIZONS},
        "ibs": round(integrated_brier(y_obs, censored, scores), 4),
        "n_test": int(len(test)),
    }


if __name__ == "__main__":
    base = build_frame()
    base = base[base["censor_days"].between(0, 4000)]
    base["commencement_dt"] = pd.to_datetime(base["commencement"], utc=True, errors="coerce")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    reg_map = register[["case_key", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    frame = base.merge(reg_map, left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    frame = frame.merge(applicants, left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    frame = frame.merge(constraints, left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["log_units"] = np.log1p(units.fillna(0))
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_house"] = description.str.contains(r"\b(?:house|houses|dwelling)\b", case=False, regex=True).astype(int)
    frame["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True).astype(int)

    train = frame[frame["commencement_dt"] < pd.Timestamp("2020-01-01", tz="UTC")]
    test = frame[frame["commencement_dt"] >= pd.Timestamp("2020-01-01", tz="UTC")]
    morphology = ["log_units", "type_house", "type_apartment", "n_phases"]
    developer = ["applicant_prior_n", "applicant_prior_grant_rate", "applicant_prior_median_activation", "has_applicant"]
    site = ["fluvial_hit_any", "coastal_hit_any", "niah_min_dist", "natura_min_dist"]

    report = {"train": int(len(train)), "test": int(len(test))}
    for family, features in (("time_only", []), ("morphology", morphology),
                             ("morphology+developer", morphology + developer),
                             ("all_families", morphology + developer + site)):
        report[family] = split_hazard(train, test, "t_first_ccc", features)

    out = settings.SILVER_DIR / "completion_models_v2_split.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
