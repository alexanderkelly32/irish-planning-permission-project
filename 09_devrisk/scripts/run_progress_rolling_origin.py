"""Rolling-origin validation of the progress-based construction model.

Re-runs the elapsed+progress GBM vs the best simple baseline (elapsed-band
median) across several historical train/test cutoffs (commencement-year
splits). The 11.7% gain must survive multiple periods, not one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "construction_progress"

FEATS = ["elapsed_days", "cum_pct", "n_ccc_to_date", "days_since_last_ccc",
         "velocity_90d", "units_remaining"]


def mae(y, p):
    return float(np.mean(np.abs(y - p)))


def main() -> None:
    snaps = pd.read_csv(OUT / "construction_progress_snapshots.csv")
    snaps = snaps.dropna(subset=["target_final_ccc_days"])
    snaps = snaps[(snaps["target_final_ccc_days"] >= 0) & (snaps["target_final_ccc_days"] <= 4000)]
    events = pd.read_csv(OUT / "construction_progress_events.csv")
    comm_year = events.groupby("case_key")["comm_dt"].min().map(lambda d: pd.to_datetime(d).year)
    snaps["comm_year"] = snaps["case_key"].map(comm_year)

    report = {"cutoffs": {}}
    for cutoff in (2020, 2021, 2022, 2023):
        train = snaps[snaps["comm_year"] < cutoff]
        test = snaps[(snaps["comm_year"] >= cutoff) & (snaps["comm_year"] <= cutoff + 1)]
        if len(train) < 200 or len(test) < 40:
            continue
        y_tr = train["target_final_ccc_days"].to_numpy()
        y_te = test["target_final_ccc_days"].to_numpy()
        train["elapsed_band"] = pd.cut(train["elapsed_days"], [0, 90, 180, 365, 730, 5000],
                                       labels=["0-90", "90-180", "180-365", "365-730", "730+"])
        test["elapsed_band"] = pd.cut(test["elapsed_days"], [0, 90, 180, 365, 730, 5000],
                                      labels=["0-90", "90-180", "180-365", "365-730", "730+"])
        em = train.groupby("elapsed_band")["target_final_ccc_days"].median().to_dict()
        p_base = test["elapsed_band"].astype(str).map(em).fillna(np.median(y_tr)).to_numpy()
        gbm = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=300,
                                        max_depth=3, learning_rate=0.05,
                                        min_samples_leaf=20, random_state=7)
        gbm.fit(train[FEATS].fillna(0.0), y_tr)
        p_gbm = np.maximum(gbm.predict(test[FEATS].fillna(0.0)), 0.0)
        m_base, m_gbm = mae(y_te, p_base), mae(y_te, p_gbm)
        report["cutoffs"][f"train<{cutoff}_test{cutoff}-{cutoff + 1}"] = {
            "n_train": int(len(train)), "n_test": int(len(test)),
            "baseline_mae": round(m_base, 1), "progress_mae": round(m_gbm, 1),
            "gain_pct": round((1 - m_gbm / m_base) * 100, 1),
        }
    (OUT / "construction_progress_rolling_origin.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
