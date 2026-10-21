#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.metrics.pairwise import linear_kernel
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = ROOT / "05_policy"
CURRENT_DIR = POLICY_ROOT / "current"
MODEL_DIR = CURRENT_DIR / "models"

INPUT_CASES = ROOT / "04_fi" / "current" / "greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv"
FLOOD_DATA = ROOT / "01_flood" / "current" / "ge10_with_flooding.csv"
POLICY_MANIFEST = POLICY_ROOT / "source_data" / "dublin_policy_manifest.csv"
POLICY_CHUNKS = CURRENT_DIR / "policy_chunks.csv"
POLICY_CLAUSE_TAGS = CURRENT_DIR / "policy_clause_tags.csv"

DUBLIN_AUTHORITIES = {
    "Dublin City Council",
    "Dun Laoghaire Rathdown County Council",
    "Fingal County Council",
    "South Dublin County Council",
}

TEXT_COLUMNS = ["DevelopmentDescription", "DevelopmentAddress", "DevelopmentPostcode"]
NUMERIC_COLUMNS = [
    "received_year",
    "received_month",
    "received_quarter",
    "received_dayofweek",
    "units_total_best",
    "units_houses_best",
    "units_apartments_best",
    "units_duplex_best",
    "units_townhouses_best",
    "units_bungalows_best",
    "bed_1_best",
    "bed_2_best",
    "bed_3_best",
    "bed_4_best",
    "bed_5_best",
    "parking_spaces_best",
    "cycle_parking_spaces_best",
    "site_area_ha_best",
    "site_area_sqm_best",
    "floor_area_sqm_best",
    "open_space_sqm_best",
    "max_storeys_best",
    "retail_area_sqm_best",
    "commercial_area_sqm_best",
    "creche_area_sqm_best",
    "serviced_sites_best",
    "ITMEasting",
    "ITMNorthing",
    "desc_chars",
    "desc_words",
    "case_units_density_per_ha",
    "case_parking_per_unit",
    "case_open_space_per_unit",
    "case_is_tall_scheme",
    "case_is_medium_height_scheme",
    "case_is_large_scheme",
    "case_low_parking_ratio",
    "case_high_density_pressure",
    "case_flood_pressure",
    "coastal_depth_max_m",
    "fluvial_depth_max_m",
    "coastal_hit_any",
    "fluvial_hit_any",
    "coastal_min_logdist",
    "fluvial_min_logdist",
]
CATEGORICAL_COLUMNS = [
    "PlanningAuthority",
    "ApplicationType",
    "LandUseCode",
    "OneOffHouse",
    "policy_coverage_flag",
    "policy_similarity_method",
]
BINARY_COLUMNS = [
    "has_retail_best",
    "has_commercial_best",
    "has_mixed_use_best",
    "has_creche_best",
    "has_community_best",
    "has_hotel_best",
    "has_industrial_best",
]

DEVELOPMENT_TYPE_COLUMNS = [
    "dev_type_apartment",
    "dev_type_houses",
    "dev_type_mixed_use",
    "dev_type_retention",
    "dev_type_demolition",
    "dev_type_outline",
    "dev_type_change_of_use",
    "dev_type_protected_structure",
    "dev_type_student",
    "dev_type_large_scheme",
]

BANNED_FEATURE_PATTERNS = [
    r"^Decision",
    r"^Grant",
    r"^Expiry",
    r"^Withdrawn",
    r"^Appeal",
    r"^FI",
    r"^fi_",
    r"^reason",
    r"^reasons",
    r"^case_primary",
    r"^case_top_primary",
    r"^has_refusal",
    r"^extraction_",
    r"ApplicationStatus",
]

THEME_COLUMNS_PREFIXES = ("policy_plan_", "policy_match_", "policy_similarity_")
THRESHOLDS = [0.20, 0.30, 0.40, 0.50, 0.60]
PRIMARY_EVAL_MODEL = "authority_year_devtype_text"


