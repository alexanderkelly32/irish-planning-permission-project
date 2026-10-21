"""Runner: multi-state timeline engine (todo 4 + todo 3 route split).

Fits each transition from train-era schemes (grant < 2020), evaluates the
Monte Carlo timeline against the holdout (grant >= 2020), with milestones
from the event ledger / label pools. Also assigns delivery routes and fits
route-specific sale transitions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.multistate import evaluate_paths, fit_transition, route_of, simulate_timeline  # noqa: E402
from run_completion_models import build_frame as build_completion_frame  # noqa: E402

RNG = np.random.default_rng(7)
N_PATHS = 500


def build_master() -> pd.DataFrame:
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits", "ReceivedDate", "DecisionDate", "AreaofSite"]],
                         on="case_key", how="inner")
    frame = frame.merge(exit_labels[["scheme_id", "first_sale_date", "time_to_first_sale_from_grant_days"]],
                        left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    frame = frame.merge(completion[["scheme_id", "t_first_ccc", "t_final_ccc"]],
                        left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["decision_dt"] = pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce")
    frame["decision_days"] = (frame["decision_dt"] - frame["received_dt"]).dt.days
    frame["activation_days"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    frame["first_sale_days"] = pd.to_numeric(frame["time_to_first_sale_from_grant_days"], errors="coerce")
    frame["first_ccc_days"] = pd.to_numeric(frame["t_first_ccc"], errors="coerce")
    frame["final_ccc_days"] = pd.to_numeric(frame["t_final_ccc"], errors="coerce")
    frame["final_minus_first_days"] = frame["final_ccc_days"] - frame["first_ccc_days"]
    frame["first_sale_dt"] = pd.to_datetime(frame["first_sale_date"], utc=True, errors="coerce")
    frame["ccc_to_sale_days"] = (frame["first_sale_dt"] - frame["grant_dt"]).dt.days - frame["activation_days"] - frame["first_ccc_days"]
    frame["censor_days"] = (pd.Timestamp("2026-09-27", tz="UTC") - frame["grant_dt"]).dt.days
    frame["era"] = np.where(frame["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC"), "pre2020",
                            np.where(frame["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC"), "2020-21", "2022+"))
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["band"] = pd.cut(units, bins=[0, 29, 99, np.inf], labels=["10-29", "30-99", "100+"]).astype(str)
    description = frame["DevelopmentDescription"].fillna("")
    frame["type"] = np.where(description.str.contains("apartment|duplex", case=False, regex=True), "apartments",
                             np.where(description.str.contains(r"\bhouse", case=False, regex=True), "houses", "other"))
    frame["authority"] = frame["PlanningAuthority"].astype(str)
    frame["description"] = description
    frame["route"] = frame.apply(route_of, axis=1)
    return frame.dropna(subset=["grant_dt"])


if __name__ == "__main__":
    master = build_master()
    train = master[master["era"] == "pre2020"].copy()
    test = master[master["era"].isin(["2020-21", "2022+"])].copy()
    report = {"n": {"train": int(len(train)), "test": int(len(test))},
              "route_split": test["route"].value_counts().to_dict()}

    transitions = {}
    # decision: submission -> decision (days)
    transitions["decision"] = fit_transition(
        train.dropna(subset=["decision_days"]).assign(censor_days=lambda d: d["decision_days"].fillna(4000)),
        "decision_days", "decision_days", ["era", "authority"])
    # final permission: appeal-resolution extra for appealed schemes only
    appealed_train = train[train["appeal_submitted"].astype(bool)]
    transitions["final_permission"] = fit_transition(
        appealed_train.assign(censor_days=0.0), "decision_days", "decision_days", ["era"])
    # commencement: grant -> first commencement
    transitions["commencement"] = fit_transition(train, "activation_days", "activation_linked", ["era", "band", "type"])
    transitions["commencement"]["ever_rate"] = float(train["activation_linked"].astype(bool).mean())
    # first CCC from commencement
    transitions["first_ccc"] = fit_transition(
        train.assign(censor_days=train["censor_days"] - train["activation_days"].fillna(0)),
        "first_ccc_days", "first_ccc_days", ["era", "band"])
    # final CCC after first CCC
    transitions["units_completed"] = fit_transition(
        train.assign(censor_days=train["censor_days"] - train["activation_days"].fillna(0) - train["first_ccc_days"].fillna(0)),
        "final_minus_first_days", "final_minus_first_days", ["era"])
    # first sale: route-specific, measured from final CCC
    transitions["first_sale"] = {}
    for route, part in train.groupby("route"):
        transitions["first_sale"][route] = fit_transition(part, "ccc_to_sale_days", "ccc_to_sale_days", ["era"])
    report["transition_n"] = {
        name: {"occurrence_overall": trans["occurrence"]["overall"],
               "duration_overall": trans["duration_quantiles"]["overall"]}
        for name, trans in transitions.items() if name != "first_sale"
    }
    report["sale_route_transitions"] = {
        route: {"n": len(part), "q50": round(float(part["first_sale_days"].median()), 0)}
        for route, part in train.groupby("route") if len(part) >= 5
    }

    # Monte Carlo on the holdout.
    test = test.reset_index(drop=True)
    paths = []
    for _, row in test.iterrows():
        scheme_paths = []
        for _ in range(N_PATHS):
            scheme_paths.append(simulate_timeline(row, transitions, RNG))
        paths.append(scheme_paths)
    report["holdout_evaluation"] = evaluate_paths(paths, test)
    report["simulated_medians"] = {
        milestone: round(float(np.nanmedian([p[milestone] for path_list in paths for p in path_list if p[milestone] is not None])), 0)
        for milestone in ("decision", "commencement", "first_ccc", "units_completed", "first_sale")
    }

    out = settings.SILVER_DIR / "multistate_engine_v1.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
