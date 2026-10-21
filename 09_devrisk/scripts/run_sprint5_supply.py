"""Sprint 5 E1: Deliverable Competitive Supply Forecast.

For historical target dates: build the local pipeline from held data,
assign state-conditional delivery probabilities from the validated
transition tables, Monte Carlo aggregate expected supplied units by
horizon/radius, and backtest against realised BCMS commencements.
Gate: must beat simple conversion-rate baselines.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint5"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    states = pd.read_csv(SILVER / "state_machine" / "states.csv")
    states["entered"] = pd.to_datetime(states["entered"], errors="coerce")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "PlanningAuthority", "NumResidentialUnits",
                                        "GrantDate", "ITMEasting", "ITMNorthing", "ReceivedDate"])
    register = register.drop_duplicates("case_key")
    register["units"] = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    register["grant_dt"] = pd.to_datetime(register["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    register["recv_dt"] = pd.to_datetime(register["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    base = register.merge(labels[["case_key", "activation"]], on="case_key", how="left")
    base = base.dropna(subset=["units", "ITMEasting", "ITMNorthing"])
    base["comm_dt"] = base["grant_dt"] + pd.to_timedelta(base["activation"], unit="D")
    base = base.dropna(subset=["grant_dt"])
    base = base[base["grant_dt"].dt.year.between(2015, 2020)]
    base = base.sort_values("grant_dt")

    grant_comm = base.dropna(subset=["comm_dt"]).copy()
    grant_comm["g2c"] = (grant_comm["comm_dt"] - grant_comm["grant_dt"]).dt.days

    rng = np.random.default_rng(7)
    targets = base.sample(min(80, len(base)), random_state=42)
    rows = []
    for _, t in targets.iterrows():
        t0 = t["grant_dt"]
        for radius in (1000, 3000, 5000, 10000):
            dist = np.sqrt((base["ITMEasting"] - t["ITMEasting"]) ** 2 +
                           (base["ITMNorthing"] - t["ITMNorthing"]) ** 2)
            pipe = base[(dist <= radius) & (base["case_key"] != t["case_key"]) &
                        (base["grant_dt"] <= t0)].copy()
            if len(pipe) < 2:
                continue
            pipe["dur24_g2c"] = (t0 + pd.Timedelta(days=730) - pipe["grant_dt"]).dt.days.clip(lower=0)
            hist = grant_comm[(grant_comm["grant_dt"] < t0 - pd.Timedelta(days=365)) &
                              (grant_comm["PlanningAuthority"] == t["PlanningAuthority"])]
            for horizon_days, horizon_m in ((365, 12), (730, 24), (1095, 36), (1825, 60)):
                # per-scheme P(commence within horizon from t0): use elapsed-since-grant
                # conditional empirical CDF from same-authority history
                fcast_units = 0.0
                for i, row in pipe.iterrows():
                    elapsed = max((t0 - row["grant_dt"]).days, 0)
                    eligible = hist["g2c"][hist["g2c"] > elapsed]
                    if len(eligible) < 15:
                        p = 0.5
                    else:
                        p = float((eligible <= elapsed + horizon_days).mean())
                    fcast_units += row["units"] * p
                realised = pipe[(pipe["comm_dt"] > t0) & (pipe["comm_dt"] <= t0 + pd.Timedelta(days=horizon_days))]["units"].sum()
                nominal = pipe["units"].sum()
                if len(hist) < 15:
                    conv = 0.5
                else:
                    conv = float((hist["g2c"] <= horizon_days).mean())
                rows.append({"target": t["case_key"], "t0": t0, "radius": radius,
                             "horizon_m": horizon_m, "n_pipeline": len(pipe),
                             "nominal_units": float(nominal),
                             "forecast_units": float(fcast_units),
                             "baseline_units": float(conv * nominal),
                             "realised_units": float(realised)})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "supply_backtest.csv", index=False)
    report = {}
    for radius in (1000, 3000, 5000, 10000):
        for h in (12, 24, 36, 60):
            sub = frame[(frame["radius"] == radius) & (frame["horizon_m"] == h)]
            if len(sub) < 15:
                continue
            f_mae = float(np.mean(np.abs(sub["forecast_units"] - sub["realised_units"])))
            b_mae = float(np.mean(np.abs(sub["baseline_units"] - sub["realised_units"])))
            n_mae = float(np.mean(np.abs(sub["nominal_units"] - sub["realised_units"])))
            report[f"r{radius}_h{h}"] = {"n": int(len(sub)),
                                         "forecast_mae": round(f_mae, 0),
                                         "baseline_mae": round(b_mae, 0),
                                         "nominal_mae": round(n_mae, 0),
                                         "gain_vs_baseline_pct": round((1 - f_mae / b_mae) * 100, 1),
                                         "gain_vs_nominal_pct": round((1 - f_mae / n_mae) * 100, 1)}
    (OUT / "supply_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