def safe_slug(value: object) -> str:
    text = str(value or "").strip().lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def normalize_application_number(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def build_merge_key(authority: object, appno: object) -> str:
    return f"{safe_slug(authority)}__{normalize_application_number(appno)}"


def parse_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def normalize_ws(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def strip_text_leakage_clues(value: object) -> str:
    text = normalize_ws(value).lower()
    replacements = [
        r"\b(dublin city council|dun laoghaire rathdown county council|dún laoghaire-rathdown county council|fingal county council|south dublin county council)\b",
        r"\b[a-z]?\d{1,3}[a-z]?[/\-]\d{2,5}\b",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{2,4}\b",
        r"\b(co\.|county)\s+dublin\b",
        r"\b(dublin\s+\d{1,2}|d\d{1,2})\b",
        r"\b\d+[a-z]?\s+(street|st|road|rd|avenue|ave|drive|lane|park|court|place|terrace|square|green|view|way|close|crescent)\b",
    ]
    for pattern in replacements:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{3,}\b", " ", text)
    return normalize_ws(text)


def compact_text_key(value: object, length: int = 80) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", normalize_ws(value).lower()).strip()
    return re.sub(r"\s+", " ", text)[:length]


def build_site_group_key(row: pd.Series) -> str:
    authority = safe_slug(row.get("PlanningAuthority"))
    easting = pd.to_numeric(pd.Series([row.get("ITMEasting")]), errors="coerce").iloc[0]
    northing = pd.to_numeric(pd.Series([row.get("ITMNorthing")]), errors="coerce").iloc[0]
    if pd.notna(easting) and pd.notna(northing):
        return f"{authority}__itm100_{int(round(float(easting) / 100.0))}_{int(round(float(northing) / 100.0))}"
    address = compact_text_key(row.get("DevelopmentAddress"), 80)
    if address:
        return f"{authority}__addr_{address}"
    return f"{authority}__desc_{compact_text_key(row.get('DevelopmentDescription'), 80)}"


def decision_to_submission_target(value: object) -> tuple[float, str]:
    if pd.isna(value):
        return np.nan, "missing_decision"
    text = re.sub(r"\s+", " ", str(value).strip().upper())
    if not text:
        return np.nan, "missing_decision"
    if any(token in text for token in ["INVALID", "WITHDRAW", "ADDITIONAL INFORMATION", "DECLARED EXEMPT", "NOT EXEMPT"]):
        return np.nan, "non_outcome_status"
    if "EXTENSION OF DURATION" in text or "EXT. OF DURATION" in text:
        return np.nan, "extension_of_duration"
    has_refuse = "REFUS" in text
    has_grant = "GRANT" in text or text in {"CONDITIONAL", "UNCONDITIONAL", "APPROVED", "MODIFIED"} or "APPROVED" in text
    if has_refuse and has_grant:
        return np.nan, "mixed_grant_refuse"
    if has_refuse:
        return 1.0, "refused"
    if has_grant:
        return 0.0, "granted"
    return np.nan, "unmapped_decision"


def load_flood_features() -> pd.DataFrame:
    df = pd.read_csv(FLOOD_DATA, low_memory=False)
    df = df[df["PlanningAuthority"].isin(DUBLIN_AUTHORITIES)].copy()
    df["merge_key"] = [build_merge_key(a, b) for a, b in zip(df["PlanningAuthority"], df["ApplicationNumber"])]
    keep = [
        "merge_key",
        "coastal_depth_max_m",
        "fluvial_depth_max_m",
        "coastal_hit_any",
        "fluvial_hit_any",
        "coastal_min_logdist",
        "fluvial_min_logdist",
    ]
    return df[[c for c in keep if c in df.columns]].drop_duplicates("merge_key")


def assign_policy_plan_by_received_date(cases: pd.DataFrame, manifest: pd.DataFrame) -> pd.DataFrame:
    downloaded = manifest[manifest["status"] == "downloaded"].copy()
    gaps = manifest[manifest["status"] == "missing_public_source"].copy()
    downloaded["plan_key"] = [
        f"{safe_slug(a)}__{int(s)}_{int(e)}"
        for a, s, e in zip(downloaded["authority"], downloaded["coverage_start_year"], downloaded["coverage_end_year"])
    ]
    plan_ranges = (
        downloaded.groupby(["authority", "coverage_start_year", "coverage_end_year", "plan_key"], as_index=False)
        .size()
        .sort_values(["authority", "coverage_start_year", "coverage_end_year"])
    )
    out = cases.copy()
    keys: list[str] = []
    flags: list[str] = []
    starts: list[float] = []
    ends: list[float] = []
    notes: list[str] = []
    for _, row in out.iterrows():
        authority = row["PlanningAuthority"]
        year = np.nan if pd.isna(row["received_date_dt"]) else row["received_date_dt"].year
        matches = plan_ranges[
            (plan_ranges["authority"] == authority)
            & (plan_ranges["coverage_start_year"] <= year)
            & (plan_ranges["coverage_end_year"] >= year)
        ].sort_values(["coverage_start_year", "coverage_end_year"], ascending=[False, False])
        if not matches.empty:
            chosen = matches.iloc[0]
            keys.append(chosen["plan_key"])
            flags.append("ok")
            starts.append(float(chosen["coverage_start_year"]))
            ends.append(float(chosen["coverage_end_year"]))
            notes.append("")
            continue
        gap = gaps[
            (gaps["authority"] == authority)
            & (gaps["coverage_start_year"] <= year)
            & (gaps["coverage_end_year"] >= year)
        ]
        if not gap.empty:
            chosen_gap = gap.iloc[0]
            keys.append("")
            flags.append("manifest_gap")
            starts.append(float(chosen_gap["coverage_start_year"]))
            ends.append(float(chosen_gap["coverage_end_year"]))
            notes.append(str(chosen_gap.get("note", "")))
            continue
        keys.append("")
        flags.append("no_plan_found")
        starts.append(np.nan)
        ends.append(np.nan)
        notes.append("")
    out["policy_plan_key"] = keys
    out["policy_coverage_flag"] = flags
    out["policy_plan_start_year"] = starts
    out["policy_plan_end_year"] = ends
    out["policy_gap_note"] = notes
    return out


def build_submission_text(row: pd.Series) -> str:
    parts = []
    for col in TEXT_COLUMNS:
        val = row.get(col)
        if pd.notna(val) and str(val).strip():
            parts.append(str(val))
    for col in ["units_total_best", "site_area_ha_best", "parking_spaces_best", "max_storeys_best"]:
        val = row.get(col)
        if pd.notna(val) and str(val).strip():
            parts.append(f"{col}: {val}")
    return normalize_ws(" ".join(parts))


def add_submission_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["received_date_dt"] = parse_date(out["ReceivedDate"])
    out["received_year"] = out["received_date_dt"].dt.year
    out["received_month"] = out["received_date_dt"].dt.month
    out["received_quarter"] = out["received_date_dt"].dt.quarter
    out["received_dayofweek"] = out["received_date_dt"].dt.dayofweek
    desc = out["DevelopmentDescription"].fillna("").astype(str)
    out["desc_chars"] = desc.str.len()
    out["desc_words"] = desc.str.split().str.len()
    out["case_units_density_per_ha"] = pd.to_numeric(out.get("units_total_best"), errors="coerce") / pd.to_numeric(
        out.get("site_area_ha_best"), errors="coerce"
    ).replace({0: np.nan})
    out["case_parking_per_unit"] = pd.to_numeric(out.get("parking_spaces_best"), errors="coerce") / pd.to_numeric(
        out.get("units_total_best"), errors="coerce"
    ).replace({0: np.nan})
    out["case_open_space_per_unit"] = pd.to_numeric(out.get("open_space_sqm_best"), errors="coerce") / pd.to_numeric(
        out.get("units_total_best"), errors="coerce"
    ).replace({0: np.nan})
    out["case_is_tall_scheme"] = (pd.to_numeric(out.get("max_storeys_best"), errors="coerce").fillna(0) >= 6).astype(float)
    out["case_is_medium_height_scheme"] = (pd.to_numeric(out.get("max_storeys_best"), errors="coerce").fillna(0) >= 4).astype(float)
    out["case_is_large_scheme"] = (pd.to_numeric(out.get("units_total_best"), errors="coerce").fillna(0) >= 100).astype(float)
    out["case_low_parking_ratio"] = (out["case_parking_per_unit"].fillna(99) < 0.75).astype(float)
    out["case_high_density_pressure"] = (out["case_units_density_per_ha"].fillna(0) >= 40).astype(float)
    out["case_flood_pressure"] = (
        (pd.to_numeric(out.get("coastal_hit_any"), errors="coerce").fillna(0) > 0)
        | (pd.to_numeric(out.get("fluvial_hit_any"), errors="coerce").fillna(0) > 0)
    ).astype(float)
    out["submission_text"] = out.apply(build_submission_text, axis=1)
    out["proposal_text"] = out["DevelopmentDescription"].fillna("").astype(str).map(normalize_ws)
    out["proposal_text_stripped"] = out["proposal_text"].map(strip_text_leakage_clues)
    out["site_group_key"] = out.apply(build_site_group_key, axis=1)
    desc_lower = out["proposal_text"].str.lower()
    out["dev_type_apartment"] = desc_lower.str.contains(r"\bapartments?\b", regex=True).astype(float)
    out["dev_type_houses"] = desc_lower.str.contains(r"\bhouses?\b|\bdwellings?\b", regex=True).astype(float)
    out["dev_type_mixed_use"] = (
        desc_lower.str.contains(r"\bmixed[- ]use\b", regex=True) | out.get("has_mixed_use_best", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    ).astype(float)
    out["dev_type_retention"] = desc_lower.str.contains(r"\bretention\b|\bretain\b", regex=True).astype(float)
    out["dev_type_demolition"] = desc_lower.str.contains(r"\bdemolition\b|\bdemolish\b", regex=True).astype(float)
    out["dev_type_outline"] = desc_lower.str.contains(r"\boutline permission\b|\boutline\b", regex=True).astype(float)
    out["dev_type_change_of_use"] = desc_lower.str.contains(r"\bchange of use\b|\bchange use\b", regex=True).astype(float)
    out["dev_type_protected_structure"] = desc_lower.str.contains(r"\bprotected structure\b|\bconservation\b", regex=True).astype(float)
    out["dev_type_student"] = desc_lower.str.contains(r"\bstudent accommodation\b|\bpbsa\b", regex=True).astype(float)
    out["dev_type_large_scheme"] = out["case_is_large_scheme"]
    return out


def add_authority_history_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in [
        "authority_history_refusal_rate_12m",
        "authority_history_refusal_rate_24m",
        "authority_history_case_count_12m",
        "authority_history_case_count_24m",
        "authority_history_refusal_rate_all_prior",
        "authority_history_case_count_all_prior",
    ]:
        out[col] = np.nan

    labeled = out[out["target_refused"].notna() & out["received_date_dt"].notna()].copy()
    labeled = labeled.sort_values(["PlanningAuthority", "received_date_dt", "case_key"])
    for authority, group in labeled.groupby("PlanningAuthority", sort=False):
        history = group.set_index("received_date_dt")["target_refused"].astype(float)
        rate_12m = history.rolling("365D", closed="left").mean()
        count_12m = history.rolling("365D", closed="left").count()
        rate_24m = history.rolling("730D", closed="left").mean()
        count_24m = history.rolling("730D", closed="left").count()
        all_count = history.expanding().count().shift(1)
        all_rate = history.expanding().mean().shift(1)
        out.loc[group.index, "authority_history_refusal_rate_12m"] = rate_12m.to_numpy()
        out.loc[group.index, "authority_history_refusal_rate_24m"] = rate_24m.to_numpy()
        out.loc[group.index, "authority_history_case_count_12m"] = count_12m.to_numpy()
        out.loc[group.index, "authority_history_case_count_24m"] = count_24m.to_numpy()
        out.loc[group.index, "authority_history_refusal_rate_all_prior"] = all_rate.to_numpy()
        out.loc[group.index, "authority_history_case_count_all_prior"] = all_count.to_numpy()

    out["authority_history_refusal_rate_12m"] = out["authority_history_refusal_rate_12m"].fillna(out["authority_history_refusal_rate_all_prior"])
    out["authority_history_refusal_rate_24m"] = out["authority_history_refusal_rate_24m"].fillna(out["authority_history_refusal_rate_all_prior"])
    out["authority_history_case_count_12m"] = out["authority_history_case_count_12m"].fillna(0)
    out["authority_history_case_count_24m"] = out["authority_history_case_count_24m"].fillna(0)
    out["authority_history_refusal_rate_all_prior"] = out["authority_history_refusal_rate_all_prior"].fillna(out["target_refused"].mean())
    out["authority_history_case_count_all_prior"] = out["authority_history_case_count_all_prior"].fillna(0)
    return out


def aggregate_plan_features(chunks: pd.DataFrame, tags: pd.DataFrame) -> pd.DataFrame:
    merged = chunks.merge(tags, on="chunk_id", how="left")
    rows = []
    for plan_key, group in merged.groupby("plan_key", dropna=False):
        row = {
            "plan_key": plan_key,
            "policy_plan_chunk_count": float(len(group)),
            "policy_plan_total_chars": float(pd.to_numeric(group["chunk_chars"], errors="coerce").fillna(0).sum()),
            "policy_plan_hard_constraint_share": float((group["constraint_strength"] == "hard").mean()),
        }
        themes = sorted({t for cell in tags.get("policy_theme_tags", pd.Series(dtype=str)).fillna("") for t in str(cell).split(";") if t})
        counts = {}
        for cell in group["policy_theme_tags"].fillna(""):
            for theme in str(cell).split(";"):
                if theme:
                    counts[theme] = counts.get(theme, 0) + 1
        for theme in themes:
            row[f"policy_plan_theme_count__{theme}"] = float(counts.get(theme, 0))
            row[f"policy_plan_theme_share__{theme}"] = float(counts.get(theme, 0) / max(1, len(group)))
        rows.append(row)
    return pd.DataFrame(rows)


def build_policy_match_features(cases: pd.DataFrame, chunks: pd.DataFrame, tags: pd.DataFrame, top_k: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    tagged = chunks.merge(tags[["chunk_id", "policy_theme_tags", "constraint_strength"]], on="chunk_id", how="left")
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=30000, min_df=1)
    chunk_text = tagged["chunk_text"].fillna("").astype(str)
    case_text = cases["submission_text"].fillna("").astype(str)
    chunk_matrix = vectorizer.fit_transform(chunk_text)
    case_matrix = vectorizer.transform(case_text)
    joblib.dump(vectorizer, MODEL_DIR / "submission_policy_tfidf_vectorizer.joblib")

    feature_rows = []
    match_rows = []
    for idx, row in cases.reset_index(drop=True).iterrows():
        plan_key = row.get("policy_plan_key", "")
        plan_idx = tagged.index[tagged["plan_key"].fillna("").astype(str) == str(plan_key)].to_numpy()
        base = {
            "case_key": row["case_key"],
            "policy_similarity_method": "tfidf",
            "policy_similarity_top_score": 0.0,
            "policy_similarity_mean_top5": 0.0,
            "policy_match_hard_share_top5": 0.0,
        }
        if len(plan_idx) == 0:
            feature_rows.append(base)
            continue
        scores = linear_kernel(case_matrix[idx], chunk_matrix[plan_idx]).ravel()
        order = np.argsort(-scores)[: min(top_k, len(scores))]
        chosen_idx = plan_idx[order]
        chosen = tagged.loc[chosen_idx].copy()
        chosen_scores = scores[order]
        base["policy_similarity_top_score"] = float(chosen_scores[0]) if len(chosen_scores) else 0.0
        base["policy_similarity_mean_top5"] = float(np.mean(chosen_scores)) if len(chosen_scores) else 0.0
        base["policy_match_hard_share_top5"] = float((chosen["constraint_strength"] == "hard").mean()) if len(chosen) else 0.0
        theme_counts: dict[str, int] = {}
        for cell in chosen["policy_theme_tags"].fillna(""):
            for theme in str(cell).split(";"):
                if theme:
                    theme_counts[theme] = theme_counts.get(theme, 0) + 1
        for theme, count in theme_counts.items():
            base[f"policy_match_theme_count__{theme}"] = float(count)
            base[f"policy_match_theme_share__{theme}"] = float(count / max(1, len(chosen)))
        for rank, (chunk_i, score) in enumerate(zip(chosen_idx, chosen_scores), start=1):
            chunk = tagged.loc[chunk_i]
            match_rows.append(
                {
                    "case_key": row["case_key"],
                    "rank": rank,
                    "score": float(score),
                    "chunk_id": chunk.get("chunk_id", ""),
                    "plan_key": chunk.get("plan_key", ""),
                    "section_heading": chunk.get("section_heading", ""),
                    "policy_theme_tags": chunk.get("policy_theme_tags", ""),
                }
            )
        feature_rows.append(base)
    features = pd.DataFrame(feature_rows).fillna(0)
    matches = pd.DataFrame(match_rows)
    return features, matches


def load_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    cases = pd.read_csv(INPUT_CASES, low_memory=False)
    cases = cases[cases["PlanningAuthority"].isin(DUBLIN_AUTHORITIES)].copy()
    cases["merge_key"] = [build_merge_key(a, b) for a, b in zip(cases["PlanningAuthority"], cases["ApplicationNumber"])]
    cases["case_key"] = cases.get("case_key", "").fillna("").astype(str).str.strip()
    invalid = cases["case_key"].str.lower().isin({"", "nan", "none", "null"})
    cases.loc[invalid, "case_key"] = cases.loc[invalid, "merge_key"]
    targets = cases["Decision"].map(decision_to_submission_target)
    cases["target_refused"] = [x[0] for x in targets]
    cases["target_mapping_status"] = [x[1] for x in targets]
    cases = cases.merge(load_flood_features(), on="merge_key", how="left")
    cases = add_submission_features(cases)
    manifest = pd.read_csv(POLICY_MANIFEST)
    chunks = pd.read_csv(POLICY_CHUNKS, low_memory=False)
    tags = pd.read_csv(POLICY_CLAUSE_TAGS, low_memory=False)
    cases = assign_policy_plan_by_received_date(cases, manifest)
    cases = cases.merge(aggregate_plan_features(chunks, tags), left_on="policy_plan_key", right_on="plan_key", how="left")
    match_features, matches = build_policy_match_features(cases, chunks, tags)
    cases = cases.merge(match_features, on="case_key", how="left")
    cases = add_authority_history_features(cases)
    return cases, matches


def leakage_guard(feature_columns: list[str]) -> None:
    offenders = []
    for col in feature_columns:
        if any(re.search(pattern, col, flags=re.IGNORECASE) for pattern in BANNED_FEATURE_PATTERNS):
            offenders.append(col)
    if offenders:
        raise ValueError(f"Leakage guard failed. Banned feature columns included: {offenders}")


def selected_feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str]]:
    policy_numeric = [
        c
        for c in df.columns
        if c.startswith(THEME_COLUMNS_PREFIXES)
        and c not in {"policy_similarity_method", "policy_plan_key"}
        and pd.api.types.is_numeric_dtype(df[c])
    ]
    numeric = [c for c in NUMERIC_COLUMNS + BINARY_COLUMNS + policy_numeric if c in df.columns]
    numeric = [c for c in numeric if pd.to_numeric(df[c], errors="coerce").notna().any()]
    categorical = [c for c in CATEGORICAL_COLUMNS if c in df.columns]
    text = ["submission_text"]
    features = numeric + categorical + text
    leakage_guard(features)
    baseline_numeric = [c for c in numeric if not c.startswith(THEME_COLUMNS_PREFIXES)]
    baseline_categorical = [c for c in categorical if not c.startswith("policy_")]
    return features, numeric, categorical, text, baseline_numeric, baseline_categorical


def split_time_based(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible = df[df["target_refused"].notna() & df["received_date_dt"].notna()].copy()
    eligible = eligible.sort_values("received_date_dt")
    split_idx = max(1, int(len(eligible) * 0.8))
    return eligible.iloc[:split_idx].copy(), eligible.iloc[split_idx:].copy()


def split_grouped_time_based(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible = df[df["target_refused"].notna() & df["received_date_dt"].notna()].copy()
    group_dates = (
        eligible.groupby("site_group_key", dropna=False)
        .agg(group_max_date=("received_date_dt", "max"), rows=("site_group_key", "size"))
        .sort_values("group_max_date")
        .reset_index()
    )
    target_train_rows = int(len(eligible) * 0.8)
    group_dates["cumulative_rows"] = group_dates["rows"].cumsum()
    train_groups = set(group_dates.loc[group_dates["cumulative_rows"] <= target_train_rows, "site_group_key"])
    if not train_groups:
        train_groups = {group_dates.iloc[0]["site_group_key"]}
    train = eligible[eligible["site_group_key"].isin(train_groups)].sort_values("received_date_dt").copy()
    test = eligible[~eligible["site_group_key"].isin(train_groups)].sort_values("received_date_dt").copy()
    return train, test


def build_logistic_pipeline(numeric: list[str], categorical: list[str]) -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), numeric),
            (
                "cat",
                Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]),
                categorical,
            ),
            ("txt", TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=50000, min_df=2), "submission_text"),
        ],
        sparse_threshold=1.0,
    )
    model = LogisticRegression(max_iter=3000, class_weight="balanced", C=0.5, solver="liblinear")
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def build_simple_pipeline(
    *,
    numeric: list[str] | None = None,
    categorical: list[str] | None = None,
    include_text: bool = False,
    text_column: str = "submission_text",
) -> Pipeline:
    numeric = numeric or []
    categorical = categorical or []
    transformers = []
    if numeric:
        transformers.append(("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), numeric))
    if categorical:
        transformers.append(
            (
                "cat",
                Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]),
                categorical,
            )
        )
    if include_text:
        transformers.append(
            (
                "txt",
                TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=50000, min_df=2),
                text_column,
            )
        )
    preprocessor = ColumnTransformer(transformers, sparse_threshold=1.0)
    model = LogisticRegression(max_iter=3000, class_weight="balanced", C=0.5, solver="liblinear")
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def safe_probability_array(proba: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.clip(np.asarray(proba, dtype=float), eps, 1.0 - eps)


def class_balance(y_true: pd.Series) -> dict[str, float | int]:
    y = y_true.to_numpy(dtype=int)
    refusals = int(y.sum())
    grants = int(len(y) - refusals)
    return {
        "n": int(len(y)),
        "grant_count": grants,
        "refusal_count": refusals,
        "grant_rate": float(grants / len(y)) if len(y) else np.nan,
        "refusal_rate": float(refusals / len(y)) if len(y) else np.nan,
    }


def calibration_intercept_slope(y_true: pd.Series, proba: np.ndarray) -> dict[str, float]:
    y = y_true.to_numpy(dtype=int)
    p = safe_probability_array(proba)
    logits = np.log(p / (1.0 - p)).reshape(-1, 1)
    try:
        model = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000)
    except Exception:
        model = LogisticRegression(C=1_000_000.0, solver="lbfgs", max_iter=1000)
    model.fit(logits, y)
    return {
        "calibration_intercept": float(model.intercept_[0]),
        "calibration_slope": float(model.coef_[0][0]),
    }


