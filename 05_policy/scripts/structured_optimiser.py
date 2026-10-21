"""Text-free structured optimiser candidate: cohort, models, sensitivity sweeps."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

GRANT_LABELS = {
    "CONDITIONAL", "CONDITIONAL PERMISSION", "GRANT PERMISSION",
    "UNCONDITIONAL", "UNCONDITIONAL PERMISSION", "GRANTED",
}
REFUSAL_LABELS = {"REFUSED", "REFUSE PERMISSION"}

NUMERIC_FEATURES = [
    "log_units",
    "storeys",
    "log_site_area_sqm",
    "log_floor_area_sqm",
    "density_units_per_ha",
    "plot_ratio_proxy",
    "log_parking_spaces",
    "log_open_space_sqm",
]
MISSING_FLAG_FEATURES = [
    "units_missing",
    "site_area_missing",
    "floor_area_missing",
    "parking_missing",
    "open_space_missing",
]
STRUCTURED_FEATURES = [*NUMERIC_FEATURES, *MISSING_FLAG_FEATURES, "received_year"]
BASE_FEATURES = ["log_units", "units_missing", "received_year"]
AUTHORITY_FEATURE = "authority_ordinal"


def resolve_outcome(decision: object) -> str:
    value = str(decision or "").strip().upper()
    if value in GRANT_LABELS:
        return "GRANTED"
    if value in REFUSAL_LABELS:
        return "REFUSED"
    return "UNKNOWN"


def _log1p(frame: pd.DataFrame, column: str) -> pd.Series:
    return np.log1p(pd.to_numeric(frame[column], errors="coerce").clip(lower=0))


def build_cohort(source: pd.DataFrame) -> pd.DataFrame:
    """GE10 cohort with outcomes, storeys and derived structured features."""
    required = {
        "case_key", "PlanningAuthority", "Decision", "ReceivedDate",
        "units_total_best", "llm_max_storeys", "max_storeys_best",
        "NumResidentialUnits", "AreaofSite", "FloorArea",
        "parking_spaces_best", "open_space_sqm_best",
    }
    missing = required.difference(source.columns)
    if missing:
        raise ValueError(f"source is missing columns: {', '.join(sorted(missing))}")
    frame = source.copy()
    frame["received_year"] = pd.to_datetime(frame["ReceivedDate"], errors="coerce").dt.year
    frame["outcome"] = frame["Decision"].map(resolve_outcome)
    frame = frame[frame["outcome"].isin(["GRANTED", "REFUSED"])].copy()
    frame["target_refused"] = frame["outcome"].eq("REFUSED").astype(int)

    llm_storeys = pd.to_numeric(frame["llm_max_storeys"], errors="coerce")
    old_storeys = pd.to_numeric(frame["max_storeys_best"], errors="coerce").where(lambda s: s.between(1, 40))
    if "storeys_final" in frame.columns:
        frame["storeys"] = pd.to_numeric(frame["storeys_final"], errors="coerce")
    else:
        frame["storeys"] = llm_storeys.fillna(old_storeys)
    frame = frame[frame["storeys"].notna()].copy()

    units = pd.to_numeric(frame["units_total_best"], errors="coerce")
    corrected_path = Path(__file__).resolve().parents[2] / "02_development" / "current" / "ground_source_units_corrected.csv"
    if corrected_path.exists():
        corrected = pd.read_csv(corrected_path, low_memory=False)
        corrected_map = dict(zip(corrected["case_key"].astype(str), pd.to_numeric(corrected["units_corrected"], errors="coerce")))
        overlay_units = frame["case_key"].astype(str).map(lambda k: corrected_map.get(k))
        units = units.fillna(overlay_units)
        frame["units_corrected"] = overlay_units
        frame["units_provenance"] = frame["case_key"].astype(str).map(
            lambda k: dict(zip(corrected["case_key"].astype(str), corrected["provenance"])).get(k, "")
        )
    else:
        frame["units_corrected"] = units
        frame["units_provenance"] = ""
    area_ha = pd.to_numeric(frame["AreaofSite"], errors="coerce")
    floor = pd.to_numeric(frame["FloorArea"], errors="coerce")
    parking = pd.to_numeric(frame["parking_spaces_best"], errors="coerce").where(lambda s: s.between(0, 5000))
    open_space = pd.to_numeric(frame["open_space_sqm_best"], errors="coerce").where(lambda s: s.between(0, 200000))
    frame["log_units"] = np.log1p(units.clip(lower=0))
    frame["log_site_area_sqm"] = np.log1p((area_ha * 10000).clip(lower=0))
    frame["log_floor_area_sqm"] = np.log1p(floor.clip(lower=0))
    frame["density_units_per_ha"] = np.where(area_ha > 0, units / area_ha, np.nan)
    frame["plot_ratio_proxy"] = np.where(area_ha > 0, floor / (area_ha * 10000), np.nan)
    frame["log_parking_spaces"] = np.log1p(parking.clip(lower=0))
    frame["log_open_space_sqm"] = np.log1p(open_space.clip(lower=0))
    frame["units_missing"] = units.isna().astype(int)
    frame["site_area_missing"] = area_ha.isna().astype(int)
    frame["floor_area_missing"] = floor.isna().astype(int)
    frame["parking_missing"] = parking.isna().astype(int)
    frame["open_space_missing"] = open_space.isna().astype(int)
    frame["authority_ordinal"] = pd.factorize(frame["PlanningAuthority"].fillna(""))[0]
    return frame.dropna(subset=["log_units"]).reset_index(drop=True)


def split_temporal(cohort: pd.DataFrame, cutoff_year: int = 2025) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = cohort[cohort["received_year"] < cutoff_year].copy()
    test = cohort[cohort["received_year"] >= cutoff_year].copy()
    if train.empty or test.empty:
        raise ValueError("temporal split produced an empty side")
    return train, test


def make_logistic(features: list[str]) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=2000, class_weight="balanced")),
    ])


def make_lightgbm(features: list[str]):
    from lightgbm import LGBMClassifier

    return Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
        ("model", LGBMClassifier(
            n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=20,
            class_weight="balanced", random_state=7, verbose=-1,
        )),
    ])


def evaluate_probas(y: pd.Series, p: np.ndarray) -> dict[str, float | None]:
    clipped = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    metrics: dict[str, float | None] = {
        "n": int(len(y)),
        "refusal_rate": float(y.mean()),
        "brier": float(brier_score_loss(y, clipped)),
        "log_loss": float(log_loss(y, clipped, labels=[0, 1])),
    }
    if y.nunique() == 2:
        metrics["roc_auc"] = float(roc_auc_score(y, clipped))
        metrics["average_precision"] = float(average_precision_score(y, clipped))
    else:
        metrics["roc_auc"] = None
        metrics["average_precision"] = None
    return metrics


def sensitivity_sweep(model, base_row: dict[str, Any], features: list[str], field: str, values: list[float]) -> list[dict[str, Any]]:
    """Holding other inputs constant, sweep one structured field through values."""
    rows = []
    for value in values:
        candidate = {**base_row, field: value}
        frame = pd.DataFrame([{feature: candidate.get(feature, 0.0) for feature in features}])
        probability = float(model.predict_proba(frame)[:, 1][0])
        rows.append({field: value, "refusal_probability": round(probability, 4)})
    return rows


def calibrate_with_cv(model, x_train: pd.DataFrame, y_train: pd.Series, n_splits: int = 3, seed: int = 20260904) -> LogisticRegression:
    """Fit a Platt calibrator on out-of-fold train probabilities."""
    from sklearn.model_selection import StratifiedKFold

    out_of_fold = np.empty(len(x_train), dtype=float)
    for train_idx, valid_idx in StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed).split(x_train, y_train):
        fold_model = make_logistic(list(x_train.columns))
        fold_model.fit(x_train.iloc[train_idx], y_train.iloc[train_idx])
        out_of_fold[valid_idx] = fold_model.predict_proba(x_train.iloc[valid_idx])[:, 1]
    logits = np.log(np.clip(out_of_fold, 1e-6, 1 - 1e-6) / (1 - np.clip(out_of_fold, 1e-6, 1 - 1e-6))).reshape(-1, 1)
    calibrator = LogisticRegression(C=1_000_000, solver="lbfgs", max_iter=1000)
    calibrator.fit(logits, y_train.to_numpy())
    return calibrator


def apply_calibration(calibrator: LogisticRegression, probabilities: np.ndarray) -> np.ndarray:
    logits = np.log(np.clip(probabilities, 1e-6, 1 - 1e-6) / (1 - np.clip(probabilities, 1e-6, 1 - 1e-6))).reshape(-1, 1)
    return calibrator.predict_proba(logits)[:, 1]


def bootstrap_ci(y: pd.Series, p: np.ndarray, n_boot: int = 500, seed: int = 20260904) -> dict[str, Any]:
    """Percentile bootstrap confidence intervals for ranking and calibration metrics."""
    rng = np.random.default_rng(seed)
    y_values = y.to_numpy()
    p_values = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    auc_samples: list[float] = []
    ap_samples: list[float] = []
    brier_samples: list[float] = []
    valid = 0
    for _ in range(n_boot):
        indices = rng.integers(0, len(y_values), size=len(y_values))
        y_boot, p_boot = y_values[indices], p_values[indices]
        if len(np.unique(y_boot)) < 2:
            continue
        valid += 1
        auc_samples.append(float(roc_auc_score(y_boot, p_boot)))
        ap_samples.append(float(average_precision_score(y_boot, p_boot)))
        brier_samples.append(float(brier_score_loss(y_boot, p_boot)))
    def interval(values: list[float]) -> dict[str, float]:
        return {
            "median": round(float(np.median(values)), 4),
            "p05": round(float(np.quantile(values, 0.05)), 4),
            "p95": round(float(np.quantile(values, 0.95)), 4),
        }

    return {
        "bootstrap_samples": n_boot,
        "valid_samples": valid,
        "roc_auc": interval(auc_samples),
        "average_precision": interval(ap_samples),
        "brier": interval(brier_samples),
    }
