#!/usr/bin/env python3
"""Query-time feature builder + scorer for national_residential_v4_full.

Given a new proposal (authority, description, units, site area, floor area,
ITM coordinates, submission year), builds the full submission-time feature row
and scores it with the v4-full ranking model + isotonic calibration.

Reference tables are loaded lazily and cached module-level.
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "05_policy" / "current" / "model_v4"
MODEL_PATH = MODEL_DIR / "national_residential_v4_full.joblib"
COMPARABLE_PATH = MODEL_DIR / "comparable_reference.joblib"
SA_REF = ROOT / "07_context" / "current" / "sa_reference.parquet"
FLOOD_POINTS = ROOT / "07_context" / "current" / "flood_points.parquet"
PLAN_SUMMARY = ROOT / "07_context" / "current" / "plan_summary.parquet"
HISTORY_REF = ROOT / "07_context" / "current" / "history_reference.parquet"

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_dublin_submission_model import strip_text_leakage_clues  # noqa: E402
from build_raw_planning_benchmarks import residential_bucket  # noqa: E402
from build_v3_policy_features_challenger import DESC_TOKENS  # noqa: E402

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
THEME_ORDER = ["housing", "design", "zoning", "rural", "transport", "economic", "environment", "flood_water", "heritage", "community", "core"]


@lru_cache(maxsize=1)
def _load_state():
    artifact = joblib.load(MODEL_PATH)
    comparable = joblib.load(COMPARABLE_PATH)
    sa_ref = pd.read_parquet(SA_REF)
    sa_tree = cKDTree(sa_ref[["centroid_x", "centroid_y"]].to_numpy())
    flood = pd.read_parquet(FLOOD_POINTS)
    flood_tree = cKDTree(flood[["ITMEasting", "ITMNorthing"]].to_numpy())
    plans = pd.read_parquet(PLAN_SUMMARY)
    history = pd.read_parquet(HISTORY_REF)
    hist_tree = cKDTree(history[["ITMEasting", "ITMNorthing"]].to_numpy())
    return {
        "artifact": artifact,
        "comparable": comparable,
        "sa_ref": sa_ref,
        "sa_tree": sa_tree,
        "flood": flood,
        "flood_tree": flood_tree,
        "plans": plans,
        "history": history,
        "hist_tree": hist_tree,
    }


def _bucket_for(description: str, units: float) -> str:
    row = pd.Series({
        "NumResidentialUnits": units if units is not None and not pd.isna(units) else 0.0,
        "OneOffHouse": "",
        "DevelopmentDescription": description or "",
    })
    try:
        return str(residential_bucket(row))
    except Exception:
        return "other residential"


def nearest_comparables(proposal: dict, k: int = 20) -> dict:
    """Return the frozen-reference nearest comparable indices and similarities
    for a proposal, for display purposes only. Uses exactly the same bucket
    and the same cosine-NN search as the scoring path."""
    state = _load_state()
    description = strip_text_leakage_clues(proposal.get("description") or "") or ""
    units = proposal.get("units")
    units = float(units) if units is not None else np.nan
    bucket = proposal.get("application_type") or _bucket_for(description, units)
    bucket_data = state["comparable"]["buckets"].get(bucket)
    if bucket_data is None or not description:
        return {"bucket": bucket, "indices": [], "similarities": [], "available": 0}
    from sklearn.neighbors import NearestNeighbors

    query = state["comparable"]["vectorizer"].transform([description])
    nn = NearestNeighbors(n_neighbors=min(k, bucket_data["matrix"].shape[0]), metric="cosine", algorithm="brute", n_jobs=1)
    nn.fit(bucket_data["matrix"])
    distances, indices = nn.kneighbors(query)
    sims = np.clip(1.0 - distances[0], 0.0, 1.0)
    return {"bucket": bucket, "indices": indices[0].tolist(), "similarities": sims.tolist(), "available": bucket_data["matrix"].shape[0]}


def _history_features(state, authority: str, year: int, easting: float, northing: float):
    hist = state["history"]
    latest = pd.to_datetime(hist["received_date_dt"]).max()
    horizon = latest - pd.DateOffset(months=24)
    horizon_12 = latest - pd.DateOffset(months=12)
    recent = hist[hist["received_date_dt"] >= horizon]
    national_count = len(recent)
    national_rate = float(recent["target_refused"].fillna(0).mean()) if national_count else np.nan
    auth = recent[recent["PlanningAuthority"] == authority]
    auth_24_count = len(auth)
    auth_24_rate = float(auth["target_refused"].fillna(0).mean()) if auth_24_count else np.nan
    auth_12 = recent[recent["received_date_dt"] >= horizon_12]
    auth_12 = auth_12[auth_12["PlanningAuthority"] == authority]
    auth_12_count = len(auth_12)
    auth_12_rate = float(auth_12["target_refused"].fillna(0).mean()) if auth_12_count else np.nan

    same_site = hist[(hist["SiteId"].notna()) & (hist["SiteId"] != "")] if "SiteId" in hist.columns else hist.iloc[0:0]
    same_site_count = 0
    same_site_rate = np.nan
    if "SiteId" in hist.columns and easting is not None and northing is not None:
        near = hist.iloc[state["hist_tree"].query_ball_point([easting, northing], 50.0)]
        same_site_count = len(near)
        same_site_rate = float(near["target_refused"].fillna(0).mean()) if same_site_count else np.nan
    nearby_counts = {}
    nearby_rates = {}
    for radius, tag in ((1000.0, "nearby_1km"), (3000.0, "nearby_3km")):
        if easting is not None and northing is not None:
            near = hist.iloc[state["hist_tree"].query_ball_point([easting, northing], radius)]
            nearby_counts[tag] = len(near)
            nearby_rates[tag] = float(near["target_refused"].fillna(0).mean()) if len(near) else np.nan
        else:
            nearby_counts[tag] = 0
            nearby_rates[tag] = np.nan
    out = {
        "national_prior_24m_count": national_count,
        "national_prior_24m_refusal_rate": national_rate,
        "authority_prior_12m_count": auth_12_count,
        "authority_prior_12m_refusal_rate": auth_12_rate,
        "authority_prior_24m_count": auth_24_count,
        "authority_prior_24m_refusal_rate": auth_24_rate,
        "same_site_prior_count": same_site_count,
        "same_site_prior_refusal_rate": same_site_rate,
        "nearby_1km_prior_24m_count": nearby_counts["nearby_1km"],
        "nearby_1km_prior_24m_refusal_rate": nearby_rates["nearby_1km"],
        "nearby_3km_prior_24m_count": nearby_counts["nearby_3km"],
        "nearby_3km_prior_24m_refusal_rate": nearby_rates["nearby_3km"],
    }
    for key in list(out):
        if key.endswith("_count"):
            out[f"log_{key}"] = np.log1p(float(out[key]) if out[key] is not None else 0)
    return out


def _comparable_features(state, bucket: str, description: str):
    comp = state["comparable"]
    vectorizer = comp["vectorizer"]
    bucket_data = comp["buckets"].get(bucket)
    if bucket_data is None or not description:
        return {f"comp_top{k}_refusal_rate": np.nan for k in (5, 10, 20)} | {
            "comp_top20_mean_similarity": np.nan,
            "comp_top20_max_refused_similarity": np.nan,
            "comp_top20_max_granted_similarity": np.nan,
            "comp_top20_refused_similarity_gap": np.nan,
            "comp_top20_same_authority_share": np.nan,
            "comp_top20_same_authority_refusal_rate": np.nan,
            "comp_top20_count": 0.0,
        }
    from sklearn.neighbors import NearestNeighbors

    query = vectorizer.transform([description])
    nn = NearestNeighbors(n_neighbors=min(20, bucket_data["matrix"].shape[0]), metric="cosine", algorithm="brute", n_jobs=1)
    nn.fit(bucket_data["matrix"])
    distances, indices = nn.kneighbors(query)
    sims = np.clip(1.0 - distances[0], 0.0, 1.0)
    targets = bucket_data["targets"][indices[0]]
    authorities = bucket_data["authorities"][indices[0]]
    out: dict[str, float] = {}
    for k in (5, 10, 20):
        kk = min(k, len(sims))
        out[f"comp_top{k}_refusal_rate"] = float(targets[:kk].mean())
    out["comp_top20_mean_similarity"] = float(sims.mean())
    refused_sim = np.where(targets == 1, sims, np.nan)
    granted_sim = np.where(targets == 0, sims, np.nan)
    out["comp_top20_max_refused_similarity"] = float(np.nanmax(refused_sim)) if np.isfinite(refused_sim).any() else np.nan
    out["comp_top20_max_granted_similarity"] = float(np.nanmax(granted_sim)) if np.isfinite(granted_sim).any() else np.nan
    out["comp_top20_refused_similarity_gap"] = out["comp_top20_max_refused_similarity"] - out["comp_top20_max_granted_similarity"]
    out["comp_top20_same_authority_share"] = float(np.mean(authorities == None))  # placeholder replaced below
    return out


def _plan_features(state, authority: str, year: int, description: str):
    plans = state["plans"]
    candidates = plans[(plans["council"] == authority) & (plans["start"] <= year) & (plans["end"] >= year)]
    if candidates.empty:
        covered = 0
        row = {f"plan_theme_{t}": 0 for t in THEME_ORDER}
        row["plan_theme_other"] = 0
        unique = mentions = 0
    else:
        covered = 1
        chosen = candidates.sort_values("start", ascending=False).iloc[0]
        row = {f"plan_theme_{t}": float(chosen[f"plan_theme_{t}"]) for t in THEME_ORDER}
        row["plan_theme_other"] = float(chosen["plan_theme_other"])
        unique = float(chosen["plan_unique_codes"])
        mentions = float(chosen["plan_mentions"])
    match_codes = 0
    if description:
        text = str(description).lower()
        if any(token in text for token in DESC_TOKENS):
            match_codes = 1.0
    return {
        "log_plan_unique_codes": np.log1p(unique),
        "log_plan_mentions": np.log1p(mentions),
        "policy_plan_covered": covered,
        **row,
        "log_plan_codes_match_desc": np.log1p(match_codes),
    }


def build_feature_row(proposal: dict) -> pd.DataFrame:
    """proposal keys: authority, description, units, site_area_sqm, floor_area_sqm,
    itm_easting, itm_northing, submission_year, application_type (optional)."""
    state = _load_state()
    authority = proposal["authority"]
    description = strip_text_leakage_clues(proposal.get("description") or "") or ""
    units = proposal.get("units")
    units = float(units) if units is not None else np.nan
    site_sqm = proposal.get("site_area_sqm")
    site_sqm = float(site_sqm) if site_sqm is not None else np.nan
    floor_sqm = proposal.get("floor_area_sqm")
    floor_sqm = float(floor_sqm) if floor_sqm is not None else np.nan
    easting = proposal.get("itm_easting")
    northing = proposal.get("itm_northing")
    year = int(proposal.get("submission_year") or 2026)

    bucket = proposal.get("application_type") or _bucket_for(description, units)
    row: dict = {
        "PlanningAuthority": authority,
        "application_bucket": bucket,
        "description_stripped": description,
        "received_year": float(year),
    }

    hist = _history_features(state, authority, year, easting, northing)
    row.update(hist)

    if easting is not None and northing is not None:
        dist, idx = state["sa_tree"].query([easting, northing], k=1)
        sa = state["sa_ref"].iloc[int(idx)]
        row["log_pop_density"] = np.log1p(float(sa["pop_density_per_sqkm"]))
        row["owner_share"] = float(sa["owner_share"])
        row["private_rent_share"] = float(sa["private_rent_share"])
        row["la_rent_share"] = float(sa["la_rent_share"])
        row["septic_share"] = float(sa["septic_share"])
        row["cars_per_hh"] = float(sa["cars_per_hh"])
        row["no_car_share"] = float(sa["no_car_share"])
        row["is_urban"] = float(sa["is_urban"])
        fdist, fidx = state["flood_tree"].query([easting, northing], k=1)
        flood_row = state["flood"].iloc[int(fidx)]
        for feature in FLOOD_FEATURES:
            row[feature] = float(flood_row[feature])
        row["flood_any"] = 1.0 if (row.get("fluvial_hit_any") or row.get("coastal_hit_any")) else 0.0
        row["_nearest_flood_m"] = float(fdist)
    else:
        for feature in FLOOD_FEATURES + ["log_pop_density", "owner_share", "private_rent_share", "la_rent_share", "septic_share", "cars_per_hh", "no_car_share", "is_urban", "flood_any"]:
            row[feature] = np.nan
        row["_nearest_flood_m"] = np.nan
    row["log_national_road_dist"] = row.get("log_national_road_dist", np.nan)
    row["national_roads_within_1km"] = row.get("national_roads_within_1km", np.nan)

    row.update(_plan_features(state, authority, year, description))
    comp = _comparable_features(state, bucket, description)
    comp.pop("comp_top20_same_authority_share", None)
    row["comp_top20_same_authority_share"] = np.nan
    row.update(comp)

    site_ha = site_sqm / 10000.0 if site_sqm is not None and not np.isnan(site_sqm) else np.nan
    row["log_units"] = np.log1p(max(units, 0)) if not pd.isna(units) else np.nan
    row["log_site_area_sqm"] = np.log1p(site_sqm) if not pd.isna(site_sqm) else np.nan
    row["log_floor_area_sqm"] = np.log1p(floor_sqm) if not pd.isna(floor_sqm) else np.nan
    row["units_missing"] = 1 if pd.isna(units) else 0
    row["applicant_prior_count"] = 0
    row["applicant_prior_refusal_rate"] = np.nan
    density = units / site_ha if (not pd.isna(units) and not pd.isna(site_ha) and site_ha > 0) else np.nan
    density = min(density, 1000) if not pd.isna(density) else density
    far = floor_sqm / site_sqm if (not pd.isna(floor_sqm) and not pd.isna(site_sqm) and site_sqm > 0) else np.nan
    far = min(far, 5) if not pd.isna(far) else far
    site_per_unit = site_sqm / units if (not pd.isna(units) and units > 0 and not pd.isna(site_sqm)) else np.nan
    site_per_unit = min(site_per_unit, 5000) if not pd.isna(site_per_unit) else site_per_unit
    avg_unit_floor = floor_sqm / units if (not pd.isna(units) and units > 0 and not pd.isna(floor_sqm)) else np.nan
    avg_unit_floor = min(avg_unit_floor, 300) if not pd.isna(avg_unit_floor) else avg_unit_floor
    row["density_units_per_ha"] = density
    row["floor_area_ratio"] = far
    row["site_sqm_per_unit"] = site_per_unit
    row["avg_unit_floor_sqm"] = avg_unit_floor
    row["density_missing"] = 1 if pd.isna(density) else 0
    row["density_band_low"] = 1 if (not pd.isna(density) and density < 35) else 0
    row["density_band_mid"] = 1 if (not pd.isna(density) and 35 <= density <= 50) else 0
    row["density_band_high"] = 1 if (not pd.isna(density) and density > 50) else 0
    row["density_over_45"] = 1 if (not pd.isna(density) and density > 45) else 0
    landuse_text = (proposal.get("application_type") or "").upper()
    row["landuse_new_house"] = 1 if "SINGLE HOUSE" in landuse_text else 0
    row["landuse_housing_new"] = 1 if "HOUSING : NEW" in landuse_text else 0
    row["landuse_extension"] = 1 if "EXTENSION" in landuse_text else 0
    row["landuse_retention"] = 1 if "RETENTION" in landuse_text else 0
    row["landuse_missing"] = 0

    feature_columns = state["artifact"]["feature_columns"]
    frame = pd.DataFrame([{col: row.get(col, np.nan) for col in feature_columns}])
    return frame


def score_proposal(proposal: dict) -> dict:
    state = _load_state()
    frame = build_feature_row(proposal)
    ranking = state["artifact"]["ranking_model"]
    raw = float(ranking.predict_proba(frame)[:, 1][0])
    calibrated_base = state["artifact"]["calibrated_base_model"]
    iso = state["artifact"]["isotonic_calibrator"]
    base_score = float(calibrated_base.predict_proba(frame)[:, 1][0])
    risk = float(iso.predict(np.array([base_score]))[0])
    thresholds = state["artifact"]["risk_band_thresholds"]
    band = "low" if risk <= thresholds["low_max"] else ("medium" if risk <= thresholds["medium_max"] else "high")
    return {
        "model_version": state["artifact"]["model_version"],
        "raw_ranking_score": round(raw, 4),
        "refusal_probability": round(risk, 4),
        "grant_probability": round(1.0 - risk, 4),
        "risk_band": band,
        "risk_band_thresholds": {k: round(v, 4) for k, v in thresholds.items()},
        "inputs": {k: proposal.get(k) for k in ("authority", "description", "units", "site_area_sqm", "floor_area_sqm", "itm_easting", "itm_northing", "submission_year")},
    }


if __name__ == "__main__":
    demo = {
        "authority": "Dun Laoghaire Rathdown County Council",
        "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
        "units": 12,
        "site_area_sqm": 4000,
        "floor_area_sqm": 2400,
        "itm_easting": 722000,
        "itm_northing": 726500,
        "submission_year": 2026,
    }
    import json

    print(json.dumps(score_proposal(demo), indent=2))