def threshold_metrics(y_true: pd.Series, proba: np.ndarray, threshold: float) -> dict[str, float | int]:
    y = y_true.to_numpy(dtype=int)
    pred = (np.asarray(proba, dtype=float) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    specificity = float(tn / (tn + fp)) if (tn + fp) else np.nan
    fpr = float(fp / (fp + tn)) if (fp + tn) else np.nan
    fnr = float(fn / (fn + tp)) if (fn + tp) else np.nan
    return {
        "threshold": float(threshold),
        "cases_flagged": int(pred.sum()),
        "share_flagged": float(pred.mean()) if len(pred) else np.nan,
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "refusal_precision": float(precision_score(y, pred, zero_division=0)),
        "refusal_recall": float(recall_score(y, pred, zero_division=0)),
        "specificity": specificity,
        "f1": float(f1_score(y, pred, zero_division=0)),
        "false_positive_rate": fpr,
        "false_negative_rate": fnr,
    }


def threshold_table(y_true: pd.Series, proba: np.ndarray, thresholds: list[float] | None = None) -> pd.DataFrame:
    chosen = thresholds or THRESHOLDS
    return pd.DataFrame([threshold_metrics(y_true, proba, threshold=t) for t in chosen])


def risk_bucket_table(y_true: pd.Series, proba: np.ndarray, buckets: int = 10) -> pd.DataFrame:
    df = pd.DataFrame({"target_refused": y_true.to_numpy(dtype=float), "probability": np.asarray(proba, dtype=float)})
    if df.empty:
        return pd.DataFrame(columns=["predicted_risk_group", "cases", "mean_predicted_risk", "actual_refusal_rate"])
    df = df.sort_values("probability").reset_index(drop=True)
    q = min(buckets, len(df))
    df["bucket_id"] = pd.qcut(df.index, q=q, labels=False, duplicates="drop")
    labels = [f"{i * 10}-{(i + 1) * 10}%" for i in range(int(df["bucket_id"].nunique()))]
    if labels:
        labels[0] = "Lowest 10%"
        labels[-1] = "Highest 10%"
    out = (
        df.groupby("bucket_id", observed=False)
        .agg(
            cases=("target_refused", "size"),
            mean_predicted_risk=("probability", "mean"),
            actual_refusal_rate=("target_refused", "mean"),
        )
        .reset_index()
    )
    out["predicted_risk_group"] = [labels[int(i)] for i in out["bucket_id"]]
    return out[["predicted_risk_group", "cases", "mean_predicted_risk", "actual_refusal_rate"]]


def compute_metrics(y_true: pd.Series, proba: np.ndarray) -> dict[str, float]:
    p = safe_probability_array(proba)
    out = {
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "pr_auc": float(average_precision_score(y_true, proba)),
        "average_precision": float(average_precision_score(y_true, proba)),
        "brier": float(brier_score_loss(y_true, proba)),
        "log_loss": float(log_loss(y_true, p)),
    }
    out.update(calibration_intercept_slope(y_true, p))
    return out


def bootstrap_metric_ci(y_true: pd.Series, proba: np.ndarray, n_boot: int = 500, seed: int = 42) -> dict[str, float | int]:
    y = y_true.to_numpy(dtype=int)
    p = np.asarray(proba, dtype=float)
    rng = np.random.default_rng(seed)
    aucs = []
    prs = []
    briers = []
    skipped = 0
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), size=len(y))
        if len(np.unique(y[idx])) < 2:
            skipped += 1
            continue
        aucs.append(roc_auc_score(y[idx], p[idx]))
        prs.append(average_precision_score(y[idx], p[idx]))
        briers.append(brier_score_loss(y[idx], p[idx]))
    if not aucs:
        return {"bootstrap_samples": 0, "skipped_single_class_samples": skipped}
    return {
        "bootstrap_samples": int(len(aucs)),
        "skipped_single_class_samples": int(skipped),
        "roc_auc_p05": float(np.quantile(aucs, 0.05)),
        "roc_auc_p50": float(np.quantile(aucs, 0.50)),
        "roc_auc_p95": float(np.quantile(aucs, 0.95)),
        "pr_auc_p05": float(np.quantile(prs, 0.05)),
        "pr_auc_p50": float(np.quantile(prs, 0.50)),
        "pr_auc_p95": float(np.quantile(prs, 0.95)),
        "brier_p05": float(np.quantile(briers, 0.05)),
        "brier_p50": float(np.quantile(briers, 0.50)),
        "brier_p95": float(np.quantile(briers, 0.95)),
    }


