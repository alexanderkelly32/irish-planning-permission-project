#!/usr/bin/env python3
"""Evaluate the FROZEN v3 model on the 2026 register pull (second prospective year)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_comparable_feature_experiment import COMPARABLE_NUMERIC, V3_FEATURES, build_comparable_features  # noqa: E402
import build_comparable_feature_experiment as cfe  # noqa: E402
from build_dublin_submission_model import decision_to_submission_target, strip_text_leakage_clues  # noqa: E402
from build_national_residential_model_v2 import V2_NUMERIC  # noqa: E402
from build_prospective_calibration_backtest import prepare  # noqa: E402
from build_raw_planning_benchmarks import residential_bucket  # noqa: E402
from build_spatial_history_feature_experiment import RAW_HISTORY_NUMERIC, add_history_features  # noqa: E402

COUNT_COLS = [c for c in RAW_HISTORY_NUMERIC if c.endswith("_count")]
RATE_COLS = [c for c in RAW_HISTORY_NUMERIC if c.endswith("_refusal_rate")]
ARTIFACT = ROOT / "05_policy" / "current" / "model_v3" / "national_residential_v3_comparables.joblib"


def clean_2026() -> pd.DataFrame:
    reg = pd.read_parquet(ROOT / "00_base" / "source_data" / "register_2026.parquet")
    units = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce")
    terms = r"\b(?:apartment|apartments|dwelling|dwellings|house|houses|residential|home|extension|retention|change of use|one-off|one off)\b"
    residential = units.gt(0) | reg["OneOffHouse"].fillna("").astype(str).str.strip().str.lower().isin({"y", "yes", "one", "single house"})
    residential |= reg["DevelopmentDescription"].fillna("").astype(str).str.contains(terms, case=False, regex=True)
    reg = reg[residential].copy()
    reg["received_date_dt"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce")
    reg["received_year"] = reg["received_date_dt"].dt.year.astype(float)
    reg["description_stripped"] = reg["DevelopmentDescription"].map(strip_text_leakage_clues)
    reg["application_bucket"] = reg.apply(residential_bucket, axis=1)
    mapped = reg["Decision"].map(decision_to_submission_target)
    reg["target_refused"] = mapped.map(lambda v: v[0] if isinstance(v, tuple) else v)
    reg["case_key"] = reg["PlanningAuthority"].astype(str) + "__" + reg["ApplicationNumber"].astype(str)
    return reg


def main() -> None:
    old = prepare()
    new = clean_2026()
    new["received_year"] = pd.to_numeric(new["received_year"], errors="coerce")
    combined = pd.concat([old, new], ignore_index=True)
    combined = combined.sort_values(["received_date_dt", "case_key"]).reset_index(drop=True)
    print("combined rows:", len(combined), "| 2026 rows:", len(new), flush=True)

    combined = add_history_features(combined)
    for col in COUNT_COLS:
        if col not in combined.columns:
            combined[col] = 0.0
        combined[f"log_{col}"] = np.log1p(pd.to_numeric(combined[col], errors="coerce").fillna(0))
    for col in RATE_COLS:
        if col not in combined.columns:
            combined[col] = np.nan

    cfe.COMPARABLE_FEATURES_PATH = OUT / "raw_planning_comparable_features_2026_ext.parquet"
    comparable = build_comparable_features(combined)
    combined = combined.merge(comparable, on="case_key", how="left")
    for col in COMPARABLE_NUMERIC:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")

    artifact = joblib.load(ARTIFACT)
    pipeline = artifact["ranking_model"]
    features = artifact["feature_columns"]
    y2026 = combined[(combined["received_date_dt"] >= "2026-01-01") & combined["target_refused"].notna()].copy()
    if len(y2026) == 0:
        print("no decided 2026 rows", flush=True)
        return
    p2026 = pipeline.predict_proba(y2026[features])[:, 1]
    y2026 = y2026.reset_index(drop=True)
    y = y2026["target_refused"]

    results = {
        "frozen_v3_on_2026": {
            "n_decided_residential": int(len(y2026)),
            "date_range": [str(y2026["received_date_dt"].min()), str(y2026["received_date_dt"].max())],
            "refusal_rate": round(float(y.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y, p2026)), 4),
            "average_precision": round(float(average_precision_score(y, p2026)), 4),
        },
        "v3_2025_reference": {"roc_auc": 0.7989, "average_precision": 0.4202},
    }
    ge10_mask = (pd.to_numeric(y2026["NumResidentialUnits"], errors="coerce") >= 10).to_numpy()
    ge10_2026 = y2026[ge10_mask]
    if len(ge10_2026) >= 20 and ge10_2026["target_refused"].nunique() == 2:
        p_ge10 = p2026[ge10_mask]
        results["frozen_v3_on_2026"]["ge10_subset"] = {
            "n": int(len(ge10_2026)),
            "refusal_rate": round(float(ge10_2026["target_refused"].mean()), 4),
            "roc_auc": round(float(roc_auc_score(ge10_2026["target_refused"], p_ge10)), 4),
            "average_precision": round(float(average_precision_score(ge10_2026["target_refused"], p_ge10)), 4),
        }
    by_month = []
    for month, group in y2026.groupby(y2026["received_date_dt"].dt.to_period("M")):
        if len(group) >= 30 and group["target_refused"].nunique() == 2:
            by_month.append({"month": str(month), "n": int(len(group)), "roc_auc": round(float(roc_auc_score(group["target_refused"], p2026[group.index])), 4)})
    results["frozen_v3_on_2026"]["by_month"] = by_month
    (OUT / "raw_planning_v3_on_2026.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
