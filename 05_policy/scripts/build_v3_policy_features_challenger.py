#!/usr/bin/env python3
"""v3 challenger with policy-layer features (objective-code layer).

Variant A (policy layer only): plan-in-force code coverage + theme counts.
Variant B (+ citation history): time-safe historical refusal-reason citation
rates (earlier cases in same council only - same class as v3 comparable
aggregates, but derived from refusal text; flagged for decision).

Same pre-2025/2025 split and frozen baseline (0.7989/0.4202). Also reports the
GE10-subset AUC, where policy strictness should matter most.
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
LAYER_CSV = OUTPUT_DIR / "objective_code_layer.csv"
REASONS_LONG = ROOT / "03_refusal" / "current" / "refusal_reasons_long_master.csv"

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
THEME_PREFIXES = {
    "housing": {"HO", "HOU", "HS", "RES", "RH", "AH", "HP"},
    "design": {"DM", "DMS", "DES", "DEV", "UD", "QDP"},
    "zoning": {"Z", "ZU", "ZO", "LU", "LZ"},
    "rural": {"RF", "RU", "RS"},
    "transport": {"TP", "TR", "TS", "TM", "PT", "TT"},
    "economic": {"EC", "ED", "RE", "RD", "ET", "EMP", "JOB"},
    "environment": {"EN", "EA", "BIO", "NH", "GI", "AQ", "NAT"},
    "flood_water": {"FL", "SF", "WS", "FR"},
    "heritage": {"BH", "CH", "HER", "HAR", "AC"},
    "community": {"CS", "CO", "CF", "CA", "SC", "CM", "SS"},
    "core": {"CORE", "CSS", "CSP", "CSO", "V"},
}

CODE_CITE_PATTERN = re.compile(
    r"\b(?:objective|policy|objectives|policies)\s+(?:no\.?\s*)?[A-Z0-9][A-Z0-9.\- ]{0,14}",
    re.IGNORECASE,
)
PLAN_CITE_PATTERN = re.compile(r"development plan", re.IGNORECASE)

DESC_TOKENS = [
    "parking", "car park", "open space", "height", "storey", "density", "unit",
    "apartment", "terrace", "semi", "detached", "duplex", "own door", "backland",
    "overlooking", "daylight", "amenity", "estate", "infill", "corner",
]


def code_context_hits(layer: pd.DataFrame) -> pd.DataFrame:
    hit_rows = []
    for token in DESC_TOKENS:
        mask = layer["context"].astype(str).str.contains(token, case=False, na=False)
        hit_rows.append(layer.loc[mask, ["council", "plan_period", "objective_code", "mentions"]].assign(token=token))
    if not hit_rows:
        return pd.DataFrame(columns=["council", "plan_period", "token", "n_codes", "mentions"])
    hits = pd.concat(hit_rows, ignore_index=True)
    agg = hits.groupby(["council", "plan_period", "token"]).agg(
        n_codes=("objective_code", "nunique"), mentions=("mentions", "sum")
    ).reset_index()
    return agg


def theme_of(code: str) -> str:
    letters = re.sub(r"[^A-Za-z]", "", str(code)).upper()
    for candidate in (letters, letters[:3], letters[:2], letters[:1]):
        if not candidate:
            continue
        for theme in THEME_ORDER:
            if candidate in THEME_PREFIXES[theme]:
                return theme
    return "other"


def build_plan_features(data: pd.DataFrame) -> pd.DataFrame:
    layer = pd.read_csv(LAYER_CSV, low_memory=False)
    layer["council"] = layer["council"].replace("Limerick City and County Council", "Limerick County Council")
    layer["start"] = pd.to_numeric(layer["plan_period"].str.split("-").str[0], errors="coerce")
    layer["end"] = pd.to_numeric(layer["plan_period"].str.split("-").str[1], errors="coerce")
    layer = layer.dropna(subset=["start", "end"])
    layer["theme"] = layer["objective_code"].map(theme_of)
    token_agg = code_context_hits(layer)

    records = []
    for (council, period), group in layer.groupby(["council", "plan_period"]):
        records.append({
            "council": council,
            "start": int(group["start"].iloc[0]),
            "end": int(group["end"].iloc[0]),
            "plan_unique_codes": int(group["objective_code"].nunique()),
            "plan_mentions": int(group["mentions"].sum()),
            **{f"plan_theme_{t}": int(group.loc[group["theme"] == t, "objective_code"].nunique()) for t in THEME_ORDER},
            "plan_theme_other": int(group.loc[group["theme"] == "other", "objective_code"].nunique()),
        })
    plans = pd.DataFrame(records).sort_values(["council", "start"])

    out: list[dict] = []
    data_year = data["received_year"]
    for i, (council, case_key, description) in enumerate(data[["PlanningAuthority", "case_key", "description_stripped"]].itertuples(index=False)):
        year = data_year.iloc[i]
        candidates = plans[(plans["council"] == council) & (plans["start"] <= year) & (plans["end"] >= year)]
        entry: dict = {"case_key": case_key}
        if candidates.empty:
            out.append(entry)
            continue
        chosen = candidates.sort_values("start", ascending=False).iloc[0]
        period = f"{int(chosen['start'])}-{int(chosen['end'])}"
        entry.update({k: chosen[k] for k in ["plan_unique_codes", "plan_mentions", *[f"plan_theme_{t}" for t in THEME_ORDER], "plan_theme_other"]})
        description_text = str(description or "").lower()
        matched_tokens = [t for t in DESC_TOKENS if t in description_text]
        plan_token_rows = token_agg[(token_agg["council"] == council) & (token_agg["plan_period"] == period)]
        if matched_tokens and not plan_token_rows.empty:
            sel = plan_token_rows[plan_token_rows["token"].isin(matched_tokens)]
            entry["plan_codes_match_desc"] = int(sel["n_codes"].sum())
            entry["plan_mentions_match_desc"] = int(sel["mentions"].sum())
        else:
            entry["plan_codes_match_desc"] = 0
            entry["plan_mentions_match_desc"] = 0
        out.append(entry)
    plan_feats = pd.DataFrame(out)
    return plan_feats


def build_citation_features(data: pd.DataFrame) -> pd.DataFrame:
    reasons = pd.read_csv(REASONS_LONG, low_memory=False)
    reasons = reasons.dropna(subset=["reason_text", "council", "application_number"])
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", str(s).lower())
    reasons["_appno"] = reasons["application_number"].astype(str).map(norm)
    reasons["code_cite"] = reasons["reason_text"].astype(str).str.contains(CODE_CITE_PATTERN)
    reasons["plan_cite"] = reasons["reason_text"].astype(str).str.contains(PLAN_CITE_PATTERN)
    case_flags = reasons.groupby(["council", "_appno"]).agg(
        code_cite=("code_cite", "any"), plan_cite=("plan_cite", "any"), reason_count=("reason_text", "size")
    ).reset_index()

    data["_appno"] = data["case_key"].astype(str).str.split("__", n=1).str[-1].map(norm)
    joined = data.merge(case_flags, left_on=["PlanningAuthority", "_appno"], right_on=["council", "_appno"], how="left", suffixes=("", "_r"))
    joined = joined.drop(columns=["council"])
    joined["received_date_dt"] = pd.to_datetime(joined["received_date_dt"])
    joined = joined.sort_values("received_date_dt").reset_index(drop=True)

    timeline: dict[str, list[tuple[pd.Timestamp, int, int]]] = {}
    n = len(joined)
    cum_code = np.zeros(n)
    cum_plan = np.zeros(n)
    cum_reasons = np.zeros(n)
    for i in range(n):
        row = joined.iloc[i]
        council = row["PlanningAuthority"]
        prior = timeline.get(council, [])
        cum_code[i] = sum(1 for _, c, _ in prior if c)
        cum_plan[i] = sum(1 for _, _, p in prior if p)
        cum_reasons[i] = len(prior)
        if pd.notna(row.get("reason_count")):
            timeline.setdefault(council, []).append((row["received_date_dt"], bool(row["code_cite"]), bool(row["plan_cite"])))

    joined["hist_code_cite_count"] = cum_code
    joined["hist_plan_cite_count"] = cum_plan
    joined["hist_reasons_count"] = cum_reasons
    joined["hist_code_cite_rate"] = np.divide(cum_code, cum_reasons, out=np.zeros(n), where=cum_reasons > 0)
    joined["hist_plan_cite_rate"] = np.divide(cum_plan, cum_reasons, out=np.zeros(n), where=cum_reasons > 0)
    joined["citation_history_covered"] = (cum_reasons > 0).astype(int)
    return joined[["case_key", "hist_code_cite_count", "hist_plan_cite_count", "hist_reasons_count", "hist_code_cite_rate", "hist_plan_cite_rate", "citation_history_covered"]]


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
    plan_feats = build_plan_features(data)
    data = data.merge(plan_feats, on="case_key", how="left")
    plan_cols = ["plan_unique_codes", "plan_mentions", "plan_codes_match_desc", "plan_mentions_match_desc"] + [f"plan_theme_{t}" for t in THEME_ORDER] + ["plan_theme_other"]
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
    data["plan_theme_design_x_units"] = data["plan_theme_design"] * data["log_units"]
    data["plan_theme_zoning_x_units"] = data["plan_theme_zoning"] * data["log_units"]
    data["plan_codes_match_x_units"] = data["log_plan_codes_match_desc"] * data["log_units"]

    citation = build_citation_features(data)
    data = data.merge(citation, on="case_key", how="left")
    for col in ["hist_code_cite_count", "hist_plan_cite_count", "hist_reasons_count", "hist_code_cite_rate", "hist_plan_cite_rate", "citation_history_covered"]:
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    base_extras = [
        "log_units", "log_site_area_sqm", "log_floor_area_sqm", "units_missing",
        "applicant_prior_count", "applicant_prior_refusal_rate",
        *FLOOD_FEATURES, "flood_any",
    ]
    policy_extras = [
        "log_plan_unique_codes", "log_plan_mentions", "policy_plan_covered",
        *[f"plan_theme_{t}" for t in THEME_ORDER], "plan_theme_other",
        "log_plan_codes_match_desc",
    ]
    policy_interactions = ["plan_theme_design_x_units", "plan_theme_zoning_x_units", "plan_codes_match_x_units"]
    citation_extras = ["hist_code_cite_rate", "hist_plan_cite_rate", "hist_reasons_count", "citation_history_covered"]

    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].copy().reset_index(drop=True)
    y = test["target_refused"]

    results: dict[str, object] = {
        "frozen_v3_baseline": {"roc_auc": 0.7989, "average_precision": 0.4202},
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "policy_plan_coverage_holdout": round(float(test["policy_plan_covered"].mean()), 4),
        "citation_history_coverage_holdout": round(float(test["citation_history_covered"].mean()), 4),
    }

    variants = {
        "A_base_plus_policy_layer": base_extras + policy_extras,
        "C_plus_interactions": base_extras + policy_extras + policy_interactions,
        "D_plus_interactions_citations": base_extras + policy_extras + policy_interactions + citation_extras,
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
        "Policy-layer features are submission-time. Variant B uses historical refusal-reason "
        "citation rates (earlier same-council cases only, same class as v3 comparable aggregates) "
        "- flagged for decision before any promotion."
    )
    (OUTPUT_DIR / "raw_planning_v3_policy_features_challenger.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