def calibration_table(y_true: pd.Series, proba: np.ndarray, bins: int = 10) -> pd.DataFrame:
    df = pd.DataFrame({"target_refused": y_true.to_numpy(dtype=float), "probability": proba})
    df["bucket"] = pd.cut(df["probability"], bins=np.linspace(0, 1, bins + 1), include_lowest=True)
    out = (
        df.groupby("bucket", observed=False)
        .agg(cases=("target_refused", "size"), mean_predicted_refusal_probability=("probability", "mean"), actual_refusal_rate=("target_refused", "mean"))
        .reset_index()
    )
    out["bucket"] = out["bucket"].astype(str)
    return out


def assemble_model_evaluation(y_true: pd.Series, proba: np.ndarray) -> dict[str, object]:
    return {
        "class_balance": class_balance(y_true),
        "ranking_probability_metrics": compute_metrics(y_true, proba),
        "bootstrap_ci": bootstrap_metric_ci(y_true, proba),
        "threshold_metrics": threshold_table(y_true, proba).to_dict(orient="records"),
        "risk_buckets": risk_bucket_table(y_true, proba).to_dict(orient="records"),
    }


def always_grant_baseline_metrics(y_true: pd.Series) -> dict[str, object]:
    proba = np.zeros(len(y_true), dtype=float)
    return assemble_model_evaluation(y_true, proba)


