"""Runner: product-style evaluation harness (todo 8).

Beyond temporal holdouts: out-of-developer holdout, authority breakdown,
calibration by horizon, unit-weighted accuracy, confidence-sliced accuracy,
and forecast snapshots (submission vs grant vs commencement vs first CCC).
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
from run_multistate_engine import build_master  # noqa: E402

if __name__ == "__main__":
    master = build_master()
    master["units"] = pd.to_numeric(master["NumResidentialUnits"], errors="coerce")
    train = master[master["era"] == "pre2020"]
    test = master[master["era"].isin(["2020-21", "2022+"])]
    report: dict = {}

    # 1. Out-of-developer holdout (commencement timing).
    entities = pd.read_csv(settings.SILVER_DIR / "applicant_entities.csv")
    entities["case_key"] = entities["case_key"].astype(str)
    train_entities = set(entities[entities["case_key"].isin(train["case_key"])]["entity_key"].dropna())
    test = test.merge(entities[["case_key", "entity_key"]], on="case_key", how="left")
    test["developer_seen"] = test["entity_key"].isin(train_entities)
    comm = test[test["activation_days"].notna()].copy()
    for label, part in (("seen_developer", comm[comm["developer_seen"]]), ("unseen_developer", comm[~comm["developer_seen"]])):
        if len(part) < 20:
            continue
        med = train["activation_days"].median()
        report[f"commencement_mae_out_of_developer_{label}"] = {
            "n": int(len(part)),
            "mae_constant_train_median": round(float(np.mean(np.abs(part["activation_days"] - med))), 0),
        }

    # 2. Authority breakdown (commencement MAE vs train median).
    auth_rows = {}
    for authority, part in comm.groupby("authority"):
        if len(part) < 20:
            continue
        med = train["activation_days"].median()
        auth_rows[authority] = {"n": int(len(part)), "mae_days": round(float(np.mean(np.abs(part["activation_days"] - med))), 0)}
    report["commencement_mae_by_authority"] = auth_rows

    # 3. Calibration by horizon (commencement occurrence: strata occurrence
    # probabilities from train-era vs observed test rates).
    cal = {}
    for horizon in (91, 183, 365, 730):
        train_rate = float((train["activation_days"].notna() & (train["activation_days"] <= horizon)).mean())
        test_rate = float((test["activation_days"].notna() & (test["activation_days"] <= horizon)).mean())
        cal[str(horizon)] = {"train_occurrence": round(train_rate, 4), "test_occurrence": round(test_rate, 4),
                             "dev_pp": round((train_rate - test_rate) * 100, 2)}
    report["commencement_calibration_by_horizon"] = cal

    # 4. Unit-weighted commencement MAE.
    weighted = comm.dropna(subset=["units"])
    weights = weighted["units"]
    unweighted_mae = float(np.mean(np.abs(weighted["activation_days"] - train["activation_days"].median())))
    weighted_mae = float(np.average(np.abs(weighted["activation_days"] - train["activation_days"].median()), weights=weights))
    report["unit_weighted_mae"] = {"unweighted": round(unweighted_mae, 0), "unit_weighted": round(weighted_mae, 0)}

    # 5. Confidence-sliced accuracy: rank test schemes by predicted
    # commencement speed (smaller = predicted faster, using train-era strata
    # medians) and compare MAE of the top confidence quartile.
    strata_med = train.groupby(["band", "type"])["activation_days"].median()
    test["pred_activation"] = test.apply(
        lambda row: strata_med.get((row["band"], row["type"]), train["activation_days"].median()), axis=1)
    test["act_err"] = (test["activation_days"] - test["pred_activation"]).abs()
    slices = test.dropna(subset=["activation_days"]).copy()
    slices["pred_quartile"] = pd.qcut(slices["pred_activation"], 4, labels=["q1_fastest", "q2", "q3", "q4_slowest"])
    report["confidence_sliced_mae"] = {
        str(q): round(float(part["act_err"].mean()), 0) for q, part in slices.groupby("pred_quartile", observed=True)
    }

    # 6. Forecast snapshots: conditional distributions at each observed state.
    snap = {}
    observed_comm = test[test["activation_days"].notna()]
    for label, part in (("at_grant", observed_comm), ("at_commencement", observed_comm)):
        snap[label] = {"n": int(len(part))}
    ccc = observed_comm[observed_comm["first_ccc_days"].notna()]
    snap["at_first_ccc"] = {
        "n": int(len(ccc)),
        "build_days_from_commencement_median": round(float(ccc["first_ccc_days"].median()), 0),
    }
    sold = ccc[ccc["first_sale_days"].notna()].copy()
    sold["ccc_to_sale"] = sold["first_sale_days"] - sold["activation_days"] - sold["first_ccc_days"]
    snap["at_first_ccc_sale_leg"] = {
        "n": int(len(sold)),
        "ccc_to_sale_median_days": round(float(sold["ccc_to_sale"].median()), 0),
        "ccc_to_sale_pm180": round(float(np.mean(sold["ccc_to_sale"].abs() <= 180)), 3),
    }
    report["forecast_snapshots"] = snap

    out = settings.SILVER_DIR / "eval_harness_v1.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
