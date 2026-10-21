"""Runner: D ablation - ePlan structured fields vs commencement (latest-era)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"09_devrisk")

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from devrisk import settings

RNG = np.random.default_rng(7)


def numeric(value):
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return np.nan


if __name__ == "__main__":
    fields = pd.read_csv(settings.SILVER_DIR / "eplan_structured_fields.csv")
    fields = fields.rename(columns={"case_key": "case_key_raw"})
    fields["case_key"] = fields["case_key_raw"].astype(str)
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    base = labels.merge(reg, on="case_key", how="inner").merge(fields, on="case_key", how="left")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)

    D_FEATS = [c for c in fields.columns if c != "case_key_raw" and c != "case_key"]
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    CBASE = ["log_units", "type_apartment", "grant_year"]

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        return np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)

    p_base, p_d = run(CBASE), run(CBASE + D_FEATS)
    y = test["activation"].to_numpy()
    report = {
        "field_coverage": {c: round(float(base[c].notna().mean()), 3) for c in D_FEATS[:8]},
        "n_train": int(len(train)), "n_test": int(len(test)),
        "base_mae": round(float(np.mean(np.abs(y - p_base))), 0),
        "eplan_mae": round(float(np.mean(np.abs(y - p_d))), 0),
        "delta": round(float(np.mean(np.abs(y - p_d)) - np.mean(np.abs(y - p_base))), 0),
    }
    out = settings.SILVER_DIR / "eplan_fields_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
