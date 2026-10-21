#!/usr/bin/env python3
"""GE10-specialist benchmark: a v3-style model trained ONLY on pre-2025
>=10-unit rows, evaluated on the 2025 GE10 holdout against frozen v3.

Same submission-time feature matrix as v3 (text + authority/bucket + history +
comparable aggregates), same split discipline, restricted to the GE10 universe.
Answers: does specialising on GE10 beat the general model for the commercial band?
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_comparable_feature_experiment import COMPARABLE_FEATURES_PATH, V3_FEATURES  # noqa: E402
from build_national_residential_model_v2 import TRAIN_CUTOFF, load_data_with_history  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402


def main() -> None:
    data = load_data_with_history().reset_index(drop=True)
    comparable = pd.read_parquet(COMPARABLE_FEATURES_PATH)
    data = data.merge(comparable, on="case_key", how="left")
    v3_scores = pd.read_csv(OUTPUT_DIR / "raw_planning_v3_2025_predictions.csv", low_memory=False)[["case_key", "v3_ranking_score"]]
    data = data.merge(v3_scores, on="case_key", how="left")

    corrected = pd.read_csv(ROOT / "02_development" / "current" / "ground_source_units_corrected.csv", low_memory=False)
    corrected_map = dict(zip(corrected["case_key"].astype(str), pd.to_numeric(corrected["units_corrected"], errors="coerce")))
    import re
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", str(s).lower())
    corrected_norm = {norm(k): v for k, v in corrected_map.items() if pd.notna(v)}
    data["_nk"] = data["case_key"].astype(str).map(norm)
    data["units"] = pd.to_numeric(data["NumResidentialUnits"], errors="coerce")
    data["units"] = data["units"].fillna(data["_nk"].map(lambda k: corrected_norm.get(k)))

    ge10 = data[data["units"] >= 10].copy()
    train = ge10[ge10["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = ge10[ge10["received_date_dt"] >= TRAIN_CUTOFF].copy()
    print(f"GE10 train rows: {len(train)} | GE10 2025 test rows: {len(test)}", flush=True)

    if len(train) < 500 or len(test) < 20:
        print(json.dumps({"status": "insufficient_ge10_rows", "train": len(train), "test": len(test)}, indent=2))
        return

    model = build_scaled_pipeline(V3_FEATURES[3:])
    model.fit(train[V3_FEATURES], train["target_refused"])
    specialist_p = model.predict_proba(test[V3_FEATURES])[:, 1]
    v3_p = test["v3_ranking_score"].to_numpy() if "v3_ranking_score" in test.columns else np.full(len(test), np.nan)

    results = {
        "ge10_specialist": {
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "refusal_rate": round(float(test["target_refused"].mean()), 4),
            "roc_auc": round(float(roc_auc_score(test["target_refused"], specialist_p)), 4) if test["target_refused"].nunique() == 2 else None,
            "average_precision": round(float(average_precision_score(test["target_refused"], specialist_p)), 4) if test["target_refused"].nunique() == 2 else None,
        },
    }
    v3_valid = ~np.isnan(v3_p)
    if v3_valid.any() and test["target_refused"].nunique() == 2:
        results["v3_on_same_ge10_holdout"] = {
            "roc_auc": round(float(roc_auc_score(test["target_refused"][v3_valid], v3_p[v3_valid])), 4),
            "average_precision": round(float(average_precision_score(test["target_refused"][v3_valid], v3_p[v3_valid])), 4),
        }
    results["caveat"] = (
        "v3 scores exist only for 2025 rows, so the comparison is on the 2025 GE10 "
        "holdout only (~170 rows). The specialist trains on all pre-2025 GE10 rows. "
        "Small holdout - direction, not decimals."
    )
    (OUTPUT_DIR / "raw_planning_ge10_specialist_benchmark.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
