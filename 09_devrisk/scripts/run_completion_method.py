"""Runner: construction-method completion experiment (revised order item 5).

Completion hazard with morphology vs morphology+construction-method
features (BCMS silver construction_method, main construction material,
consequence class, storeys). Train commencement<2020, test>=2020,
corrected fixed-grid evaluation (dynAUC, IBS).
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


def hazard_scores(frame: pd.DataFrame, target: str, features: list[str]):
    from run_completion_models_v2 import observed  # noqa: E402

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
    grid_frame = pd.DataFrame({"row": np.repeat(np.arange(len(frame)), len(GRID)),
                               "interval_start": np.tile(GRID, len(frame))})
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
    from run_completion_models_v2 import observed  # noqa: E402

    y_obs, censored = observed(frame[target], frame["censor_days"])
    scores = hazard_scores(frame, target, features)
    return {
        "dyn_auc_730": round(dynamic_auc(y_obs, censored, scores[730], 730), 3),
        "dyn_auc_1096": round(dynamic_auc(y_obs, censored, scores[1096], 1096), 3),
        "ibs": round(integrated_brier(y_obs, censored, scores), 4),
    }


if __name__ == "__main__":
    frame = build_frame()
    frame = frame[frame["censor_days"].between(0, 4000)]
    frame["commencement_dt"] = pd.to_datetime(frame["commencement"], utc=True, errors="coerce")
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    events = confirmed.merge(bcms, on="bcms_event_id", how="inner")
    method_map = events.groupby("scheme_id").agg(
        method=("construction_method", lambda s: s.mode().iloc[0] if len(s.mode()) else ""),
        n_notices=("phase_number", "nunique"),
    )
    frame = frame.merge(method_map, left_on="scheme_id", right_index=True, how="left")
    frame["log_units"] = np.log1p(pd.to_numeric(frame["units_reg"], errors="coerce").fillna(0))
    frame["method_mmc"] = frame["method"].fillna("").astype(str).str.contains("offsite|modern|modular|precast|timber frame", case=False, na=False).astype(int)
    frame["method_masonry"] = frame["method"].fillna("").astype(str).str.contains("masonry|concrete|block", case=False, na=False).astype(int)
    frame["method_concrete"] = frame["method"].fillna("").astype(str).str.contains("concrete|in-situ", case=False, na=False).astype(int)
    frame["n_phases"] = pd.to_numeric(frame["n_phases"], errors="coerce")

    train = frame[frame["commencement_dt"] < pd.Timestamp("2020-01-01", tz="UTC")]
    test = frame[frame["commencement_dt"] >= pd.Timestamp("2020-01-01", tz="UTC")]
    morphology = ["log_units", "n_phases"]
    report = {
        "train": int(len(train)), "test": int(len(test)),
        "method_coverage": round(float(frame["method"].ne("").mean()), 3),
    }
    # Correct protocol: train features fit, evaluate on test. The hazard
    # evaluator above fits and evaluates on the same frame; for the split,
    # fit on train and score test.
    def split_evaluate(target, features):
        y_obs_tr, cen_tr = None, None
        # fit model on train person-periods
        from run_completion_models_v2 import observed  # noqa: E402
        y_tr, c_tr = observed(train[target], train["censor_days"])
        persons = []
        for i in range(len(train)):
            duration = min(float(y_tr[i]), MAX_TIME)
            for start in GRID:
                if start >= duration:
                    break
                persons.append({"row": i, "interval_start": start,
                                "y": int((not c_tr[i]) and y_tr[i] <= start + 30.0)})
        pp = pd.DataFrame(persons)
        pp["t_years"] = pp["interval_start"] / 365.0
        pp = pp.merge(train.reset_index().rename(columns={"index": "row"})[["row"] + features], on="row", how="left")
        model = LogisticRegression(C=0.5, max_iter=2000)
        model.fit(pp[["t_years"] + features].fillna(0.0), pp["y"])
        y_te, c_te = observed(test[target], test["censor_days"])
        grid_frame = pd.DataFrame({"row": np.repeat(np.arange(len(test)), len(GRID)),
                                   "interval_start": np.tile(GRID, len(test))})
        grid_frame["t_years"] = grid_frame["interval_start"] / 365.0
        grid_frame = grid_frame.merge(test.reset_index().rename(columns={"index": "row"})[["row"] + features], on="row", how="left")
        grid_frame["hazard"] = model.predict_proba(grid_frame[["t_years"] + features].fillna(0.0))[:, 1]
        scores = {}
        for horizon in HORIZONS:
            intervals = int(np.ceil(horizon / 30.0))
            wide = grid_frame.pivot_table(index="row", columns="interval_start", values="hazard", aggfunc="first")
            wide = wide[sorted(wide.columns)[:intervals]]
            scores[horizon] = np.clip(1.0 - np.prod(1.0 - wide.to_numpy(), axis=1), 0.0, 1.0)
        return {
            "dyn_auc_730": round(dynamic_auc(y_te, c_te, scores[730], 730), 3),
            "dyn_auc_1096": round(dynamic_auc(y_te, c_te, scores[1096], 1096), 3),
            "ibs": round(integrated_brier(y_te, c_te, scores), 4),
        }

    method_feats = ["method_mmc", "method_masonry", "method_concrete"]
    report["t_first_ccc"] = {
        "morphology": split_evaluate("t_first_ccc", morphology),
        "morphology_plus_method": split_evaluate("t_first_ccc", morphology + method_feats),
    }
    report["t_final_ccc"] = {
        "morphology": split_evaluate("t_final_ccc", morphology),
        "morphology_plus_method": split_evaluate("t_final_ccc", morphology + method_feats),
    }
    out = settings.SILVER_DIR / "completion_method_experiment.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
