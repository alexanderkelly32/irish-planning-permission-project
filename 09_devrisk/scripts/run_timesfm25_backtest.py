"""Runner: TimesFM 2.5 (Apache-2.0) zero-shot backtest on PPR/BCMS series.

Same targets and baselines as the 3.0 backtest; batch forecast API.
2.5 is Apache-2.0 licensed (commercially usable).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from run_timesfm_ppr_bcms_backtest import CONTEXT, HORIZON, monthly_series  # noqa: E402

if __name__ == "__main__":
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms = bcms[bcms["commencement_date_dt"].notna()]

    targets = {
        "ppr_county_monthly_volume": monthly_series(ppr, "county_norm", "sale_date_dt"),
        "ppr_county_monthly_median_price": monthly_series(ppr, "county_norm", "sale_date_dt", "price_num"),
        "bcms_county_monthly_commencements": monthly_series(bcms, "county", "commencement_date_dt"),
    }

    from timesfm import TimesFM_2p5_200M_torch

    from timesfm import TimesFM_2p5_200M_torch, configs

    forecaster = TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch", torch_compile=False)
    forecaster.compile(configs.ForecastConfig(max_context=128, max_horizon=128))
    print("TimesFM 2.5 loaded (compiled)", flush=True)

    results = []
    for target, series in targets.items():
        names, contexts, actuals = [], [], []
        baseline_results = {}
        for name, values in series.items():
            values = np.asarray(values, dtype=float)
            context = values[-(CONTEXT + HORIZON):-HORIZON]
            actual = values[-HORIZON:]
            if np.isnan(context).any() or np.isnan(actual).any():
                continue
            baseline_results[name] = {
                "persistence": round(float(np.mean(np.abs(actual - context[-1]))), 2),
                "seasonal_naive": round(float(np.mean(np.abs(actual - context[-12:]))), 2),
                "context_mean": round(float(np.mean(np.abs(actual - context.mean()))), 2),
            }
            names.append(name)
            contexts.append(context)
            actuals.append(actual)

        mean_f, quantile_f = forecaster.forecast(HORIZON, contexts)
        mean_f = np.asarray(mean_f)[:, :HORIZON]

        timesfm_results = {}
        for idx, name in enumerate(names):
            timesfm_results[name] = round(float(np.mean(np.abs(actuals[idx] - mean_f[idx]))), 2)

        pooled = {"persistence": [], "seasonal_naive": [], "context_mean": [], "timesfm2p5": []}
        for name in baseline_results:
            for method in ("persistence", "seasonal_naive", "context_mean"):
                pooled[method].append(baseline_results[name][method])
            pooled["timesfm2p5"].append(timesfm_results[name])
        entry = {
            "target": target,
            "n_series": int(len(names)),
            "pooled_mae": {method: round(float(np.mean(values)), 2) for method, values in pooled.items()},
            "timesfm2p5_beats_persistence": int(sum(
                1 for name in baseline_results if timesfm_results[name] < baseline_results[name]["persistence"])),
            "timesfm2p5_beats_seasonal": int(sum(
                1 for name in baseline_results if timesfm_results[name] < baseline_results[name]["seasonal_naive"])),
        }
        results.append(entry)
        print(json.dumps(entry, indent=1), flush=True)

    out = settings.SILVER_DIR / "timesfm25_backtest.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
