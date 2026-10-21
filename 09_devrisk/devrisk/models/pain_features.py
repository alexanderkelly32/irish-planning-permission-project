"""Shared feature/eval helpers for pain-model scripts (research, not product)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from .. import settings

HOUSES_RE = r"\b(?:house|houses|dwelling|dwellings)\b"
APARTMENTS_RE = r"\b(?:apartment|apartments|duplex|apartment-led)\b"


def load_cohort() -> pd.DataFrame:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv")
    labels = labels.rename(columns={"scheme_id": "case_key"})
    frame = register.merge(labels, on="case_key", how="inner").drop_duplicates("case_key").copy()
    frame["received_date_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["received_year"] = frame["received_date_dt"].dt.year
    frame["units"] = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["site_area"] = pd.to_numeric(frame["AreaofSite"], errors="coerce")
    frame["density"] = frame["units"] / frame["site_area"] * 10000.0  # units per ha
    frame["density"] = frame["density"].replace([np.inf, -np.inf], np.nan)
    frame["log_units"] = np.log1p(frame["units"].fillna(0))
    frame["log_site_area"] = np.log1p(frame["site_area"].fillna(0))
    frame["units_missing"] = frame["units"].isna().astype(int)
    frame["site_missing"] = frame["site_area"].isna().astype(int)
    frame["covid_era"] = frame["received_year"].between(2020, 2021).astype(int)
    description = frame["DevelopmentDescription"].fillna("")
    frame["type_house"] = description.str.contains(HOUSES_RE, case=False, regex=True) & ~description.str.contains("apartment", case=False)
    frame["type_apartment"] = description.str.contains(APARTMENTS_RE, case=False, regex=True)
    frame["scheme_type"] = np.where(
        frame["type_apartment"] & frame["type_house"], "mixed",
        np.where(frame["type_apartment"], "apartments", np.where(frame["type_house"], "houses", "other")),
    )
    frame["description_lower"] = description.str.lower()
    return frame.dropna(subset=["pain_high_binary", "received_date_dt"])


def bootstrap_auc(y: np.ndarray, p: np.ndarray, n_boot: int = 500, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if np.unique(y[idx]).size < 2:
            continue
        aucs.append(roc_auc_score(y[idx], p[idx]))
    return float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))


def calibration_slope_intercept(y: np.ndarray, p: np.ndarray) -> dict[str, float | None]:
    from scipy.stats import linregress

    p_clipped = np.clip(p, 1e-6, 1 - 1e-6)
    logit = np.log(p_clipped / (1 - p_clipped))
    if np.ptp(logit) < 1e-9:
        return {"calibration_slope": None, "calibration_intercept": None}
    slope, intercept, _, _, _ = linregress(logit, y)
    return {"calibration_slope": float(slope), "calibration_intercept": float(intercept)}


def evaluate(y: np.ndarray, p: np.ndarray) -> dict[str, float | int | None]:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    lo, hi = bootstrap_auc(y, p, seed=0)
    out: dict[str, float | int | None] = {
        "n": int(len(y)),
        "prevalence": round(float(y.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "auc_ci_low": round(lo, 4),
        "auc_ci_high": round(hi, 4),
        "average_precision": round(float(average_precision_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "log_loss": round(float(log_loss(y, p, labels=[0, 1])), 4),
    }
    out.update(calibration_slope_intercept(y, p))
    return out
