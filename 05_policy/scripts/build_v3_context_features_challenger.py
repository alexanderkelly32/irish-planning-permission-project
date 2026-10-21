#!/usr/bin/env python3
"""v3 challenger with case-level context features:

- register ratios: density (units/ha), floor-area ratio, site-per-unit, avg unit floor area
- national-guideline density-band flags (35/45/50 dph)
- LandUseCode scheme flags (new house, housing new, extension, retention)
- time-safe spatial prevailing-density context (earlier cases within 1km/3km)
- national transit access (TFI GTFS stops: nearest distance, stops within 400m/800m)

Variants:
  E = A + register ratios + bands + landuse flags
  F = E + spatial density context
  G = F + transit access

Same pre-2025/2025 split, frozen baseline 0.7989/0.4202, GE10 subset reported.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_comparable_feature_experiment import COMPARABLE_FEATURES_PATH, V3_FEATURES  # noqa: E402
from build_national_residential_model_v2 import TRAIN_CUTOFF, load_data_with_history  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

FLOOD_CSV = ROOT / "01_flood" / "current" / "all_cases_with_flooding.parquet"
TRANSIT_STOPS = ROOT / "07_context" / "current" / "national_transit_stops.parquet"
CASE_CONTEXT = ROOT / "07_context" / "current" / "case_context_features.parquet"


def landuse_flags(values: pd.Series) -> pd.DataFrame:
    text = values.fillna("").astype(str).str.upper()
    return pd.DataFrame({
        "landuse_new_house": text.str.contains("SINGLE HOUSE", regex=False).astype(int),
        "landuse_housing_new": text.str.contains("HOUSING : NEW", regex=False).astype(int),
        "landuse_extension": text.str.contains("EXTENSION", regex=False).astype(int),
        "landuse_retention": text.str.contains("RETENTION", regex=False).astype(int),
        "landuse_missing": values.isna().astype(int),
    })


def spatial_density_context(data: pd.DataFrame) -> pd.DataFrame:
    coords = data[["ITMEasting", "ITMNorthing"]].to_numpy(dtype=float)
    dates = pd.to_datetime(data["received_date_dt"]).to_numpy(dtype="datetime64[ns]")
    density = pd.to_numeric(data["density_units_per_ha"], errors="coerce").to_numpy()
    units = pd.to_numeric(data["units"], errors="coerce").to_numpy()
    tree = cKDTree(coords)
    out = pd.DataFrame(index=data.index)
    for radius, tag in ((1000.0, "1km"), (3000.0, "3km")):
        print(f"  spatial radius {tag}...", flush=True)
        neighbors = tree.query_ball_point(coords, radius, workers=-1)
        n = len(neighbors)
        mean_density = np.zeros(n)
        max_units = np.zeros(n)
        counts = np.zeros(n)
        for i in range(n):
            idx = neighbors[i]
            if not idx:
                continue
            idx = np.asarray(idx)
            earlier = dates[idx] < dates[i]
            if not earlier.any():
                continue
            sel = idx[earlier]
            den = density[sel]
            den = den[np.isfinite(den) & (den > 0)]
            if den.size:
                mean_density[i] = den.mean()
            uni = units[sel]
            uni = uni[np.isfinite(uni)]
            if uni.size:
                max_units[i] = uni.max()
            counts[i] = sel.size
        out[f"nearby_{tag}_prior_density_mean"] = mean_density
        out[f"nearby_{tag}_prior_units_max"] = max_units
        out[f"nearby_{tag}_prior_count"] = counts
    out["density_vs_nearby1km_gap"] = data["density_units_per_ha"].to_numpy() - out["nearby_1km_prior_density_mean"].to_numpy()
    out["density_vs_nearby1km_ratio"] = np.divide(
        data["density_units_per_ha"].to_numpy(), out["nearby_1km_prior_density_mean"].to_numpy(),
        out=np.zeros(len(out)), where=out["nearby_1km_prior_density_mean"].to_numpy() > 0,
    )
    return out


def transit_features(data: pd.DataFrame) -> pd.DataFrame:
    stops = pd.read_parquet(TRANSIT_STOPS)
    stop_xy = stops[["ITMEasting", "ITMNorthing"]].to_numpy(dtype=float)
    tree = cKDTree(stop_xy)
    coords = data[["ITMEasting", "ITMNorthing"]].to_numpy(dtype=float)
    dist, _ = tree.query(coords, k=1, workers=-1)
    out = pd.DataFrame(index=data.index)
    out["log_nearest_stop_dist"] = np.log1p(dist)
    for radius, tag in ((400.0, "400m"), (800.0, "800m")):
        counts = tree.query_ball_point(coords, radius, workers=-1, return_length=True)
        out[f"stops_within_{tag}"] = counts
    return out


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
    applicant_history: dict[str, list[tuple[int, int]]] = {}
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
    data["density_units_per_ha"] = np.divide(units, site_ha, out=np.full(len(data), np.nan), where=(site_ha > 0) & units.notna())
    data["density_units_per_ha"] = data["density_units_per_ha"].clip(upper=1000)
    data["floor_area_ratio"] = np.divide(floor, site_ha * 10000, out=np.full(len(data), np.nan), where=site_ha > 0).clip(upper=5)
    data["site_sqm_per_unit"] = np.divide(site_ha * 10000, units, out=np.full(len(data), np.nan), where=units > 0).clip(upper=5000)
    data["avg_unit_floor_sqm"] = np.divide(floor, units, out=np.full(len(data), np.nan), where=units > 0).clip(upper=300)
    density = data["density_units_per_ha"]
    data["density_band_low"] = (density < 35).astype(int)
    data["density_band_mid"] = ((density >= 35) & (density <= 50)).astype(int)
    data["density_band_high"] = (density > 50).astype(int)
    data["density_over_45"] = (density > 45).astype(int)
    data["density_missing"] = density.isna().astype(int)

    landuse = landuse_flags(data["LandUseCode"])
    data = pd.concat([data, landuse], axis=1)

    print("loading CSO/TII case context...", flush=True)
    context = pd.read_parquet(CASE_CONTEXT)
    data = data.merge(context, on="case_key", how="left")
    for col in ["pop_density_per_sqkm", "owner_share", "private_rent_share", "la_rent_share", "septic_share", "cars_per_hh", "no_car_share", "national_road_dist_m", "national_roads_within_1km", "is_urban"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["log_pop_density"] = np.log1p(data["pop_density_per_sqkm"])
    data["log_national_road_dist"] = np.log1p(data["national_road_dist_m"])
    data["is_urban"] = data["is_urban"].fillna(0)
    data["density_x_urban"] = data["density_units_per_ha"].fillna(0) * data["is_urban"]
    data["far_x_urban"] = data["floor_area_ratio"].fillna(0) * data["is_urban"]

    print("simple case-level extras...", flush=True)
    train_mask = data["received_date_dt"] < TRAIN_CUTOFF
    log_density = np.log1p(data["density_units_per_ha"].clip(lower=0))
    train_log_density = log_density[train_mask]
    for feature, values, train_values in (
        ("density_z_council", log_density, train_log_density),
        ("far_z_council", np.log1p(data["floor_area_ratio"].clip(lower=0)), np.log1p(data["floor_area_ratio"].clip(lower=0))[train_mask]),
    ):
        group_means = train_values.groupby(data["PlanningAuthority"][train_mask]).mean()
        group_stds = train_values.groupby(data["PlanningAuthority"][train_mask]).std().replace(0, np.nan)
        data[feature] = (values - data["PlanningAuthority"].map(group_means)) / data["PlanningAuthority"].map(group_stds)

    company_pattern = r"\b(ltd|limited|holdings|developments|properties|group|construction|builders|homes|company|clg|co\.|investments|estates)\b"
    surname = data["ApplicantSurname"].fillna("").astype(str)
    forename = data["ApplicantForename"].fillna("").astype(str)
    data["applicant_is_company"] = (surname.str.contains(company_pattern, case=False, regex=True) | forename.str.contains(company_pattern, case=False, regex=True)).astype(int)

    desc = data["description_stripped"].fillna("").astype(str)
    data["log_desc_chars"] = np.log1p(desc.str.len())
    data["log_desc_words"] = np.log1p(desc.str.split().str.len())
    data["desc_has_digits"] = desc.str.contains(r"\d", regex=True).astype(int)

    month = pd.to_datetime(data["received_date_dt"]).dt.month.astype(float)
    data["month_sin"] = np.sin(2 * np.pi * month / 12)
    data["month_cos"] = np.cos(2 * np.pi * month / 12)

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
    spatial_extras = []
    transit_extras = []
    context_extras = [
        "log_pop_density", "owner_share", "private_rent_share", "la_rent_share",
        "septic_share", "cars_per_hh", "no_car_share",
        "log_national_road_dist", "national_roads_within_1km",
        "is_urban",
    ]
    simple_extras = [
        "density_z_council", "far_z_council",
        "density_x_urban", "far_x_urban",
        "applicant_is_company",
        "log_desc_chars", "log_desc_words", "desc_has_digits",
        "month_sin", "month_cos",
    ]

    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].copy().reset_index(drop=True)
    y = test["target_refused"]

    results: dict[str, object] = {
        "frozen_v3_baseline": {"roc_auc": 0.7989, "average_precision": 0.4202},
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "density_coverage_holdout": round(float(test["density_missing"].eq(0).mean()), 4),
    }

    variants = {
        "E_plus_register_ratios_bands": base_extras + policy_extras + ratio_extras,
        "H_plus_cso_context": base_extras + policy_extras + ratio_extras + context_extras,
        "I_plus_simple_extras": base_extras + policy_extras + ratio_extras + context_extras + simple_extras,
    }
    for name, extras in variants.items():
        features = V3_FEATURES + extras
        pipeline = build_scaled_pipeline(V3_FEATURES[3:] + extras)
        pipeline.fit(train[features], train["target_refused"])
        p = pipeline.predict_proba(test[features])[:, 1]
        results[name] = {
            "roc_auc": round(float(roc_auc_score(y, p)), 4),
            "average_precision": round(float(average_precision_score(y, p)), 4),
        }
        ge10_test = test[test["units"] >= 10].reset_index(drop=True)
        if len(ge10_test) >= 20 and ge10_test["target_refused"].nunique() == 2:
            p_ge10 = p[test["units"] >= 10]
            results[name]["ge10_subset"] = {
                "n": int(len(ge10_test)),
                "auc": round(float(roc_auc_score(ge10_test["target_refused"], p_ge10)), 4),
                "ap": round(float(average_precision_score(ge10_test["target_refused"], p_ge10)), 4),
            }
    results["caveat"] = (
        "All features submission-time: register ratios from the application form, guideline bands from "
        "national policy, spatial context from earlier cases only, transit from TFI GTFS static feed."
    )
    (OUTPUT_DIR / "raw_planning_v3_context_features_challenger.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
