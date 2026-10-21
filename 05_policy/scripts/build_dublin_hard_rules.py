#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = ROOT / "05_policy"
CURRENT_DIR = POLICY_ROOT / "current"


def load_policy_module():
    path = POLICY_ROOT / "scripts" / "build_dublin_policy_pipeline.py"
    spec = importlib.util.spec_from_file_location("policy_pipeline", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


BEDROOM_LABEL_MAP = {
    "studio": "studio",
    "1-bed": "1-bed",
    "one bedroom": "1-bed",
    "1 bed": "1-bed",
    "1 bedroom": "1-bed",
    "2-bed": "2-bed",
    "two bedroom": "2-bed",
    "2 bed": "2-bed",
    "2 bedroom": "2-bed",
    "3-bed": "3-bed",
    "three bedroom": "3-bed",
    "3 bed": "3-bed",
    "3 bedroom": "3-bed",
    "4-bed": "4-bed",
    "four bedroom": "4-bed",
    "4 bed": "4-bed",
    "4 bedroom": "4-bed",
}

APARTMENT_PLAUSIBLE_MIN = {
    "studio": 25.0,
    "1-bed": 35.0,
    "2-bed": 45.0,
    "3-bed": 55.0,
    "4-bed": 70.0,
}

APARTMENT_PLAUSIBLE_MAX = {
    "studio": 60.0,
    "1-bed": 90.0,
    "2-bed": 140.0,
    "3-bed": 180.0,
    "4-bed": 240.0,
}


def normalize_bedroom_label(label: str) -> str:
    cleaned = normalize_text(label).lower().replace("-", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return BEDROOM_LABEL_MAP.get(cleaned, cleaned.replace(" ", ""))


def extract_apartment_size_rules(chunks: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    patterns = [
        re.compile(r"\b(studio|1[- ]?bed|one bedroom|2[- ]?bed|two bedroom|3[- ]?bed|three bedroom|4[- ]?bed|four bedroom)\b[^0-9]{0,40}(\d+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m2)", re.I),
    ]
    for _, row in chunks.iterrows():
        text = str(row["chunk_text"])
        lowered = text.lower()
        if "minimum bedroom floor areas" in lowered or "aggregate bedroom floor areas" in lowered:
            continue
        if not re.search(r"\bapartment|duplex|maisonette|minimum floor area|minimum dwelling|apartment floor area\b", text, flags=re.I):
            continue
        found = []
        for pat in patterns:
            for match in pat.finditer(text):
                a, b = match.group(1), match.group(2)
                if re.match(r"^\d", a) and not re.search(r"bed|studio|bedroom", a, flags=re.I):
                    size = float(a)
                    label = b.lower()
                else:
                    label = a.lower()
                    size = float(b)
                label = normalize_bedroom_label(label)
                found.append((label, size))
        dedup = {}
        for label, size in found:
            if label not in dedup or size < dedup[label]:
                dedup[label] = size
        for label, size in dedup.items():
            if label not in APARTMENT_PLAUSIBLE_MIN:
                continue
            if size < APARTMENT_PLAUSIBLE_MIN[label] or size > APARTMENT_PLAUSIBLE_MAX[label]:
                continue
            rows.append(
                {
                    "plan_key": row["plan_key"],
                    "authority": row["authority"],
                    "plan_start_year": row["plan_start_year"],
                    "plan_end_year": row["plan_end_year"],
                    "rule_family": "apartment_min_floor_area",
                    "subject_type": label,
                    "threshold_kind": "min",
                    "threshold_value": size,
                    "threshold_unit": "sqm",
                    "scope_note": "apartment_or_duplex",
                    "source_chunk_id": row["chunk_id"],
                    "source_document_label": row["document_label"],
                    "source_section_title": row["section_title"],
                    "source_page_range": row["page_range"],
                    "source_excerpt": normalize_text(text)[:800],
                    "confidence": "medium",
                }
            )
    return rows


def choose_canonical_rule(group: pd.DataFrame) -> pd.Series:
    counts = Counter(group["threshold_value"].tolist())
    best_value = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    canonical = group[group["threshold_value"] == best_value].copy()
    canonical = canonical.sort_values(["source_page_range", "source_chunk_id"]).iloc[0].copy()
    canonical["canonical_threshold_value"] = best_value
    canonical["candidate_threshold_values"] = ";".join(str(v) for v in sorted(counts))
    canonical["candidate_value_counts"] = json.dumps({str(k): v for k, v in sorted(counts.items())})
    canonical["source_rule_count"] = int(len(group))
    canonical["source_chunk_count"] = int(group["source_chunk_id"].nunique())
    return canonical


def canonicalize_registry(registry: pd.DataFrame) -> pd.DataFrame:
    if registry.empty:
        return registry.copy()
    group_cols = ["plan_key", "authority", "plan_start_year", "plan_end_year", "rule_family", "subject_type", "threshold_kind", "threshold_unit", "scope_note"]
    canonical_rows = []
    for _, group in registry.groupby(group_cols, dropna=False):
        canonical_rows.append(choose_canonical_rule(group))
    canonical = pd.DataFrame(canonical_rows).reset_index(drop=True)
    canonical = canonical.sort_values(["authority", "plan_start_year", "rule_family", "subject_type"]).reset_index(drop=True)
    canonical.to_csv(CURRENT_DIR / "hard_policy_rules_registry.csv", index=False)
    apartment_only = canonical[canonical["rule_family"] == "apartment_min_floor_area"].copy()
    apartment_only.to_csv(CURRENT_DIR / "hard_policy_apartment_standards.csv", index=False)
    return canonical


def extract_communal_amenity_rules(chunks: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    pattern = re.compile(r"(studio|one bedroom|two bedroom|three bedroom|1[- ]?bed|2[- ]?bed|3[- ]?bed)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m2)", re.I)
    for _, row in chunks.iterrows():
        text = str(row["chunk_text"])
        if not re.search(r"communal amenity", text, flags=re.I):
            continue
        found = {}
        for label, value in pattern.findall(text):
            label = normalize_bedroom_label(label)
            found[label] = float(value)
        for label, value in found.items():
            rows.append(
                {
                    "plan_key": row["plan_key"],
                    "authority": row["authority"],
                    "plan_start_year": row["plan_start_year"],
                    "plan_end_year": row["plan_end_year"],
                    "rule_family": "communal_amenity_min_per_unit",
                    "subject_type": label,
                    "threshold_kind": "min",
                    "threshold_value": value,
                    "threshold_unit": "sqm_per_unit",
                    "scope_note": "communal_amenity",
                    "source_chunk_id": row["chunk_id"],
                    "source_document_label": row["document_label"],
                    "source_section_title": row["section_title"],
                    "source_page_range": row["page_range"],
                    "source_excerpt": normalize_text(text)[:800],
                    "confidence": "medium",
                }
            )
    return rows


def extract_simple_scalar_rules(chunks: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    specs = [
        {
            "rule_family": "private_amenity_min_depth",
            "pattern": re.compile(r"minimum depth[^0-9]{0,30}(\d+(?:\.\d+)?)\s*m", re.I),
            "unit": "m",
            "scope": "balcony_or_patio",
        },
        {
            "rule_family": "disabled_parking_min_ratio",
            "pattern": re.compile(r"at least\s*(\d+(?:\.\d+)?)\s*%\s+of the total number of spaces", re.I),
            "unit": "percent",
            "scope": "disabled_car_parking",
        },
        {
            "rule_family": "units_per_core_max",
            "pattern": re.compile(r"maximum of\s*(\d+(?:\.\d+)?)\s*units per core per floor", re.I),
            "unit": "units_per_core_per_floor",
            "scope": "apartment_block",
        },
    ]
    for _, row in chunks.iterrows():
        text = str(row["chunk_text"])
        for spec in specs:
            match = spec["pattern"].search(text)
            if not match:
                continue
            value = float(match.group(1))
            rows.append(
                {
                    "plan_key": row["plan_key"],
                    "authority": row["authority"],
                    "plan_start_year": row["plan_start_year"],
                    "plan_end_year": row["plan_end_year"],
                    "rule_family": spec["rule_family"],
                    "subject_type": "",
                    "threshold_kind": "min" if "min" in spec["rule_family"] else "max",
                    "threshold_value": value,
                    "threshold_unit": spec["unit"],
                    "scope_note": spec["scope"],
                    "source_chunk_id": row["chunk_id"],
                    "source_document_label": row["document_label"],
                    "source_section_title": row["section_title"],
                    "source_page_range": row["page_range"],
                    "source_excerpt": normalize_text(text)[:800],
                    "confidence": "high",
                }
            )
    return rows


def build_hard_rules_registry(chunks: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rows.extend(extract_apartment_size_rules(chunks))
    rows.extend(extract_communal_amenity_rules(chunks))
    rows.extend(extract_simple_scalar_rules(chunks))
    registry = pd.DataFrame(rows).drop_duplicates(
        subset=["plan_key", "rule_family", "subject_type", "threshold_value", "threshold_unit", "source_chunk_id"]
    )
    registry = registry.sort_values(["authority", "plan_start_year", "rule_family", "subject_type", "threshold_value"]).reset_index(drop=True)
    return canonicalize_registry(registry)


def parse_case_apartment_sizes(description: str) -> dict[str, float]:
    text = normalize_text(description)
    sizes: dict[str, float] = {}
    segments = [normalize_text(seg) for seg in re.split(r"[;:]\s+|\.\s+|\)\s+and\s+|\)\s*,\s*", text) if normalize_text(seg)]
    patterns = [
        re.compile(r"(?P<beds>studio|1[- ]?bed|one bedroom|1 bedroom|2[- ]?bed|two bedroom|2 bedroom|3[- ]?bed|three bedroom|3 bedroom|4[- ]?bed|four bedroom|4 bedroom)[^.;]{0,45}?(?P<size>\d+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m2)", re.I),
    ]
    if not re.search(r"\bapartment|apartments|duplex|duplexes|maisonette|maisonettes|penthouse|penthouses|unit|units\b", text, flags=re.I):
        return sizes
    for segment in segments:
        if not re.search(r"\bapartment|apartments|duplex|duplexes|maisonette|maisonettes|penthouse|penthouses|unit|units\b", segment, flags=re.I):
            continue
        for pat in patterns:
            for match in pat.finditer(segment):
                label = normalize_bedroom_label(match.group("beds"))
                size = float(match.group("size"))
                if label not in APARTMENT_PLAUSIBLE_MIN:
                    continue
                if size < APARTMENT_PLAUSIBLE_MIN[label] or size > APARTMENT_PLAUSIBLE_MAX[label]:
                    continue
                prefix_context = normalize_text(segment[max(0, match.start("beds") - 80): match.start("beds")])
                prefix_labels = re.findall(r"\b(?:studio|[1-4][ -]?bed|one bedroom|two bedroom|three bedroom|four bedroom|[1-4] bedroom)\b", prefix_context, flags=re.I)
                if prefix_labels and re.search(r"(?:,|\band\b)", prefix_context, flags=re.I):
                    continue
                local_context = normalize_text(segment[max(0, match.start("beds") - 60): match.end("size")])
                if re.search(r"\b[1-4]\s+and\s+[1-4]\s+bed\b", local_context, flags=re.I):
                    continue
                if re.search(r"\b[1-4]\s*,\s*[1-4](?:\s*,\s*[1-4])*\s*,?\s*bed\b", local_context, flags=re.I):
                    continue
                other_labels = re.findall(r"\b(?:studio|[1-4][ -]?bed|one bedroom|two bedroom|three bedroom|four bedroom|[1-4] bedroom)\b", local_context, flags=re.I)
                normalized_labels = {normalize_bedroom_label(item) for item in other_labels}
                if len(normalized_labels) > 1:
                    continue
                sizes[label] = min(size, sizes.get(label, size))
    return sizes


def build_case_hard_rule_features(policy_module, registry: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    manifest_df = pd.read_csv(POLICY_ROOT / "source_data" / "dublin_policy_manifest.csv")
    cases = policy_module.load_dublin_cases()
    cases = cases.merge(policy_module.load_flood_features(), on="merge_key", how="left")
    cases = cases.merge(policy_module.load_refusal_case_tags(), on="case_key", how="left", suffixes=("", "_refusal"))
    cases = policy_module.assign_policy_plan(cases, manifest_df)

    apartment_rules = registry[registry["rule_family"] == "apartment_min_floor_area"].copy()
    communal_rules = registry[registry["rule_family"] == "communal_amenity_min_per_unit"].copy()
    parking_base_rules = registry[registry["rule_family"] == "parking_min_spaces_per_unit"].copy()
    parking_visitor_rules = registry[registry["rule_family"] == "parking_visitor_spaces_per_unit_ratio"].copy()
    open_space_ratio_rules = registry[registry["rule_family"] == "open_space_min_site_ratio"].copy()
    if registry.empty:
        features = cases[["case_key", "PlanningAuthority", "ApplicationNumber", "policy_plan_key", "policy_coverage_flag"]].copy()
        features["hard_rule_apartment_size_rules_available"] = 0
        features["hard_rule_apartment_sizes_parsed"] = 0
        features["hard_rule_apartment_size_breach_count"] = 0
        features["hard_rule_apartment_size_breach_any"] = 0
        features["hard_rule_apartment_size_worst_margin_sqm"] = np.nan
        features["hard_rule_communal_amenity_rules_available"] = 0
        features["hard_rule_communal_amenity_subjects_available"] = ""
        features["hard_rule_parking_rules_available"] = 0
        features["hard_rule_parking_compare_possible"] = 0
        features["hard_rule_parking_required_spaces_min"] = np.nan
        features["hard_rule_parking_spaces_provided"] = np.nan
        features["hard_rule_parking_margin_spaces"] = np.nan
        features["hard_rule_parking_breach_any"] = 0
        features["hard_rule_parking_rule_basis"] = ""
        features["hard_rule_open_space_rules_available"] = 0
        features["hard_rule_open_space_compare_possible"] = 0
        features["hard_rule_open_space_required_sqm_min"] = np.nan
        features["hard_rule_open_space_sqm_provided"] = np.nan
        features["hard_rule_open_space_margin_sqm"] = np.nan
        features["hard_rule_open_space_breach_any"] = 0
        features["hard_rule_open_space_rule_basis"] = ""
        features.to_csv(CURRENT_DIR / "dublin_case_hard_rule_features.csv", index=False)
        pd.DataFrame().to_csv(CURRENT_DIR / "dublin_case_hard_rule_matches.csv", index=False)
        return features, pd.DataFrame()

    rules_by_plan = {
        plan_key: grp.sort_values("threshold_value").drop_duplicates(subset=["subject_type"], keep="first")
        for plan_key, grp in apartment_rules.groupby("plan_key")
    }
    communal_rules_by_plan = {
        plan_key: grp.sort_values(["subject_type", "threshold_value"]).drop_duplicates(subset=["subject_type"], keep="last")
        for plan_key, grp in communal_rules.groupby("plan_key")
    }
    parking_base_rules_by_plan = {
        plan_key: grp.sort_values(["subject_type", "threshold_value"]).drop_duplicates(subset=["subject_type"], keep="last")
        for plan_key, grp in parking_base_rules.groupby("plan_key")
    }
    parking_visitor_rules_by_plan = {
        plan_key: grp.sort_values(["subject_type", "threshold_value"]).drop_duplicates(subset=["subject_type"], keep="last")
        for plan_key, grp in parking_visitor_rules.groupby("plan_key")
    }
    open_space_ratio_rules_by_plan = {
        plan_key: grp.sort_values(["subject_type", "threshold_value"]).drop_duplicates(subset=["subject_type"], keep="last")
        for plan_key, grp in open_space_ratio_rules.groupby("plan_key")
    }

    match_rows = []
    feature_rows = []
    for _, case in cases.iterrows():
        parsed = parse_case_apartment_sizes(case.get("DevelopmentDescription", ""))
        plan_key = case.get("policy_plan_key", "")
        plan_rules = rules_by_plan.get(plan_key, pd.DataFrame())
        communal_plan_rules = communal_rules_by_plan.get(plan_key, pd.DataFrame(columns=communal_rules.columns))
        parking_plan_rules = parking_base_rules_by_plan.get(plan_key, pd.DataFrame(columns=parking_base_rules.columns))
        parking_visitor_plan_rules = parking_visitor_rules_by_plan.get(plan_key, pd.DataFrame(columns=parking_visitor_rules.columns))
        open_space_plan_rules = open_space_ratio_rules_by_plan.get(plan_key, pd.DataFrame(columns=open_space_ratio_rules.columns))
        breach_count = 0
        worst_margin = np.nan
        parsed_count = 0
        available_rules = int(len(plan_rules))
        communal_available_rules = int(len(communal_plan_rules))
        communal_subjects = ""
        if not communal_plan_rules.empty and "subject_type" in communal_plan_rules.columns:
            communal_subjects = ";".join(sorted(str(value) for value in communal_plan_rules["subject_type"].dropna().tolist()))
        parking_available_rules = int(len(parking_plan_rules) + len(parking_visitor_plan_rules))
        parking_compare_possible = 0
        parking_required_spaces_min = np.nan
        parking_spaces_provided = pd.to_numeric(pd.Series([case.get("parking_spaces_best")]), errors="coerce").iloc[0]
        parking_margin_spaces = np.nan
        parking_breach_any = 0
        parking_rule_basis = ""
        open_space_rules_available = int(len(open_space_plan_rules))
        open_space_compare_possible = 0
        open_space_required_sqm_min = np.nan
        open_space_sqm_provided = pd.to_numeric(pd.Series([case.get("open_space_sqm_best")]), errors="coerce").iloc[0]
        open_space_margin_sqm = np.nan
        open_space_breach_any = 0
        open_space_rule_basis = ""
        for _, rule in plan_rules.iterrows():
            subject = str(rule["subject_type"])
            case_size = parsed.get(subject)
            if case_size is None:
                continue
            parsed_count += 1
            margin = float(case_size - float(rule["threshold_value"]))
            if np.isnan(worst_margin) or margin < worst_margin:
                worst_margin = margin
            breached = int(margin < 0)
            breach_count += breached
            match_rows.append(
                {
                    "case_key": case["case_key"],
                    "PlanningAuthority": case["PlanningAuthority"],
                    "ApplicationNumber": case["ApplicationNumber"],
                    "policy_plan_key": plan_key,
                    "rule_family": rule["rule_family"],
                    "subject_type": subject,
                    "threshold_value": rule["threshold_value"],
                    "threshold_unit": rule["threshold_unit"],
                    "case_value": case_size,
                    "margin": margin,
                    "breached": breached,
                    "source_chunk_id": rule["source_chunk_id"],
                    "source_page_range": rule["source_page_range"],
                    "source_section_title": rule["source_section_title"],
                }
            )

        if parking_available_rules > 0 and not pd.isna(parking_spaces_provided):
            units_houses = pd.to_numeric(pd.Series([case.get("units_houses_best")]), errors="coerce").fillna(0).iloc[0]
            units_apartments = pd.to_numeric(pd.Series([case.get("units_apartments_best")]), errors="coerce").fillna(0).iloc[0]
            units_duplex = pd.to_numeric(pd.Series([case.get("units_duplex_best")]), errors="coerce").fillna(0).iloc[0]
            units_townhouses = pd.to_numeric(pd.Series([case.get("units_townhouses_best")]), errors="coerce").fillna(0).iloc[0]
            apartment_like_units = units_apartments + units_duplex + units_townhouses
            apartment_only_case = apartment_like_units > 0 and units_houses <= 0
            if apartment_only_case and not parking_plan_rules.empty:
                bed_counts = {
                    "1-bed": pd.to_numeric(pd.Series([case.get("bed_1_best")]), errors="coerce").fillna(0).iloc[0],
                    "2-bed": pd.to_numeric(pd.Series([case.get("bed_2_best")]), errors="coerce").fillna(0).iloc[0],
                    "3-bed": pd.to_numeric(pd.Series([case.get("bed_3_best")]), errors="coerce").fillna(0).iloc[0],
                    "4-bed": pd.to_numeric(pd.Series([case.get("bed_4_best")]), errors="coerce").fillna(0).iloc[0],
                    "5-bed": pd.to_numeric(pd.Series([case.get("bed_5_best")]), errors="coerce").fillna(0).iloc[0],
                }
                required_spaces = 0.0
                applied_rule = False
                for _, rule in parking_plan_rules.iterrows():
                    subject = str(rule.get("subject_type", ""))
                    value = float(rule["threshold_value"])
                    if subject == "apartment_1-bed":
                        required_spaces += bed_counts["1-bed"] * value
                        applied_rule = applied_rule or bed_counts["1-bed"] > 0
                    elif subject == "apartment_2-bed":
                        required_spaces += bed_counts["2-bed"] * value
                        applied_rule = applied_rule or bed_counts["2-bed"] > 0
                    elif subject in {"apartment_3-bed", "apartment_3-bed-plus"}:
                        if subject == "apartment_3-bed":
                            count = bed_counts["3-bed"]
                        else:
                            count = bed_counts["3-bed"] + bed_counts["4-bed"] + bed_counts["5-bed"]
                        required_spaces += count * value
                        applied_rule = applied_rule or count > 0
                if applied_rule:
                    for _, rule in parking_visitor_plan_rules.iterrows():
                        ratio = float(rule["threshold_value"])
                        required_spaces += math.ceil(apartment_like_units * ratio)
                    parking_compare_possible = 1
                    parking_required_spaces_min = required_spaces
                    parking_margin_spaces = float(parking_spaces_provided - required_spaces)
                    parking_breach_any = int(parking_margin_spaces < 0)
                    parking_rule_basis = "apartment_only_exact"

        if open_space_rules_available > 0 and not pd.isna(open_space_sqm_provided):
            site_area_sqm = pd.to_numeric(pd.Series([case.get("site_area_sqm_best")]), errors="coerce").iloc[0]
            if not pd.isna(site_area_sqm) and float(site_area_sqm) > 0:
                units_apartments = pd.to_numeric(pd.Series([case.get("units_apartments_best")]), errors="coerce").fillna(0).iloc[0]
                units_duplex = pd.to_numeric(pd.Series([case.get("units_duplex_best")]), errors="coerce").fillna(0).iloc[0]
                units_townhouses = pd.to_numeric(pd.Series([case.get("units_townhouses_best")]), errors="coerce").fillna(0).iloc[0]
                apartment_like_units = units_apartments + units_duplex + units_townhouses
                for _, rule in open_space_plan_rules.iterrows():
                    scope_note = str(rule.get("scope_note", ""))
                    subject = str(rule.get("subject_type", ""))
                    if scope_note != "apartment_total_open_space":
                        continue
                    if apartment_like_units <= 0:
                        continue
                    required_sqm = float(site_area_sqm) * float(rule["threshold_value"])
                    open_space_compare_possible = 1
                    open_space_required_sqm_min = required_sqm
                    open_space_margin_sqm = float(open_space_sqm_provided - required_sqm)
                    open_space_breach_any = int(open_space_margin_sqm < 0)
                    open_space_rule_basis = subject or scope_note
                    match_rows.append(
                        {
                            "case_key": case["case_key"],
                            "PlanningAuthority": case["PlanningAuthority"],
                            "ApplicationNumber": case["ApplicationNumber"],
                            "policy_plan_key": plan_key,
                            "rule_family": rule["rule_family"],
                            "subject_type": subject,
                            "threshold_value": rule["threshold_value"],
                            "threshold_unit": rule["threshold_unit"],
                            "case_value": float(open_space_sqm_provided / site_area_sqm),
                            "margin": open_space_margin_sqm,
                            "breached": open_space_breach_any,
                            "source_chunk_id": rule.get("source_chunk_id", ""),
                            "source_page_range": rule.get("source_page_range", ""),
                            "source_section_title": rule.get("source_section_title", ""),
                        }
                    )
                    break
        feature_rows.append(
            {
                "case_key": case["case_key"],
                "PlanningAuthority": case["PlanningAuthority"],
                "ApplicationNumber": case["ApplicationNumber"],
                "policy_plan_key": plan_key,
                "policy_coverage_flag": case["policy_coverage_flag"],
                "units_apartments_best": case.get("units_apartments_best"),
                "hard_rule_apartment_size_rules_available": available_rules,
                "hard_rule_apartment_sizes_parsed": parsed_count,
                "hard_rule_apartment_size_breach_count": breach_count,
                "hard_rule_apartment_size_breach_any": int(breach_count > 0),
                "hard_rule_apartment_size_worst_margin_sqm": worst_margin,
                "hard_rule_apartment_size_parseable_case": int(bool(parsed)),
                "hard_rule_apartment_size_subjects_found": ";".join(sorted(parsed)),
                "hard_rule_communal_amenity_rules_available": communal_available_rules,
                "hard_rule_communal_amenity_subjects_available": communal_subjects,
                "hard_rule_parking_rules_available": parking_available_rules,
                "hard_rule_parking_compare_possible": parking_compare_possible,
                "hard_rule_parking_required_spaces_min": parking_required_spaces_min,
                "hard_rule_parking_spaces_provided": parking_spaces_provided,
                "hard_rule_parking_margin_spaces": parking_margin_spaces,
                "hard_rule_parking_breach_any": parking_breach_any,
                "hard_rule_parking_rule_basis": parking_rule_basis,
                "hard_rule_open_space_rules_available": open_space_rules_available,
                "hard_rule_open_space_compare_possible": open_space_compare_possible,
                "hard_rule_open_space_required_sqm_min": open_space_required_sqm_min,
                "hard_rule_open_space_sqm_provided": open_space_sqm_provided,
                "hard_rule_open_space_margin_sqm": open_space_margin_sqm,
                "hard_rule_open_space_breach_any": open_space_breach_any,
                "hard_rule_open_space_rule_basis": open_space_rule_basis,
            }
        )

    features_df = pd.DataFrame(feature_rows)
    matches_df = pd.DataFrame(match_rows)
    features_df.to_csv(CURRENT_DIR / "dublin_case_hard_rule_features.csv", index=False)
    matches_df.to_csv(CURRENT_DIR / "dublin_case_hard_rule_matches.csv", index=False)
    return features_df, matches_df


def build_summary(registry: pd.DataFrame, features_df: pd.DataFrame, matches_df: pd.DataFrame) -> dict[str, object]:
    summary = {
        "rules_by_family": registry["rule_family"].value_counts().to_dict(),
        "case_rows": int(len(features_df)),
        "cases_with_apartments": int((pd.to_numeric(features_df.get("units_apartments_best"), errors="coerce").fillna(0) > 0).sum()),
        "cases_parseable_apartment_sizes": int(features_df["hard_rule_apartment_size_parseable_case"].sum()),
        "cases_with_breach_any": int(features_df["hard_rule_apartment_size_breach_any"].sum()),
        "cases_with_communal_amenity_rules_available": int(pd.to_numeric(features_df.get("hard_rule_communal_amenity_rules_available"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_parking_rules_available": int(pd.to_numeric(features_df.get("hard_rule_parking_rules_available"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_parking_compare_possible": int(pd.to_numeric(features_df.get("hard_rule_parking_compare_possible"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_parking_breach_any": int(pd.to_numeric(features_df.get("hard_rule_parking_breach_any"), errors="coerce").fillna(0).sum()),
        "cases_with_open_space_rules_available": int(pd.to_numeric(features_df.get("hard_rule_open_space_rules_available"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_open_space_compare_possible": int(pd.to_numeric(features_df.get("hard_rule_open_space_compare_possible"), errors="coerce").fillna(0).gt(0).sum()),
        "cases_with_open_space_breach_any": int(pd.to_numeric(features_df.get("hard_rule_open_space_breach_any"), errors="coerce").fillna(0).sum()),
        "total_rule_matches": int(len(matches_df)),
    }
    return summary


def main() -> None:
    policy_module = load_policy_module()
    chunks = pd.read_csv(CURRENT_DIR / "policy_chunks.csv")
    registry = build_hard_rules_registry(chunks)
    features_df, matches_df = build_case_hard_rule_features(policy_module, registry)
    summary = build_summary(registry, features_df, matches_df)
    (CURRENT_DIR / "dublin_hard_rule_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