def per_authority_metrics(scored: pd.DataFrame, probability_col: str) -> dict[str, dict[str, float | int]]:
    out = {}
    for authority, group in scored.groupby("PlanningAuthority"):
        if group["target_refused"].nunique() < 2:
            out[authority] = {"rows": int(len(group)), "skipped": "only_one_class"}
            continue
        metrics = compute_metrics(group["target_refused"], group[probability_col].to_numpy())
        metrics.update(bootstrap_metric_ci(group["target_refused"], group[probability_col].to_numpy(), n_boot=500))
        metrics["rows"] = int(len(group))
        metrics["refusal_rate"] = float(group["target_refused"].mean())
        out[authority] = metrics
    return out


def run_decomposition_benchmarks(
    train: pd.DataFrame,
    test: pd.DataFrame,
    scored: pd.DataFrame,
    structured_numeric: list[str],
) -> tuple[pd.DataFrame, dict[str, object]]:
    specs = {
        "authority_only": {
            "numeric": [],
            "categorical": ["PlanningAuthority"],
            "text": False,
        },
        "authority_year": {
            "numeric": ["received_year"],
            "categorical": ["PlanningAuthority"],
            "text": False,
        },
        "structured_no_text": {
            "numeric": structured_numeric,
            "categorical": ["PlanningAuthority", "ApplicationType", "LandUseCode", "OneOffHouse"],
            "text": False,
        },
        "description_text_only": {
            "numeric": [],
            "categorical": [],
            "text": True,
            "text_column": "proposal_text",
        },
        "description_text_stripped": {
            "numeric": [],
            "categorical": [],
            "text": True,
            "text_column": "proposal_text_stripped",
        },
        "authority_year_devtype": {
            "numeric": ["received_year", *DEVELOPMENT_TYPE_COLUMNS],
            "categorical": ["PlanningAuthority"],
            "text": False,
        },
        "authority_year_devtype_text": {
            "numeric": ["received_year", *DEVELOPMENT_TYPE_COLUMNS],
            "categorical": ["PlanningAuthority"],
            "text": True,
            "text_column": "proposal_text_stripped",
        },
        "authority_history": {
            "numeric": [
                "authority_history_refusal_rate_12m",
                "authority_history_refusal_rate_24m",
                "authority_history_case_count_12m",
                "authority_history_case_count_24m",
                "authority_history_refusal_rate_all_prior",
                "authority_history_case_count_all_prior",
            ],
            "categorical": ["PlanningAuthority"],
            "text": False,
        },
        "authority_history_devtype": {
            "numeric": [
                "authority_history_refusal_rate_12m",
                "authority_history_refusal_rate_24m",
                "authority_history_case_count_12m",
                "authority_history_case_count_24m",
                "authority_history_refusal_rate_all_prior",
                "authority_history_case_count_all_prior",
                *DEVELOPMENT_TYPE_COLUMNS,
            ],
            "categorical": ["PlanningAuthority"],
            "text": False,
        },
        "authority_history_devtype_text": {
            "numeric": [
                "authority_history_refusal_rate_12m",
                "authority_history_refusal_rate_24m",
                "authority_history_case_count_12m",
                "authority_history_case_count_24m",
                "authority_history_refusal_rate_all_prior",
                "authority_history_case_count_all_prior",
                *DEVELOPMENT_TYPE_COLUMNS,
            ],
            "categorical": ["PlanningAuthority"],
            "text": True,
            "text_column": "proposal_text_stripped",
        },
    }
    results: dict[str, object] = {}
    out = scored.copy()
    for name, spec in specs.items():
        numeric = [c for c in spec["numeric"] if c in train.columns]
        categorical = [c for c in spec["categorical"] if c in train.columns]
        include_text = bool(spec["text"])
        text_column = str(spec.get("text_column", "submission_text"))
        feature_columns = numeric + categorical + ([text_column] if include_text else [])
        leakage_guard(feature_columns)
        model = build_simple_pipeline(numeric=numeric, categorical=categorical, include_text=include_text, text_column=text_column)
        model.fit(train[feature_columns], train["target_refused"])
        probability_col = f"{name}_refusal_score"
        out[probability_col] = model.predict_proba(out[feature_columns])[:, 1]
        holdout = out[out["split"] == "holdout"]
        results[name] = {
            "features": feature_columns,
            "holdout": compute_metrics(holdout["target_refused"], holdout[probability_col].to_numpy()),
            "holdout_by_authority": per_authority_metrics(holdout, probability_col),
        }
        joblib.dump(model, MODEL_DIR / f"dublin_submission_{name}.joblib")
        if include_text:
            write_text_coefficients(model, name)
    return out, results


