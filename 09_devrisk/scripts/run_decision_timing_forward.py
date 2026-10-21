"""Runner: decision-timing with TimesFM forward-congestion features.

Question: does a forward-looking authority-congestion feature (TimesFM-2.5
forecast of the authority's next 12-month application volume, made from data
available at 2023-12) improve the GBM on the 2024+ holdout vs the
backward-only congestion features?
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402
from run_decision_timing import add_congestion_features_fast, build_features, load_cohort  # noqa: E402

RNG = 7


def pinball(y, pred, tau):
    diff = y - pred
    return float(np.mean(np.where(diff >= 0, tau * diff, (tau - 1) * diff)))


def forward_congestion() -> pd.DataFrame:
    """Authority-level TimesFM forecast of monthly application counts.

    Forecasts are made once from data up to 2023-12 (available to every 2024+
    submission). Returns DataFrame: authority -> forward_mean_next_3m.
    """
    from timesfm import TimesFM_2p5_200M_torch, configs

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = register.copy()
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["month"] = frame["received_dt"].dt.to_period("M")
    rows = []
    for authority, group in frame.groupby("PlanningAuthority"):
        monthly = group.groupby("month").size()
        monthly.index = monthly.index.to_timestamp()
        monthly = monthly.resample("MS").asfreq().fillna(0)
        monthly = monthly[monthly.index <= pd.Timestamp("2023-12-01")]
        if monthly.notna().sum() < 60:
            continue
        rows.append((str(authority), monthly.to_numpy(dtype=float)[-96:]))

    forecaster = TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch", torch_compile=False)
    forecaster.compile(configs.ForecastConfig(max_context=128, max_horizon=128))
    names = [name for name, _ in rows]
    contexts = [values for _, values in rows]
    mean_f, _ = forecaster.forecast(12, contexts)
    mean_f = np.asarray(mean_f)[:, :12]
    out = pd.DataFrame({
        "PlanningAuthority": names,
        "forward_next_3m_mean": mean_f[:, :3].mean(axis=1),
        "forward_next_12m_mean": mean_f[:, :12].mean(axis=1),
    })
    out.to_parquet(settings.SILVER_DIR / "forward_congestion.parquet", index=False)
    return out


if __name__ == "__main__":
    forward = forward_congestion()
    print(f"forward congestion built for {len(forward)} authorities", flush=True)

    frame = load_cohort()
    frame = add_congestion_features_fast(frame)
    frame = frame.merge(forward, on="PlanningAuthority", how="left")
    frame["forward_next_3m_mean"] = frame["forward_next_3m_mean"].fillna(frame["forward_next_3m_mean"].median())

    train = frame[frame["received_year"] < 2024]
    test = frame[frame["received_year"] >= 2024]
    y_train = train["duration_days"].to_numpy()
    y_test = test["duration_days"].to_numpy()

    base_cols = ["log_units", "type_apartment", "type_house", "received_year", "received_month",
                 "auth_prior_90d_count", "auth_prior_180d_median_duration"]
    X_train = build_features(train).fillna(0.0).astype(float)
    X_test = build_features(test).fillna(0.0).astype(float)
    X_train["authority"] = train["PlanningAuthority"].astype(str)
    X_test["authority"] = test["PlanningAuthority"].astype(str)
    X_train_d = pd.get_dummies(X_train, columns=["authority"])
    X_test_d = X_test.reindex(columns=X_train_d.columns, fill_value=0)

    fwd_train = train["forward_next_3m_mean"].fillna(0.0).values.reshape(-1, 1)
    fwd_test = test["forward_next_3m_mean"].fillna(0.0).values.reshape(-1, 1)

    results = {}
    for name, X_tr, X_te in (
        ("base", X_train_d.values, X_test_d.values),
        ("with_forward_congestion", np.hstack([X_train_d.values, fwd_train]), np.hstack([X_test_d.values, fwd_test])),
    ):
        entry = {}
        for tau in (0.2, 0.5, 0.8):
            gbm = GradientBoostingRegressor(loss="quantile", alpha=tau, n_estimators=300, max_depth=3,
                                            learning_rate=0.05, min_samples_leaf=20, random_state=RNG)
            gbm.fit(X_tr, y_train)
            pred = np.maximum(gbm.predict(X_te), 1.0)
            entry[f"pinball_p{int(tau*100)}"] = round(pinball(y_test, pred, tau), 1)
            if tau == 0.5:
                entry["mae"] = round(float(np.mean(np.abs(y_test - pred))), 1)
        results[name] = entry
        print(name, entry, flush=True)

    out = settings.SILVER_DIR / "decision_timing_forward_congestion.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
