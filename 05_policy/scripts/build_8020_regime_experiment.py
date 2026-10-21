#!/usr/bin/env python3
"""80/20 regime split experiment.

Train on everything received before 2024-01-01 (83.7%), test on 2024+2025
(16.3%, fully inside the modern post-2017 planning regime and post-2022
development-plan wave). Compares:
  - V3SAME: v3 feature set + pipeline, retrained on this split
  - E8020:  v3 + flood/units/applicant + policy layer + register ratios
2026 is excluded (decisions still landing).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
CUTOFF = pd.Timestamp("2024-01-01", tz="UTC")

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_comparable_feature_experiment import COMPARABLE_FEATURES_PATH, V3_FEATURES  # noqa: E402
from build_national_residential_model_v2 import load_data_with_history  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

FLOOD_CSV = ROOT / "01_flood" / "current" / "all_cases_with_flooding.parquet"
CASE_CONTEXT = ROOT / "07_context" / "current" / "case_context_features.parquet"


def bootstrap_auc_ci(y: np.ndarray, p: np.ndarray, n_boot: int = 400, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if np.unique(y[idx]).size < 2:
            continue
        values.append(roc_auc_score(y[idx], p[idx]))
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def build_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
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
    flood = pd.read_parquet(FLOOD_CSV)
    flood = flood[["case_key", *pc.FLOOD_FEATURES]].drop_duplicates("case_key", keep="first")
    data = data.merge(flood, on="case_key", how="left")
    for feature in pc.FLOOD_FEATURES:
        data[feature] = pd.to_numeric(data[feature], errors="coerce")
    data["log_units"] = np.log1p(pd.to_numeric(data["units"], errors="coerce").clip(lower=0))
    data["log_site_area_sqm"] = np.log1p(pd.to_numeric(data["AreaofSite"], errors="coerce").clip(lower=0) * 10000)
    data["log_floor_area_sqm"] = np.log1p(pd.to_numeric(data["FloorArea"], errors="coerce").clip(lower=0))
    data["units_missing"] = data["log_units"].isna().astype(int)
    data["flood_any"] = pd.concat([pd.to_numeric(data[f], errors="coerce") for f in ["fluvial_hit_any", "coastal_hit_any"]], axis=1).max(axis=1).fillna(0)
    data["applicant_id"] = data["ApplicantForename"].fillna("").astype(str).str.lower() + "|" + data["ApplicantSurname"].fillna("").astype(str).str.lower()
    data["applicant_id"] = data["applicant_id"].replace({"|": "", "||": ""}, regex=False).replace("", np.nan)
    data = data.sort_values("received_date_dt").reset_index(drop=True)
    applicant_history = {}
    prior_count = np.zeros(len(data))
    prior_refusal = np.zeros(len(data))
    for i, (_, row) in enumerate(data.iterrows()):
        key = row.get("applicant_id")
        if pd.notna(key) and key:
            for _, refused in applicant_history.get(str(key), []):
                prior_count[i] += 1
                prior_refusal[i] += refused
            if pd.notna(row.get("target_refused")):
                applicant_history.setdefault(str(key), []).append((i, int(row["target_refused"])))
    data["applicant_prior_count"] = prior_count
    data["applicant_prior_refusal_rate"] = np.divide(prior_refusal, prior_count, out=np.zeros_like(prior_count), where=prior_count > 0)
    data = data.reset_index(drop=True)
    data["received_year"] = pd.to_numeric(data["received_year"], errors="coerce")
    plan_feats = pc.build_plan_features(data)
    data = data.merge(plan_feats, on="case_key", how="left")
    plan_cols = ["plan_unique_codes", "plan_mentions", "plan_codes_match_desc", "plan_mentions_match_desc"] + [f"plan_theme_{t}" for t in pc.THEME_ORDER] + ["plan_theme_other"]
    for col in plan_cols:
        if col not in data.columns:
            data[col] = 0.0
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["policy_plan_covered"] = data["plan_unique_codes"].notna().astype(int)
    for col in plan_cols:
        data[col] = data[col].fillna(0)
    data["log_plan_unique_codes"] = np.log1p(data["plan_unique_codes"])
    data["log_plan_mentions"] = np.log1p(data["plan_mentions"])
    data["log_plan_codes_match_desc"] = np.log1p(data["plan_codes_match_desc"])
    site_ha = pd.to_numeric(data["AreaofSite"], errors="coerce")
    floor = pd.to_numeric(data["FloorArea"], errors="coerce").clip(lower=0)
    units = pd.to_numeric(data["units"], errors="coerce")
    data["density_units_per_ha"] = np.divide(units, site_ha, out=np.full(len(data), np.nan), where=(site_ha > 0) & units.notna()).clip(upper=1000)
    data["floor_area_ratio"] = np.divide(floor, site_ha * 10000, out=np.full(len(data), np.nan), where=site_ha > 0).clip(upper=5)
    data["site_sqm_per_unit"] = np.divide(site_ha * 10000, units, out=np.full(len(data), np.nan), where=units > 0).clip(upper=5000)
    data["avg_unit_floor_sqm"] = np.divide(floor, units, out=np.full(len(data), np.nan), where=units > 0).clip(upper=300)
    density = data["density_units_per_ha"]
    data["density_band_low"] = (density < 35).astype(int)
    data["density_band_mid"] = ((density >= 35) & (density <= 50)).astype(int)
    data["density_band_high"] = (density > 50).astype(int)
    data["density_over_45"] = (density > 45).astype(int)
    data["density_missing"] = density.isna().astype(int)
    landuse = cc.landuse_flags(data["LandUseCode"])
    data = pd.concat([data, landuse], axis=1)
    context = pd.read_parquet(CASE_CONTEXT)
    data = data.merge(context, on="case_key", how="left")
    for col in ["pop_density_per_sqkm", "owner_share", "private_rent_share", "la_rent_share", "septic_share", "cars_per_hh", "no_car_share", "national_road_dist_m", "national_roads_within_1km", "is_urban"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["log_pop_density"] = np.log1p(data["pop_density_per_sqkm"])
    data["log_national_road_dist"] = np.log1p(data["national_road_dist_m"])
    data["is_urban"] = data["is_urban"].fillna(0)

    train = data[data["received_date_dt"] < CUTOFF].copy()
    test = data[data["received_date_dt"] >= CUTOFF].copy().reset_index(drop=True)
    y = test["target_refused"]
    return data, train, test, y


def main() -> None:
    data, train, test, y = build_data()
    print(f"train {len(train)} test {len(test)} cutoff 2024-01-01", flush=True)

    base_extras = [
        "log_units", "log_site_area_sqm", "log_floor_area_sqm", "units_missing",
        "applicant_prior_count", "applicant_prior_refusal_rate",
        *pc.FLOOD_FEATURES, "flood_any",
    ]
    policy_extras = [
        "log_plan_unique_codes", "log_plan_mentions", "policy_plan_covered",
        *[f"plan_theme_{t}" for t in pc.THEME_ORDER], "plan_theme_other",
        "log_plan_codes_match_desc",
    ]
    ratio_extras = [
        "density_units_per_ha", "floor_area_ratio", "site_sqm_per_unit", "avg_unit_floor_sqm",
        "density_band_low", "density_band_mid", "density_band_high", "density_over_45", "density_missing",
        "landuse_new_house", "landuse_housing_new", "landuse_extension", "landuse_retention", "landuse_missing",
    ]
    context_extras = [
        "log_pop_density", "owner_share", "private_rent_share", "la_rent_share",
        "septic_share", "cars_per_hh", "no_car_share",
        "log_national_road_dist", "national_roads_within_1km", "is_urban",
    ]
    variants = {
        "V3SAME": [],
        "E8020": base_extras + policy_extras + ratio_extras + context_extras,
    }
    results: dict[str, object] = {
        "protocol": "80/20 regime split",
        "cutoff": "2024-01-01",
        "rationale": "test 2024+2025 sits fully inside the modern regime (post-NPF 2018 guidelines, post-2022 development-plan adoption wave); 2026 excluded (decisions still landing)",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "test_years": [int(t) for t in sorted(test["received_date_dt"].dt.year.unique())],
        "test_refusal_rate": round(float(y.mean()), 4),
    }
    for name, extras in variants.items():
        features = V3_FEATURES + extras
        pipeline = build_scaled_pipeline(V3_FEATURES[3:] + extras)
        pipeline.fit(train[features], train["target_refused"])
        p = pipeline.predict_proba(test[features])[:, 1]
        ci = bootstrap_auc_ci(y.to_numpy(), p)
        results[name] = {
            "n": int(len(y)),
            "roc_auc": round(float(roc_auc_score(y, p)), 4),
            "roc_auc_bootstrap95": [round(x, 4) for x in ci],
            "average_precision": round(float(average_precision_score(y, p)), 4),
            "brier": round(float(brier_score_loss(y, np.clip(p, 1e-6, 1 - 1e-6))), 4),
            "log_loss": round(float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))), 4),
        }
        by_year = {}
        for year, group in test.groupby(test["received_date_dt"].dt.year):
            p_year = p[group.index]
            by_year[str(year)] = {
                "n": int(len(group)),
                "refusal_rate": round(float(group["target_refused"].mean()), 4),
                "roc_auc": round(float(roc_auc_score(group["target_refused"], p_year)), 4),
                "average_precision": round(float(average_precision_score(group["target_refused"], p_year)), 4),
            }
        results[name]["by_year"] = by_year
        ge10 = test[test["units"] >= 10]
        if len(ge10) >= 20 and ge10["target_refused"].nunique() == 2:
            p_ge10 = p[(test["units"] >= 10).to_numpy()]
            ge10_ci = bootstrap_auc_ci(ge10["target_refused"].to_numpy(), p_ge10, n_boot=2000)
            results[name]["ge10_subset"] = {
                "n": int(len(ge10)),
                "refusal_rate": round(float(ge10["target_refused"].mean()), 4),
                "roc_auc": round(float(roc_auc_score(ge10["target_refused"], p_ge10)), 4),
                "roc_auc_bootstrap95": [round(x, 4) for x in ge10_ci],
                "average_precision": round(float(average_precision_score(ge10["target_refused"], p_ge10)), 4),
            }
        print(json.dumps({name: results[name]}), flush=True)
    results["frozen_v3_2025_reference"] = {"roc_auc": 0.7989, "average_precision": 0.4202}
    (OUTPUT_DIR / "raw_planning_8020_regime_experiment.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