def write_text_coefficients(model: Pipeline, benchmark_name: str, n: int = 75) -> None:
    preprocessor = model.named_steps["preprocessor"]
    classifier = model.named_steps["model"]
    names = preprocessor.get_feature_names_out()
    coefs = classifier.coef_[0]
    rows = []
    for idx in np.argsort(coefs)[-n:][::-1]:
        rows.append({"direction": "refusal_positive", "feature": names[idx], "coefficient": float(coefs[idx])})
    for idx in np.argsort(coefs)[:n]:
        rows.append({"direction": "grant_positive", "feature": names[idx], "coefficient": float(coefs[idx])})
    pd.DataFrame(rows).to_csv(CURRENT_DIR / f"dublin_submission_tfidf_coefficients_{benchmark_name}.csv", index=False)


def write_authority_comparison(metrics: dict[str, object]) -> None:
    rows = []
    decomp = metrics.get("decomposition_benchmarks", {})
    authorities = sorted(
        {
            authority
            for payload in decomp.values()
            for authority in payload.get("holdout_by_authority", {}).keys()
        }
    )
    for authority in authorities:
        row = {"authority": authority}
        for model_name in ["authority_year", "description_text_only", "description_text_stripped", "structured_no_text", "baseline_logistic", "policy_logistic"]:
            if model_name in decomp:
                payload = decomp[model_name]["holdout_by_authority"].get(authority, {})
            else:
                payload = metrics.get(f"{model_name}_holdout_by_authority", {}).get(authority, {})
            row["holdout_n"] = payload.get("rows", row.get("holdout_n"))
            row["refusal_rate"] = payload.get("refusal_rate", row.get("refusal_rate"))
            row[f"{model_name}_auc"] = payload.get("roc_auc")
            row[f"{model_name}_pr_auc"] = payload.get("pr_auc")
            row[f"{model_name}_brier"] = payload.get("brier")
        rows.append(row)
    pd.DataFrame(rows).to_csv(CURRENT_DIR / "dublin_submission_authority_benchmark_summary.csv", index=False)


def related_application_split_diagnostics(scored: pd.DataFrame) -> dict[str, object]:
    groups = []
    for key, group in scored.groupby("site_group_key", dropna=False):
        splits = set(group["split"].dropna().astype(str))
        if len(splits) <= 1:
            continue
        descriptions = group["proposal_text"].fillna("").astype(str).map(compact_text_key).value_counts().head(3)
        groups.append(
            {
                "site_group_key": key,
                "rows": int(len(group)),
                "train_rows": int((group["split"] == "train").sum()),
                "holdout_rows": int((group["split"] == "holdout").sum()),
                "authorities": ";".join(sorted(group["PlanningAuthority"].dropna().astype(str).unique())),
                "application_numbers": ";".join(group["ApplicationNumber"].dropna().astype(str).head(8)),
                "description_keys": " | ".join(descriptions.index.tolist()),
            }
        )
    out = pd.DataFrame(groups)
    if not out.empty:
        out = out.sort_values(["rows", "holdout_rows"], ascending=[False, False])
    out.to_csv(CURRENT_DIR / "dublin_submission_related_group_split_diagnostics.csv", index=False)
    return {
        "site_groups_total": int(scored["site_group_key"].nunique(dropna=False)),
        "site_groups_crossing_train_holdout": int(len(out)),
        "rows_in_crossing_site_groups": int(out["rows"].sum()) if not out.empty else 0,
        "diagnostic_path": str(CURRENT_DIR / "dublin_submission_related_group_split_diagnostics.csv"),
    }


def run_grouped_text_benchmarks(dataset: pd.DataFrame) -> dict[str, object]:
    train, test = split_grouped_time_based(dataset)
    results = {
        "train_rows": int(len(train)),
        "holdout_rows": int(len(test)),
        "train_site_groups": int(train["site_group_key"].nunique(dropna=False)),
        "holdout_site_groups": int(test["site_group_key"].nunique(dropna=False)),
        "holdout_start_received_date": str(test["received_date_dt"].min()),
        "holdout_end_received_date": str(test["received_date_dt"].max()),
        "models": {},
    }
    summary_rows = []
    for name, text_col in [
        ("grouped_description_text_only", "proposal_text"),
        ("grouped_description_text_stripped", "proposal_text_stripped"),
    ]:
        feature_columns = [text_col]
        model = build_simple_pipeline(include_text=True, text_column=text_col)
        model.fit(train[feature_columns], train["target_refused"])
        proba = model.predict_proba(test[feature_columns])[:, 1]
        scored = test[["PlanningAuthority", "target_refused"]].copy()
        scored[f"{name}_score"] = proba
        model_metrics = {
            "features": feature_columns,
            "holdout": compute_metrics(test["target_refused"], proba),
            "holdout_by_authority": per_authority_metrics(scored, f"{name}_score"),
        }
        results["models"][name] = model_metrics
        row = {"model": name, **model_metrics["holdout"]}
        summary_rows.append(row)
        for authority, payload in model_metrics["holdout_by_authority"].items():
            authority_row = {"model": name, "authority": authority, **payload}
            summary_rows.append(authority_row)
        joblib.dump(model, MODEL_DIR / f"dublin_submission_{name}.joblib")
    pd.DataFrame(summary_rows).to_csv(CURRENT_DIR / "dublin_submission_grouped_text_benchmark_summary.csv", index=False)
    return results


