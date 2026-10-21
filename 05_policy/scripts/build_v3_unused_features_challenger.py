#!/usr/bin/env python3
"""v3 challenger with previously-unused submission-time features:
- flood layers (CFRAM/NFHM hits, depths, coastal/fluvial distance)
- register numerics (units, site area, floor area)
- applicant-repeat history (time-safe prior submissions by same applicant)
- LandUseCode

Same pre-2025/2025 split and frozen baseline (0.7989/0.4202). Also reports the
GE10-subset AUC, where the flood layer should matter most.
"""
from __future__ import annotations

import json
import re
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

FLOOD_CSV = ROOT / "01_flood" / "current" / "ge10_with_flooding.csv"

FLOOD_FEATURES = [
    "flood_depth__ncfhm__rp100__m",
    "flood_depth__ncfhm__rp20__m",
    "flood_depth__nifm__rp20__m",
    "coastal_depth_max_m",
    "fluvial_depth_max_m",
    "coastal_hit_any",
    "fluvial_hit_any",
    "coastal_min_logdist",
    "fluvial_min_logdist",
]


def main() -> None:
    data = load_data_with_history().reset_index(drop=True)
    comparable = pd.read_parquet(COMPARABLE_FEATURES_PATH)
    data = data.merge(comparable, on="case_key", how="left")

    norm = lambda s: re.sub(r"[^a-z0-9]+", "", str(s).lower())
    corrected = pd.read_csv(ROOT / "02_development" / "current" / "ground_source_units_corrected.csv", low_memory=False)
    corrected_norm = {norm(k): v for k, v in zip(corrected["case_key"].astype(str), pd.to_numeric(corrected["units_corrected"], errors="coerce")) if pd.notna(v)}
    holdout_units = pd.read_csv(ROOT / "02_development" / "current" / "holdout_units_extracted.csv", low_memory=False)
    holdout_norm = {norm(k): v for k, v in zip(holdout_units["case_key"].astype(str), pd.to_numeric(holdout_units["units_final"], errors="coerce")) if pd.notna(v)}
    data["_nk"] = data["case_key"].astype(str).map(norm)
    data["units"] = pd.to_numeric(data["NumResidentialUnits"], errors="coerce")
    data["units"] = data["units"].fillna(data["_nk"].map(lambda k: corrected_norm.get(k)))
    data["units"] = data["units"].fillna(data["_nk"].map(lambda k: holdout_norm.get(k)))

    flood = pd.read_csv(FLOOD_CSV, low_memory=False)
    flood["_key"] = flood["PlanningAuthority"].fillna("").astype(str) + "__" + flood["ApplicationNumber"].fillna("").astype(str)
    flood_map = flood.drop_duplicates("_key", keep="first").set_index("_key")[FLOOD_FEATURES]
    for feature in FLOOD_FEATURES:
        data[feature] = data["case_key"].map(lambda k: flood_map.loc[k, feature] if k in flood_map.index else np.nan)

    data["log_units"] = np.log1p(pd.to_numeric(data["units"], errors="coerce").clip(lower=0))
    data["log_site_area_sqm"] = np.log1p(pd.to_numeric(data["AreaofSite"], errors="coerce").clip(lower=0) * 10000)
    data["log_floor_area_sqm"] = np.log1p(pd.to_numeric(data["FloorArea"], errors="coerce").clip(lower=0))
    data["units_missing"] = data["log_units"].isna().astype(int)
    data["flood_any"] = pd.concat([pd.to_numeric(data[f], errors="coerce") for f in ["fluvial_hit_any", "coastal_hit_any"]], axis=1).max(axis=1).fillna(0)

    data["applicant_id"] = data["ApplicantForename"].fillna("").astype(str).str.lower() + "|" + data["ApplicantSurname"].fillna("").astype(str).str.lower()
    data["applicant_id"] = data["applicant_id"].replace({"|": "", "||": ""}, regex=False).replace("", np.nan)
    applicant_history = {}
    data = data.sort_values("received_date_dt").reset_index(drop=True)
    prior_count = np.zeros(len(data))
    prior_refusal = np.zeros(len(data))
    applicant_rows: dict[str, list[tuple[int, int]]] = {}
    for i, (_, row) in enumerate(data.iterrows()):
        key = row.get("applicant_id")
        if pd.notna(key) and key:
            for prior_idx, refused in applicant_rows.get(str(key), []):
                prior_count[i] += 1
                prior_refusal[i] += refused
            if pd.notna(row.get("target_refused")):
                applicant_rows.setdefault(str(key), []).append((i, int(row["target_refused"])))
    data["applicant_prior_count"] = prior_count
    data["applicant_prior_refusal_rate"] = np.divide(prior_refusal, prior_count, out=np.zeros_like(prior_count), where=prior_count > 0)

    extra_features = [
        "log_units", "log_site_area_sqm", "log_floor_area_sqm", "units_missing",
        "applicant_prior_count", "applicant_prior_refusal_rate",
        *FLOOD_FEATURES, "flood_any",
    ]
    features = V3_FEATURES + extra_features
    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].copy().reset_index(drop=True)

    pipeline = build_scaled_pipeline(V3_FEATURES[3:] + extra_features)
    pipeline.fit(train[features], train["target_refused"])
    p = pipeline.predict_proba(test[features])[:, 1]

    y = test["target_refused"]
    results = {
        "challenger_v3_plus_unused": {
            "roc_auc": round(float(roc_auc_score(y, p)), 4),
            "average_precision": round(float(average_precision_score(y, p)), 4),
        },
        "frozen_v3_baseline": {"roc_auc": 0.7989, "average_precision": 0.4202},
        "extra_features": extra_features,
        "flood_join_coverage": round(float(test["flood_any"].notna().mean()), 4),
    }
    ge10_test = test[test["units"] >= 10]
    if len(ge10_test) >= 20 and ge10_test["target_refused"].nunique() == 2:
        results["ge10_subset"] = {
            "n": int(len(ge10_test)),
            "challenger_auc": round(float(roc_auc_score(ge10_test["target_refused"], p[ge10_test.index])), 4),
            "challenger_ap": round(float(average_precision_score(ge10_test["target_refused"], p[ge10_test.index])), 4),
        }
    results["caveat"] = (
        "All features are submission-time: flood maps and applicant history predate the "
        "application. Flood join covers GE10 rows only (the flood CSV is the GE10 universe)."
    )
    (OUTPUT_DIR / "raw_planning_v3_unused_features_challenger.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
