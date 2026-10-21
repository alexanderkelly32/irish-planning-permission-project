"""Runner: commencement-timing era recalibration experiment.

The pre-2020 strata applied to post-2020 grants overpredicts (MAE 469d vs a
380d floor). Test deployable recalibrations on the holdout (grant >= 2020):
  A. constant: pre-2020 global median (current baseline)
  B. rolling: median activation of schemes granted in the prior 24 months
     (time-safe at grant date)
  C. shrunk strata: authority median shrunk toward the rolling global median
  D. oracle: test-era realized median (upper bound, not deployable)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402


def mae(y, pred):
    return round(float(np.mean(np.abs(y - pred))), 1)


if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate"]], on="case_key", how="inner")
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    comm = frame[frame["activation_linked"].astype(bool)].dropna(subset=["activation", "grant_dt"])
    comm = comm.sort_values("grant_dt").reset_index(drop=True)

    train = comm[comm["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2020-01-01", tz="UTC")]
    y_train = train["activation"].to_numpy()
    y_test = test["activation"].to_numpy()
    print(f"train={len(train)}, test={len(test)}, test median {np.median(y_test):.0f}d", flush=True)

    report = {"n_test": int(len(test))}

    # A: constant (pre-2020 global median)
    const = float(np.median(y_train))
    report["A_constant_pre2020_median"] = {"mae": mae(y_test, np.full(len(y_test), const)), "prediction": const}

    # B: rolling 24-month median (time-safe at each grant date)
    roll_preds = []
    for _, row in test.iterrows():
        window = comm[(comm["grant_dt"] < row["grant_dt"]) & (comm["grant_dt"] >= row["grant_dt"] - pd.Timedelta(days=730))]
        roll_preds.append(float(window["activation"].median()) if len(window) >= 5 else const)
    report["B_rolling_24m_median"] = {"mae": mae(y_test, np.asarray(roll_preds)), "n_fallback_to_const": int(sum(1 for p in roll_preds if p == const))}

    # C: authority median shrunk toward rolling global median
    auth_med = train.groupby("PlanningAuthority")["activation"].median()
    shrunk = []
    for _, row in test.iterrows():
        auth_p = float(auth_med.get(row["PlanningAuthority"], const))
        window = comm[(comm["grant_dt"] < row["grant_dt"]) & (comm["grant_dt"] >= row["grant_dt"] - pd.Timedelta(days=730))]
        roll_p = float(window["activation"].median()) if len(window) >= 5 else const
        shrunk.append(0.5 * auth_p + 0.5 * roll_p)
    report["C_shrunk_authority_rolling"] = {"mae": mae(y_test, np.asarray(shrunk))}

    # D: oracle test-era median (upper bound)
    oracle = float(np.median(y_test))
    report["D_oracle_test_median"] = {"mae": mae(y_test, np.full(len(y_test), oracle)), "prediction": oracle}

    out = settings.SILVER_DIR / "commencement_recalibration.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
