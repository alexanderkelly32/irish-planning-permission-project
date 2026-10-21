"""Macro market forecaster: TimesFM-2.5 (Apache-2.0) county-level forecasts.

Generates 12-month forecasts for:
  - PPR monthly sales volume per county
  - PPR monthly median price per county
  - BCMS monthly commencement count per county

Backtest-validated (timesfm25_backtest.json): volumes MAE 29.5 vs 34.8
seasonal; prices EUR 19.2k vs 28.4k; commencements 11.5 vs 22.2. Forecasts
feed market-context blocks in reports; recomputed on the drift cadence.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from scripts.run_timesfm_ppr_bcms_backtest import monthly_series  # noqa: E402

HORIZON = 12


def generate_forecasts() -> pd.DataFrame:
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms = bcms[bcms["commencement_date_dt"].notna()]

    targets = {
        "ppr_volume": monthly_series(ppr, "county_norm", "sale_date_dt"),
        "ppr_median_price": monthly_series(ppr, "county_norm", "sale_date_dt", "price_num"),
        "bcms_commencements": monthly_series(bcms, "county", "commencement_date_dt"),
    }

    from timesfm import TimesFM_2p5_200M_torch, configs

    forecaster = TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch", torch_compile=False)
    forecaster.compile(configs.ForecastConfig(max_context=128, max_horizon=128))

    rows = []
    for target, series in targets.items():
        names, contexts = [], []
        for name, values in series.items():
            values = np.asarray(values, dtype=float)
            context = values[-96:]
            if np.isnan(context).any():
                continue
            names.append(str(name))
            contexts.append(context)
        mean_f, _ = forecaster.forecast(HORIZON, contexts)
        mean_f = np.asarray(mean_f)[:, :HORIZON]
        last_month = pd.Timestamp("2026-09-01", tz="UTC")
        for idx, name in enumerate(names):
            for step in range(HORIZON):
                month = (last_month + pd.DateOffset(months=1 + step)).to_period("M")
                rows.append({
                    "target": target,
                    "county": name,
                    "month": str(month),
                    "forecast": round(float(mean_f[idx, step]), 1),
                    "model_version": "timesfm-2.5-200m",
                    "licence": "Apache-2.0",
                    "horizon_months": step + 1,
                })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    frame = generate_forecasts()
    out = settings.SILVER_DIR / "macro_forecasts.parquet"
    frame.to_parquet(out, index=False)
    print(f"macro forecasts -> {out} ({len(frame)} rows)")
    print(frame.groupby("target")["county"].nunique().to_dict())