def run_rolling_temporal_validation(dataset: pd.DataFrame) -> dict[str, object]:
    eligible = dataset[dataset["target_refused"].notna() & dataset["received_date_dt"].notna()].copy()
    windows = [
        ("2020_2021", "2020-01-01", "2022-01-01"),
        ("2021_2022", "2021-01-01", "2023-01-01"),
        ("2022_2023", "2022-01-01", "2024-01-01"),
        ("2023_2024", "2023-01-01", "2025-01-01"),
        ("2024_2026", "2024-01-01", "2027-01-01"),
    ]
    rows = []
    for label, start, end in windows:
        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC")
        train = eligible[eligible["received_date_dt"] < start_ts].copy()
        test = eligible[(eligible["received_date_dt"] >= start_ts) & (eligible["received_date_dt"] < end_ts)].copy()
        if len(train) < 100 or len(test) < 20 or train["target_refused"].nunique() < 2 or test["target_refused"].nunique() < 2:
            rows.append({"test_period": label, "status": "skipped", "train_rows": len(train), "holdout_rows": len(test)})
            continue
        specs = {
            "authority_history": (
                [
                    "authority_history_refusal_rate_12m",
                    "authority_history_refusal_rate_24m",
                    "authority_history_case_count_12m",
                    "authority_history_case_count_24m",
                    "authority_history_refusal_rate_all_prior",
                    "authority_history_case_count_all_prior",
                ],
                ["PlanningAuthority"],
                False,
                "proposal_text_stripped",
            ),
            "description_text_stripped": ([], [], True, "proposal_text_stripped"),
        }
        for model_name, (numeric, categorical, include_text, text_col) in specs.items():
            feature_columns = numeric + categorical + ([text_col] if include_text else [])
            model = build_simple_pipeline(numeric=numeric, categorical=categorical, include_text=include_text, text_column=text_col)
            model.fit(train[feature_columns], train["target_refused"])
            proba = model.predict_proba(test[feature_columns])[:, 1]
            metrics = compute_metrics(test["target_refused"], proba)
            rows.append(
                {
                    "test_period": label,
                    "model": model_name,
                    "status": "fit",
                    "train_rows": int(len(train)),
                    "holdout_rows": int(len(test)),
                    "refusal_rate": float(test["target_refused"].mean()),
                    **metrics,
                }
            )
            scored = test[["PlanningAuthority", "target_refused"]].copy()
            scored["score"] = proba
            for authority, payload in per_authority_metrics(scored, "score").items():
                rows.append(
                    {
                        "test_period": label,
                        "model": model_name,
                        "authority": authority,
                        "status": "fit",
                        **payload,
                    }
                )
    out = pd.DataFrame(rows)
    out.to_csv(CURRENT_DIR / "dublin_submission_rolling_temporal_validation.csv", index=False)
    return {
        "windows": windows,
        "path": str(CURRENT_DIR / "dublin_submission_rolling_temporal_validation.csv"),
    }


def train_optional_boosters(train: pd.DataFrame, test: pd.DataFrame, feature_columns: list[str], numeric: list[str], categorical: list[str]) -> tuple[pd.DataFrame, dict[str, object]]:
    results: dict[str, object] = {}
    scored = pd.DataFrame(index=test.index)
    for name, import_name, class_name in [
        ("xgboost", "xgboost", "XGBClassifier"),
        ("lightgbm", "lightgbm", "LGBMClassifier"),
    ]:
        try:
            module = __import__(import_name)
            cls = getattr(module, class_name)
        except Exception as exc:
            results[name] = {"status": "skipped", "reason": f"{import_name} not installed: {exc}"}
            continue
        preprocessor = ColumnTransformer(
            [
                ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), numeric),
                (
                    "cat",
                    Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]),
                    categorical,
                ),
                ("txt", TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=30000, min_df=2), "submission_text"),
            ],
            sparse_threshold=1.0,
        )
        if name == "xgboost":
            model = cls(
                n_estimators=300,
                max_depth=3,
                learning_rate=0.03,
                subsample=0.85,
                colsample_bytree=0.85,
                eval_metric="logloss",
                random_state=42,
            )
        else:
            model = cls(
                n_estimators=400,
                learning_rate=0.03,
                num_leaves=15,
                subsample=0.85,
                colsample_bytree=0.85,
                random_state=42,
            )
        pipe = Pipeline([("preprocessor", preprocessor), ("model", model)])
        pipe.fit(train[feature_columns], train["target_refused"])
        proba = pipe.predict_proba(test[feature_columns])[:, 1]
        scored[f"{name}_refusal_probability"] = proba
        results[name] = {"status": "fit", **compute_metrics(test["target_refused"], proba)}
        joblib.dump(pipe, MODEL_DIR / f"dublin_submission_{name}.joblib")
    return scored, results


def write_benchmark_summary(metrics: dict[str, object]) -> None:
    rows = []
    for name in ["baseline_logistic", "policy_logistic"]:
        key = f"{name}_holdout"
        if key in metrics:
            row = {"model": name, **metrics[key]}
            rows.append(row)
    for name, payload in metrics.get("decomposition_benchmarks", {}).items():
        row = {"model": name, **payload["holdout"]}
        rows.append(row)
    for name, payload in metrics.get("optional_boosters", {}).items():
        if payload.get("status") == "fit":
            rows.append({"model": name, **payload})
        else:
            rows.append({"model": name, "status": payload.get("status"), "reason": payload.get("reason")})
    pd.DataFrame(rows).to_csv(CURRENT_DIR / "dublin_submission_benchmark_summary.csv", index=False)


