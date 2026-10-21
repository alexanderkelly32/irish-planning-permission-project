"""Runner: strata-conditioned interval engine (time-safe).

Smooth-GBM intervals average ~1,155d (commencement) because they shrink to
the mean. A strata-quantile engine - (era x authority x units-band x type)
percentiles computed ONLY from training-era schemes, with fallbacks to
coarser strata - gives per-scheme intervals that are honest and materially
narrower where the data supports it. Compares mean width + coverage vs the
pooled/GBM intervals on the same holdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = 7


def build_strata(data: pd.DataFrame) -> dict:
    strata = {}
    for key in ("era_auth_band_type", "era_auth_band", "era_auth", "era", "global"):
        strata[key] = {}
        for value, part in data.groupby(key, dropna=False):
            if len(part) >= 10:
                strata[key][str(value)] = np.quantile(part["target"], [0.1, 0.5, 0.9])
    return strata


def predict_intervals(row: pd.Series, strata: dict) -> tuple[float, float, str]:
    for key in ("era_auth_band_type", "era_auth_band", "era_auth", "era", "global"):
        quantiles = strata[key].get(str(row[key]))
        if quantiles is not None:
            return float(quantiles[0]), float(quantiles[2]), key
    return np.nan, np.nan, "none"


def engine(name: str, train: pd.DataFrame, test: pd.DataFrame) -> dict:
    # Time-safe rolling strata: for each test row, stratum quantiles come from
    # earlier grants (train + earlier test rows) within the prior 24 months,
    # fallback chain auth|band|type -> auth -> rolling global -> train global.
    full = pd.concat([train, test], ignore_index=True).sort_values("grant_dt").reset_index(drop=True)
    lows, highs, depths = [], [], []
    for i, row in full.iterrows():
        prior = full.iloc[:i]
        window = prior[prior["grant_dt"] >= row["grant_dt"] - pd.Timedelta(days=730)]
        quantiles = None
        depth = "global"
        for key in ("auth_band_type", "auth", "global"):
            part = window[window[key] == row[key]] if key != "global" else window
            if len(part) >= 10:
                quantiles = np.quantile(part["target"], [0.1, 0.9])
                depth = key
                break
        if quantiles is None and len(window) >= 10:
            quantiles = np.quantile(window["target"], [0.1, 0.9])
            depth = "rolling_global"
        if quantiles is None:
            quantiles = np.quantile(train["target"], [0.1, 0.9])
            depth = "train_global"
        lows.append(float(quantiles[0]))
        highs.append(float(quantiles[1]))
        depths.append(depth)
    test_rows = full.iloc[len(train):]
    y = test_rows["target"].to_numpy()
    lows = np.asarray(lows[len(train):])
    highs = np.asarray(highs[len(train):])
    coverage = float(np.mean((y >= lows) & (y <= highs)))
    width = float(np.mean(highs - lows))
    depth_counts = {depth: int(depths[len(train):].count(depth)) for depth in sorted(set(depths[len(train):]))}
    return {
        "model": name,
        "n_test": int(len(test_rows)),
        "mean_80pct_interval_width_days": round(width, 0),
        "empirical_coverage": round(coverage, 3),
        "depth_distribution": depth_counts,
    }


def commencement_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits"]], on="case_key", how="inner")
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["target"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    data = frame[frame["activation_linked"].astype(bool)].dropna(subset=["target", "grant_dt"]).copy()
    data["era"] = np.where(data["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC"), "pre2020",
                           np.where(data["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC"), "2020-21", "2022+"))
    units = pd.to_numeric(data["NumResidentialUnits"], errors="coerce")
    data["band"] = pd.cut(units, bins=[0, 29, 99, np.inf], labels=["10-29", "30-99", "100+"]).astype(str)
    description = data["DevelopmentDescription"].fillna("")
    data["type"] = np.where(description.str.contains("apartment|duplex", case=False, regex=True), "apartments",
                            np.where(description.str.contains(r"\bhouse", case=False, regex=True), "houses", "other"))
    data["auth"] = data["PlanningAuthority"].astype(str)
    data["auth_band_type"] = data["auth"] + "|" + data["band"] + "|" + data["type"]
    data["global"] = "g"
    train = data[data["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC")]
    test = data[data["grant_dt"] >= pd.Timestamp("2020-01-01", tz="UTC")]
    return train, test


def sale_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    sold = exit_labels[(exit_labels["sales_linked"] > 0) & exit_labels["sales_eligible"]].copy()
    data = sold.merge(cohort[["case_key", "PlanningAuthority", "NumResidentialUnits", "DevelopmentDescription",
                              "grant_date_dt"]], left_on="scheme_id", right_on="case_key", how="inner")
    data["grant_dt"] = pd.to_datetime(data["grant_date_dt"], utc=True, errors="coerce")
    data["target"] = pd.to_numeric(data["time_to_first_sale_from_grant_days"], errors="coerce")
    data = data[data["target"].between(0, 2200)].dropna(subset=["grant_dt"])
    data["era"] = np.where(data["grant_dt"] < pd.Timestamp("2021-01-01", tz="UTC"), "pre2021", "2021+")
    units = pd.to_numeric(data["NumResidentialUnits"], errors="coerce")
    data["band"] = pd.cut(units, bins=[0, 29, 99, np.inf], labels=["10-29", "30-99", "100+"]).astype(str)
    description = data["DevelopmentDescription"].fillna("")
    data["type"] = np.where(description.str.contains("apartment|duplex", case=False, regex=True), "apartments",
                            np.where(description.str.contains(r"\bhouse", case=False, regex=True), "houses", "other"))
    data["auth"] = data["PlanningAuthority"].astype(str)
    data["auth_band_type"] = data["auth"] + "|" + data["band"] + "|" + data["type"]
    data["global"] = "g"
    train = data[data["grant_dt"] < pd.Timestamp("2021-01-01", tz="UTC")]
    test = data[data["grant_dt"] >= pd.Timestamp("2021-01-01", tz="UTC")]
    return train, test


if __name__ == "__main__":
    report = {}
    comm_train, comm_test = commencement_frames()
    report["commencement"] = engine("commencement_strata_intervals", comm_train, comm_test)
    report["commencement"]["gbm_smooth_comparison"] = {
        "mean_80pct_width_days": 1155.0,
        "empirical_coverage": 0.746,
    }
    sale_train, sale_test = sale_frames()
    report["sale"] = engine("sale_strata_intervals", sale_train, sale_test)
    report["sale"]["gbm_smooth_comparison"] = {
        "mean_80pct_width_days": 1462.0,
        "empirical_coverage": 0.753,
    }
    out = settings.SILVER_DIR / "strata_interval_engine.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
