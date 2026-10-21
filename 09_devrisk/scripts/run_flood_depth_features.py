"""Runner: flood-depth features (data in hand) + commencement ablation.

ge10_with_flooding.csv carries per-scheme depth maxima (fluvial/coastal/
NCFHM 100yr/1000yr). These depth magnitudes were never used - only
hit/distance flags. Build depth features + ablate.
"""
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
    flood = pd.read_csv(settings.ROOT / "01_flood" / "current" / "ge10_with_flooding.csv", low_memory=False)
    depth_cols = [c for c in flood.columns if c.startswith("flood_depth_") and c.endswith("__m") and not c.endswith("__has")]
    keep = ["PlanningAuthority", "ApplicationNumber"] + depth_cols + ["coastal_depth_max_m", "fluvial_depth_max_m"]
    flood = flood[keep].copy()
    flood["_join"] = flood["PlanningAuthority"].astype(str).str.lower() + "__" + flood["ApplicationNumber"].astype(str)

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "PlanningAuthority", "ApplicationNumber", "GrantDate", "NumResidentialUnits",
                    "DevelopmentDescription"]].drop_duplicates("case_key")
    reg["_join"] = reg["PlanningAuthority"].astype(str).str.lower() + "__" + reg["ApplicationNumber"].astype(str)
    flood = flood.drop(columns=["PlanningAuthority", "ApplicationNumber"]).drop_duplicates("_join")
    base = labels.merge(reg, on="case_key", how="inner").merge(flood, on="_join", how="left")
    for column in depth_cols + ["coastal_depth_max_m", "fluvial_depth_max_m"]:
        base[column] = pd.to_numeric(base[column], errors="coerce")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    CBASE = ["log_units", "type_apartment", "grant_year"]
    DEPTH = [c for c in base.columns if c in depth_cols or c in ("coastal_depth_max_m", "fluvial_depth_max_m")]

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        return np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)

    p_base, p_depth = run(CBASE), run(CBASE + DEPTH)
    y = test["activation"].to_numpy()
    report = {
        "depth_feature_coverage": round(float(base[DEPTH].notna().any(axis=1).mean()), 3),
        "n_train": int(len(train)), "n_test": int(len(test)),
        "base_mae": round(float(np.mean(np.abs(y - p_base))), 0),
        "depth_mae": round(float(np.mean(np.abs(y - p_depth))), 0),
        "delta": round(float(np.mean(np.abs(y - p_depth)) - np.mean(np.abs(y - p_base))), 0),
    }
    out = settings.SILVER_DIR / "flood_depth_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