def write_holdout_evaluation_artifacts(evaluations: dict[str, dict[str, object]]) -> None:
    metric_rows = []
    threshold_rows = []
    bucket_rows = []
    calibration_rows = []
    for model_name, payload in evaluations.items():
        metric_rows.append(
            {
                "model": model_name,
                **payload["class_balance"],
                **payload["ranking_probability_metrics"],
                **payload["bootstrap_ci"],
            }
        )
        threshold_rows.extend([{"model": model_name, **row} for row in payload["threshold_metrics"]])
        bucket_rows.extend([{"model": model_name, **row} for row in payload["risk_buckets"]])
        calibration_rows.append(
            {
                "model": model_name,
                "calibration_intercept": payload["ranking_probability_metrics"].get("calibration_intercept"),
                "calibration_slope": payload["ranking_probability_metrics"].get("calibration_slope"),
            }
        )
    pd.DataFrame(metric_rows).to_csv(CURRENT_DIR / "dublin_submission_holdout_model_metrics.csv", index=False)
    pd.DataFrame(threshold_rows).to_csv(CURRENT_DIR / "dublin_submission_threshold_metrics.csv", index=False)
    pd.DataFrame(bucket_rows).to_csv(CURRENT_DIR / "dublin_submission_risk_buckets.csv", index=False)
    pd.DataFrame(calibration_rows).to_csv(CURRENT_DIR / "dublin_submission_calibration_summary.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build leakage-safe Dublin submission-time refusal model.")
    parser.add_argument("--skip-optional-boosters", action="store_true", help="Only run logistic regression.")
    args = parser.parse_args()

    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    dataset, matches = load_dataset()
    feature_columns, numeric, categorical, text, baseline_numeric, baseline_categorical = selected_feature_columns(dataset)
    baseline_feature_columns = baseline_numeric + baseline_categorical + text
    dataset.to_csv(CURRENT_DIR / "dublin_submission_model_dataset.csv", index=False)
    matches.to_csv(CURRENT_DIR / "dublin_submission_policy_matches.csv", index=False)
    (
        dataset.groupby(["Decision", "target_mapping_status", "target_refused"], dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values(["target_mapping_status", "Decision"], na_position="last")
        .to_csv(CURRENT_DIR / "dublin_submission_target_mapping_audit.csv", index=False)
    )

    train, test = split_time_based(dataset)
    if train.empty or test.empty or test["target_refused"].nunique() < 2:
        raise ValueError("Time split did not produce a usable labelled holdout.")

    baseline_logistic = build_logistic_pipeline(baseline_numeric, baseline_categorical)
    policy_logistic = build_logistic_pipeline(numeric, categorical)
    baseline_logistic.fit(train[baseline_feature_columns], train["target_refused"])
    policy_logistic.fit(train[feature_columns], train["target_refused"])
    joblib.dump(baseline_logistic, MODEL_DIR / "dublin_submission_baseline_logistic.joblib")
    joblib.dump(policy_logistic, MODEL_DIR / "dublin_submission_policy_logistic.joblib")

    scored = dataset[dataset["target_refused"].notna() & dataset["received_date_dt"].notna()].copy()
    scored["split"] = np.where(scored.index.isin(test.index), "holdout", "train")
    scored["baseline_logistic_refusal_probability"] = baseline_logistic.predict_proba(scored[baseline_feature_columns])[:, 1]
    scored["policy_logistic_refusal_probability"] = policy_logistic.predict_proba(scored[feature_columns])[:, 1]
    scored, decomposition_results = run_decomposition_benchmarks(
        train=train,
        test=test,
        scored=scored,
        structured_numeric=baseline_numeric,
    )

    optional_results: dict[str, object] = {}
    if not args.skip_optional_boosters:
        optional_scored, optional_results = train_optional_boosters(train, test, feature_columns, numeric, categorical)
        for col in optional_scored.columns:
            scored.loc[optional_scored.index, col] = optional_scored[col]

    holdout = scored[scored["split"] == "holdout"].copy()
    holdout_model_columns = {
        "baseline_logistic": "baseline_logistic_refusal_probability",
        "policy_logistic": "policy_logistic_refusal_probability",
        "authority_only": "authority_only_refusal_score",
        "authority_year": "authority_year_refusal_score",
        "authority_year_devtype": "authority_year_devtype_refusal_score",
        "authority_year_devtype_text": "authority_year_devtype_text_refusal_score",
        "description_text_only": "description_text_only_refusal_score",
        "description_text_stripped": "description_text_stripped_refusal_score",
        "structured_no_text": "structured_no_text_refusal_score",
        "authority_history": "authority_history_refusal_score",
        "authority_history_devtype": "authority_history_devtype_refusal_score",
        "authority_history_devtype_text": "authority_history_devtype_text_refusal_score",
    }
    for booster_name, booster_payload in optional_results.items():
        if booster_payload.get("status") == "fit":
            holdout_model_columns[booster_name] = f"{booster_name}_refusal_probability"

    holdout_evaluations = {
        model_name: assemble_model_evaluation(holdout["target_refused"], holdout[col].to_numpy())
        for model_name, col in holdout_model_columns.items()
        if col in holdout.columns
    }
    holdout_evaluations["always_grant_baseline"] = always_grant_baseline_metrics(holdout["target_refused"])

    metrics = {
        "prediction_time": "immediately_before_submission",
        "target": "final local-authority refusal vs grant/approval for original permission decisions",
        "train_rows": int(len(train)),
        "holdout_rows": int(len(test)),
        "holdout_class_balance": class_balance(holdout["target_refused"]),
        "train_start_received_date": str(train["received_date_dt"].min()),
        "train_end_received_date": str(train["received_date_dt"].max()),
        "holdout_start_received_date": str(test["received_date_dt"].min()),
        "holdout_end_received_date": str(test["received_date_dt"].max()),
        "label_mapping_status_counts": dataset["target_mapping_status"].value_counts(dropna=False).to_dict(),
        "features": {
            "baseline_numeric": baseline_numeric,
            "baseline_categorical": baseline_categorical,
            "policy_numeric": numeric,
            "policy_categorical": categorical,
            "text": text,
            "banned_patterns": BANNED_FEATURE_PATTERNS,
        },
        "baseline_logistic_holdout": compute_metrics(
            holdout["target_refused"],
            holdout["baseline_logistic_refusal_probability"].to_numpy(),
        ),
        "baseline_logistic_holdout_by_authority": per_authority_metrics(
            holdout,
            "baseline_logistic_refusal_probability",
        ),
        "policy_logistic_holdout": compute_metrics(
            holdout["target_refused"],
            holdout["policy_logistic_refusal_probability"].to_numpy(),
        ),
        "policy_logistic_holdout_by_authority": per_authority_metrics(holdout, "policy_logistic_refusal_probability"),
        "holdout_model_evaluations": holdout_evaluations,
        "baseline_comparisons": {
            "always_grant_baseline": holdout_evaluations["always_grant_baseline"],
            "authority_year_devtype_baseline": holdout_evaluations.get("authority_year_devtype"),
            "primary_submission_model": PRIMARY_EVAL_MODEL,
            "primary_submission_model_evaluation": holdout_evaluations.get(PRIMARY_EVAL_MODEL),
        },
        "decomposition_benchmarks": decomposition_results,
        "related_application_split_diagnostics": related_application_split_diagnostics(scored),
        "grouped_site_text_benchmarks": run_grouped_text_benchmarks(dataset),
        "rolling_temporal_validation": run_rolling_temporal_validation(dataset),
        "optional_boosters": optional_results,
    }
    for model_name, col in holdout_model_columns.items():
        if col not in holdout.columns:
            continue
        calibration_table(
            holdout["target_refused"],
            holdout[col].to_numpy(),
        ).to_csv(CURRENT_DIR / f"dublin_submission_calibration_{model_name}.csv", index=False)
    scored.to_csv(CURRENT_DIR / "dublin_submission_predictions.csv", index=False)
    (CURRENT_DIR / "dublin_submission_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_benchmark_summary(metrics)
    write_authority_comparison(metrics)
    write_holdout_evaluation_artifacts(holdout_evaluations)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
