"""Runner: B ablation - condition-burden features vs commencement (frozen
latest-era protocol), on the subset with planner-report PDFs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)


if __name__ == "__main__":
    burden = pd.read_csv(settings.SILVER_DIR / "condition_burden_features.csv")
    burden["appno"] = burden["appno"].astype(str)
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "ApplicationNumber", "GrantDate", "NumResidentialUnits",
                    "DevelopmentDescription"]].drop_duplicates("case_key")
    reg["appno"] = reg["ApplicationNumber"].astype(str)
    base = labels.merge(reg, on="case_key", how="inner").merge(burden, on="appno", how="inner")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    CBASE = ["log_units", "type_apartment", "grant_year"]
    COND = ["n_conditions", "n_precommencement"] + [c for c in burden.columns if c.startswith("has_")]

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        return np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)

    report = {
        "schemes_with_burden": int(len(base)),
        "n_train": int(len(train)), "n_test": int(len(test)),
    }
    if len(train) >= 30 and len(test) >= 15:
        p_base, p_cond = run(CBASE), run(CBASE + COND)
        y = test["activation"].to_numpy()
        report.update({
            "base_mae": round(float(np.mean(np.abs(y - p_base))), 0),
            "cond_mae": round(float(np.mean(np.abs(y - p_cond))), 0),
            "delta": round(float(np.mean(np.abs(y - p_cond)) - np.mean(np.abs(y - p_base))), 0),
        })
    else:
        report["note"] = "insufficient burden-labelled schemes for split"
    out = settings.SILVER_DIR / "condition_burden_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
