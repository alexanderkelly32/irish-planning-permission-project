from __future__ import annotations

import math
import re
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import linear_kernel
from pyproj import Transformer

GRANT_DECISIONS = {
    "CONDITIONAL",
    "UNCONDITIONAL",
    "GRANTED",
    "CONDITIONAL PERMISSION",
    "GRANT PERMISSION",
}
REFUSAL_DECISIONS = {"REFUSED"}
STOPWORDS = {
    "and",
    "with",
    "from",
    "that",
    "have",
    "this",
    "will",
    "into",
    "site",
    "development",
    "proposed",
    "housing",
    "works",
}
_ITM_TO_WGS84 = Transformer.from_crs("EPSG:2157", "EPSG:4326", always_xy=True)
CURRENT_DATE = date(2026, 8, 30)
THEME_LABELS = {
    "density_scale": "height / scale / density",
    "design_layout": "design / layout",
    "traffic_access": "traffic / access / parking",
    "residential_amenity": "residential amenity",
    "flooding_drainage": "flood / drainage",
    "land_use_policy": "policy conflict / land use",
    "premature_or_info_gap": "prematurity / missing information",
    "heritage_archaeology": "heritage / archaeology",
    "ecology_trees": "ecology / trees",
    "water_wastewater": "water / wastewater",
    "other": "other",
}
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


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_ws(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def short_text(value: object, length: int = 220) -> str:
    text = clean_text(value)
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."


def token_set(value: object) -> set[str]:
    text = clean_text(value).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text)
        if token not in STOPWORDS
    }


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


def normalize_decision(value: object) -> str:
    text = clean_text(value).upper()
    if text in REFUSAL_DECISIONS:
        return "REFUSED"
    if text in GRANT_DECISIONS:
        return "GRANTED"
    if "REFUS" in text:
        return "REFUSED"
    if "GRANT" in text or "CONDITIONAL" in text or "UNCONDITIONAL" in text:
        return "GRANTED"
    if text in {"INVALID", "WITHDRAWN"}:
        return text
    return text or "UNKNOWN"


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    if math.isnan(parsed):
        return None
    return parsed


def normalize_cases(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["decision_normalized"] = out.get("Decision", "").map(normalize_decision)
    out["reason_count_num"] = pd.to_numeric(out.get("reason_count"), errors="coerce").fillna(0.0)
    out["fi_count_num"] = pd.to_numeric(out.get("fi_request_items_count"), errors="coerce").fillna(0.0)
    out["units_total_num"] = pd.to_numeric(
        out.get("units_total_best", out.get("NumResidentialUnits")),
        errors="coerce",
    )
    out["max_storeys_num"] = pd.to_numeric(out.get("max_storeys_best"), errors="coerce")
    out["site_area_ha_num"] = pd.to_numeric(
        out.get("site_area_ha_best", out.get("AreaofSite")),
        errors="coerce",
    )
    out["itm_easting_num"] = pd.to_numeric(out.get("ITMEasting"), errors="coerce")
    out["itm_northing_num"] = pd.to_numeric(out.get("ITMNorthing"), errors="coerce")
    out["source_url"] = out.get("fi_resolved_url").fillna(out.get("LinkAppDetails")).fillna("")
    out["refusal_excerpt"] = out.get("reasons_joined", "").map(lambda v: short_text(v, 500))
    out["fi_excerpt"] = out.get("fi_request_items_joined", "").map(lambda v: short_text(v, 500))
    out["case_summary"] = out.apply(build_case_summary, axis=1)
    out["coverage_note"] = out.apply(build_coverage_note, axis=1)
    out["risk_flags"] = out.apply(build_risk_flags, axis=1)
    out["latitude"], out["longitude"] = _transform_itm_series(
        out["itm_easting_num"],
        out["itm_northing_num"],
    )
    return out


def _transform_itm_series(easting: pd.Series, northing: pd.Series) -> tuple[pd.Series, pd.Series]:
    lat_values: list[float | None] = []
    lon_values: list[float | None] = []
    for e, n in zip(easting.tolist(), northing.tolist(), strict=False):
        if pd.isna(e) or pd.isna(n):
            lat_values.append(None)
            lon_values.append(None)
            continue
        lon, lat = _ITM_TO_WGS84.transform(float(e), float(n))
        lat_values.append(lat)
        lon_values.append(lon)
    return pd.Series(lat_values), pd.Series(lon_values)


def build_case_summary(row: pd.Series) -> str:
    bits: list[str] = []
    units = safe_float(row.get("units_total_best", row.get("NumResidentialUnits")))
    if units is not None:
        bits.append(f"{int(units)} units")
    if clean_text(row.get("ApplicationType")):
        bits.append(clean_text(row.get("ApplicationType")).title())
    if clean_text(row.get("Decision")):
        bits.append(clean_text(row.get("Decision")).title())
    description = short_text(row.get("DevelopmentDescription"), 180)
    if description:
        bits.append(description)
    return " | ".join(bits)


def build_coverage_note(row: pd.Series) -> str:
    notes: list[str] = []
    extraction_source = clean_text(row.get("extraction_source"))
    extraction_method = clean_text(row.get("extraction_method"))
    fi_status = clean_text(row.get("fi_request_extraction_status"))
    if extraction_source == "pdf_ocr":
        notes.append("decision reasons derived from OCR")
    if extraction_method in {"not_found", "fallback"}:
        notes.append("low-confidence refusal extraction")
    if safe_float(row.get("reason_count")) in {None, 0.0} and normalize_decision(row.get("Decision")) == "REFUSED":
        notes.append("no structured refusal reasons extracted")
    if safe_float(row.get("fi_request_items_count")) in {None, 0.0}:
        notes.append("no structured FI items extracted")
    elif fi_status and fi_status != "ok":
        notes.append(f"FI extraction status: {fi_status}")
    return "; ".join(notes) if notes else "good structured coverage"


def build_risk_flags(row: pd.Series) -> str:
    flags: list[str] = []
    tag = clean_text(row.get("case_top_primary_tag"))
    if tag:
        flags.append(tag)
    if safe_float(row.get("fi_request_items_count")) not in {None, 0.0}:
        flags.append("fi-heavy")
    if normalize_decision(row.get("Decision")) == "REFUSED":
        flags.append("refusal")
    return ", ".join(flags)


def build_query_payload(
    *,
    planning_authority: str = "",
    application_type: str = "",
    description: str = "",
    address: str = "",
    units_total: float | None = None,
    storeys: float | None = None,
    site_area_ha: float | None = None,
    itm_easting: float | None = None,
    itm_northing: float | None = None,
    issue_tag: str = "",
    uploaded_documents: Iterable[str] | None = None,
) -> dict[str, object]:
    return {
        "PlanningAuthority": planning_authority or None,
        "ApplicationType": application_type or None,
        "DevelopmentDescription": description,
        "DevelopmentAddress": address,
        "units_total_best": units_total,
        "NumResidentialUnits": units_total,
        "max_storeys_best": storeys,
        "site_area_ha_best": site_area_ha,
        "ITMEasting": itm_easting,
        "ITMNorthing": itm_northing,
        "case_top_primary_tag": issue_tag or None,
        "uploaded_documents": list(uploaded_documents or []),
        "received_year": float(CURRENT_DATE.year),
    }


def _infer_query_devtype_features(description: object, units_total: object) -> dict[str, float]:
    text = clean_text(description).lower()
    units = safe_float(units_total) or 0.0
    return {
        "dev_type_apartment": float(bool(re.search(r"\bapartments?\b", text))),
        "dev_type_houses": float(bool(re.search(r"\bhouses?\b|\bdwellings?\b", text))),
        "dev_type_mixed_use": float(bool(re.search(r"\bmixed[- ]use\b", text))),
        "dev_type_retention": float(bool(re.search(r"\bretention\b|\bretain\b", text))),
        "dev_type_demolition": float(bool(re.search(r"\bdemolition\b|\bdemolish\b", text))),
        "dev_type_outline": float(bool(re.search(r"\boutline permission\b|\boutline\b", text))),
        "dev_type_change_of_use": float(bool(re.search(r"\bchange of use\b|\bchange use\b", text))),
        "dev_type_protected_structure": float(bool(re.search(r"\bprotected structure\b|\bconservation\b", text))),
        "dev_type_student": float(bool(re.search(r"\bstudent accommodation\b|\bpbsa\b", text))),
        "dev_type_large_scheme": float(units >= 100),
    }


def build_submission_risk_features(query: dict[str, object]) -> pd.DataFrame:
    description = clean_text(query.get("DevelopmentDescription"))
    received_year = safe_float(query.get("received_year"))
    if received_year is None:
        received_year = float(CURRENT_DATE.year)
    feature_row = {
        "PlanningAuthority": clean_text(query.get("PlanningAuthority")),
        "received_year": received_year,
        "proposal_text_stripped": strip_text_leakage_clues(description),
    }
    feature_row.update(_infer_query_devtype_features(description, query.get("units_total_best")))
    return pd.DataFrame([feature_row], columns=["PlanningAuthority", "received_year", *DEVELOPMENT_TYPE_COLUMNS, "proposal_text_stripped"])


def infer_residential_application_bucket(query: dict[str, object]) -> str:
    description = clean_text(query.get("DevelopmentDescription")).lower()
    application_type = clean_text(query.get("ApplicationType")).lower()
    units = safe_float(query.get("units_total_best", query.get("NumResidentialUnits")))
    if "retention" in application_type or re.search(r"\bretention\b|\bretain\b", description):
        return "retention"
    if re.search(r"\bchange of use\b|\bchange use\b", description):
        return "change of use"
    if re.search(r"\bextension\b|\balteration\b|\brenovation\b|\brefurbishment\b", description):
        return "extension / alteration"
    if units == 1:
        return "single dwelling"
    if units is not None and 2 <= units <= 9:
        return "2-9 units"
    if units is not None and units >= 10:
        return "10+ units"
    if re.search(r"\bone[- ]off\b|\bsingle house\b|\bsingle dwelling\b|\bhouse\b", description):
        return "single dwelling"
    return "other residential"


def build_v1_risk_features(query: dict[str, object]) -> pd.DataFrame:
    received_year = safe_float(query.get("received_year")) or float(CURRENT_DATE.year)
    return pd.DataFrame(
        [
            {
                "received_year": received_year,
                "PlanningAuthority": clean_text(query.get("PlanningAuthority")),
                "application_bucket": infer_residential_application_bucket(query),
                "description_stripped": strip_text_leakage_clues(query.get("DevelopmentDescription")),
            }
        ]
    )


def query_received_timestamp(query: dict[str, object]) -> pd.Timestamp:
    explicit = query.get("received_date") or query.get("ReceivedDate")
    if explicit:
        parsed = pd.to_datetime(explicit, utc=True, errors="coerce")
        if not pd.isna(parsed):
            return parsed
    received_year = int(safe_float(query.get("received_year")) or CURRENT_DATE.year)
    if received_year == CURRENT_DATE.year:
        return pd.Timestamp(CURRENT_DATE, tz="UTC")
    return pd.Timestamp(year=received_year, month=7, day=1, tz="UTC")


def _prior_count_rate(reference: pd.DataFrame, target: pd.Timestamp, window_days: int | None = None) -> tuple[float, float | None]:
    if reference.empty or "received_date_dt" not in reference.columns:
        return 0.0, None
    dates = pd.to_datetime(reference["received_date_dt"], utc=True, errors="coerce")
    mask = dates < target
    if window_days is not None:
        mask &= dates >= target - pd.Timedelta(days=window_days)
    prior = reference[mask]
    if prior.empty:
        return 0.0, None
    target_values = pd.to_numeric(prior.get("target_refused"), errors="coerce").dropna()
    if target_values.empty:
        return float(len(prior)), None
    return float(len(prior)), float(target_values.mean())


def _nearby_prior_count_rate(
    reference: pd.DataFrame,
    *,
    target: pd.Timestamp,
    easting: float | None,
    northing: float | None,
    radius_m: float,
    window_days: int,
) -> tuple[float, float | None]:
    if reference.empty or easting is None or northing is None:
        return 0.0, None
    refs = reference.copy()
    refs["ITMEasting"] = pd.to_numeric(refs.get("ITMEasting"), errors="coerce")
    refs["ITMNorthing"] = pd.to_numeric(refs.get("ITMNorthing"), errors="coerce")
    refs["received_date_dt"] = pd.to_datetime(refs.get("received_date_dt"), utc=True, errors="coerce")
    refs = refs[
        refs["ITMEasting"].notna()
        & refs["ITMNorthing"].notna()
        & refs["received_date_dt"].notna()
        & (refs["received_date_dt"] < target)
        & (refs["received_date_dt"] >= target - pd.Timedelta(days=window_days))
    ]
    if refs.empty:
        return 0.0, None
    distance_m = ((refs["ITMEasting"] - easting) ** 2 + (refs["ITMNorthing"] - northing) ** 2) ** 0.5
    nearby = refs[distance_m <= radius_m]
    if nearby.empty:
        return 0.0, None
    target_values = pd.to_numeric(nearby.get("target_refused"), errors="coerce").dropna()
    if target_values.empty:
        return float(len(nearby)), None
    return float(len(nearby)), float(target_values.mean())


def build_v2_risk_features(query: dict[str, object], model: dict[str, object]) -> tuple[pd.DataFrame, dict[str, object]]:
    base = build_v1_risk_features(query).rename(columns={"proposal_text_stripped": "description_stripped"})
    reference = model.get("history_reference", pd.DataFrame())
    if not isinstance(reference, pd.DataFrame):
        reference = pd.DataFrame()
    target_date = query_received_timestamp(query)
    effective_history_date = target_date
    if not reference.empty and "received_date_dt" in reference.columns:
        max_reference_date = pd.to_datetime(reference["received_date_dt"], utc=True, errors="coerce").max()
        if not pd.isna(max_reference_date):
            latest_available = max_reference_date + pd.Timedelta(days=1)
            if target_date > latest_available:
                effective_history_date = latest_available
    authority = clean_text(query.get("PlanningAuthority"))
    easting = safe_float(query.get("ITMEasting"))
    northing = safe_float(query.get("ITMNorthing"))
    site_id = clean_text(query.get("SiteId"))

    row = base.iloc[0].to_dict()
    national_count, national_rate = _prior_count_rate(reference, effective_history_date, 730)
    authority_reference = reference[reference.get("PlanningAuthority", pd.Series(dtype=str)).astype(str) == authority] if authority else pd.DataFrame()
    auth_12_count, auth_12_rate = _prior_count_rate(authority_reference, effective_history_date, 365)
    auth_24_count, auth_24_rate = _prior_count_rate(authority_reference, effective_history_date, 730)
    if site_id and "SiteId" in reference.columns:
        site_reference = reference[reference["SiteId"].fillna("").astype(str) == site_id]
    else:
        site_reference = pd.DataFrame()
    site_count, site_rate = _prior_count_rate(site_reference, effective_history_date, None)
    near_1_count, near_1_rate = _nearby_prior_count_rate(
        authority_reference,
        target=effective_history_date,
        easting=easting,
        northing=northing,
        radius_m=1000.0,
        window_days=730,
    )
    near_3_count, near_3_rate = _nearby_prior_count_rate(
        authority_reference,
        target=effective_history_date,
        easting=easting,
        northing=northing,
        radius_m=3000.0,
        window_days=730,
    )
    raw_values = {
        "national_prior_24m_count": national_count,
        "authority_prior_12m_count": auth_12_count,
        "authority_prior_24m_count": auth_24_count,
        "same_site_prior_count": site_count,
        "nearby_1km_prior_24m_count": near_1_count,
        "nearby_3km_prior_24m_count": near_3_count,
        "national_prior_24m_refusal_rate": national_rate,
        "authority_prior_12m_refusal_rate": auth_12_rate,
        "authority_prior_24m_refusal_rate": auth_24_rate,
        "same_site_prior_refusal_rate": site_rate,
        "nearby_1km_prior_24m_refusal_rate": near_1_rate,
        "nearby_3km_prior_24m_refusal_rate": near_3_rate,
    }
    for key, value in raw_values.items():
        if key.endswith("_count"):
            row[f"log_{key}"] = math.log1p(float(value or 0.0))
        else:
            row[key] = np.nan if value is None else float(value)
    feature_columns = list(model.get("feature_columns", row.keys()))
    feature_snapshot = {column: row.get(column, np.nan) for column in feature_columns}
    diagnostics = {
        "history_reference_rows": int(len(reference)),
        "history_target_date": str(target_date),
        "effective_history_date": str(effective_history_date),
        "history_was_capped_to_reference": bool(effective_history_date != target_date),
        "nearby_history_available": easting is not None and northing is not None,
        "same_site_history_available": bool(site_id),
        "history_raw_values": raw_values,
    }
    return pd.DataFrame([feature_snapshot], columns=feature_columns), diagnostics


def _query_comparable_values(query: dict[str, object], model: dict[str, object], application_bucket: str, effective_history_date: pd.Timestamp) -> dict[str, float | None]:
    reference = model.get("comparable_reference", pd.DataFrame())
    vectorizer = model.get("comparable_vectorizer")
    if not isinstance(reference, pd.DataFrame) or reference.empty or vectorizer is None:
        return {"comp_top20_count": 0.0}
    refs = reference.copy()
    refs["received_date_dt"] = pd.to_datetime(refs.get("received_date_dt"), utc=True, errors="coerce")
    lookback_years = int(model.get("comparable_lookback_years", 8))
    refs = refs[
        (refs["application_bucket"].astype(str) == application_bucket)
        & refs["received_date_dt"].notna()
        & (refs["received_date_dt"] < effective_history_date)
        & (refs["received_date_dt"] >= effective_history_date - pd.DateOffset(years=lookback_years))
    ]
    if refs.empty:
        return {"comp_top20_count": 0.0}

    query_text = strip_text_leakage_clues(query.get("DevelopmentDescription"))
    x_query = vectorizer.transform([query_text])
    x_refs = vectorizer.transform(refs["description_stripped"].fillna("").astype(str))
    similarity = linear_kernel(x_query, x_refs).ravel()
    k = min(20, len(refs))
    top_idx = np.argpartition(-similarity, kth=np.arange(k))[:k]
    top_idx = top_idx[np.argsort(-similarity[top_idx])]
    top = refs.iloc[top_idx].copy()
    top_similarity = similarity[top_idx]
    top_target = pd.to_numeric(top["target_refused"], errors="coerce").to_numpy(dtype=float)
    same_authority = top["PlanningAuthority"].fillna("").astype(str).to_numpy() == clean_text(query.get("PlanningAuthority"))
    refused_similarity = top_similarity[top_target == 1]
    granted_similarity = top_similarity[top_target == 0]
    same_authority_target = top_target[same_authority]

    def rate_for(count: int) -> float | None:
        values = top_target[: min(count, len(top_target))]
        values = values[np.isfinite(values)]
        return None if len(values) == 0 else float(values.mean())

    return {
        "comp_top5_refusal_rate": rate_for(5),
        "comp_top10_refusal_rate": rate_for(10),
        "comp_top20_refusal_rate": rate_for(20),
        "comp_top20_mean_similarity": float(np.nanmean(top_similarity)),
        "comp_top20_max_refused_similarity": None if len(refused_similarity) == 0 else float(np.nanmax(refused_similarity)),
        "comp_top20_max_granted_similarity": None if len(granted_similarity) == 0 else float(np.nanmax(granted_similarity)),
        "comp_top20_refused_similarity_gap": (
            None
            if len(refused_similarity) == 0 or len(granted_similarity) == 0
            else float(np.nanmax(refused_similarity) - np.nanmax(granted_similarity))
        ),
        "comp_top20_same_authority_share": float(np.mean(same_authority)),
        "comp_top20_same_authority_refusal_rate": None
        if len(same_authority_target) == 0
        else float(np.nanmean(same_authority_target)),
        "comp_top20_count": float(k),
    }


def build_v3_risk_features(query: dict[str, object], model: dict[str, object]) -> tuple[pd.DataFrame, dict[str, object]]:
    features, diagnostics = build_v2_risk_features(query, model)
    row = features.iloc[0].to_dict()
    application_bucket = str(row.get("application_bucket", infer_residential_application_bucket(query)))
    effective_history_date = pd.to_datetime(
        diagnostics.get("effective_history_date") or diagnostics.get("history_target_date"),
        utc=True,
        errors="coerce",
    )
    if pd.isna(effective_history_date):
        effective_history_date = query_received_timestamp(query)
    comparable_values = _query_comparable_values(query, model, application_bucket, effective_history_date)
    for key in model.get("comparable_features", []):
        value = comparable_values.get(key)
        row[key] = np.nan if value is None else float(value)
    diagnostics["comparable_raw_values"] = comparable_values
    diagnostics["comparable_reference_rows"] = int(len(model.get("comparable_reference", pd.DataFrame())))
    feature_columns = list(model.get("feature_columns", row.keys()))
    feature_snapshot = {column: row.get(column, np.nan) for column in feature_columns}
    return pd.DataFrame([feature_snapshot], columns=feature_columns), diagnostics


def reliability_lookup(frame: pd.DataFrame, group_col: str, group_value: str, risk_band: str) -> dict[str, object]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or group_col not in frame.columns:
        return {}
    match = frame[(frame[group_col].astype(str) == group_value) & (frame["risk_band"].astype(str) == risk_band)]
    if match.empty:
        return {}
    row = match.iloc[0]
    return {
        "cases": int(row.get("cases", 0)),
        "actual_refusal_rate": safe_float(row.get("actual_refusal_rate")),
        "evaluation_auc": safe_float(row.get("evaluation_auc")),
        "evaluation_n": int(row.get("evaluation_n", 0)),
        "confidence": clean_text(row.get("confidence")),
    }


def compute_match_reasons(query: dict[str, object], row: pd.Series) -> list[str]:
    reasons: list[str] = []
    query_pa = clean_text(query.get("PlanningAuthority"))
    row_pa = clean_text(row.get("PlanningAuthority"))
    if query_pa and row_pa and query_pa.lower() == row_pa.lower():
        reasons.append(f"same planning authority: {row_pa}")

    query_type = clean_text(query.get("ApplicationType"))
    row_type = clean_text(row.get("ApplicationType"))
    if query_type and row_type and query_type.lower() == row_type.lower():
        reasons.append(f"same application type: {row_type}")

    query_units = safe_float(query.get("units_total_best"))
    row_units = safe_float(row.get("units_total_num", row.get("units_total_best")))
    if query_units is not None and row_units is not None:
        gap = abs(query_units - row_units)
        if gap <= 5:
            reasons.append(f"very similar scale: {int(row_units)} units")
        elif gap <= 15:
            reasons.append(f"comparable scale: {int(row_units)} units")

    query_tag = clean_text(query.get("case_top_primary_tag")).lower()
    row_tag = clean_text(row.get("case_top_primary_tag")).lower()
    if query_tag and row_tag and query_tag == row_tag:
        reasons.append(f"same issue theme: {row_tag}")

    overlap = sorted(
        token_set(query.get("DevelopmentDescription"))
        & token_set(row.get("DevelopmentDescription"))
    )
    if overlap:
        reasons.append("shared terms: " + ", ".join(overlap[:5]))

    query_easting = safe_float(query.get("ITMEasting"))
    query_northing = safe_float(query.get("ITMNorthing"))
    row_easting = safe_float(row.get("itm_easting_num", row.get("ITMEasting")))
    row_northing = safe_float(row.get("itm_northing_num", row.get("ITMNorthing")))
    if None not in {query_easting, query_northing, row_easting, row_northing}:
        distance_km = itm_distance_km(query_easting, query_northing, row_easting, row_northing)
        reasons.append(f"nearby: {distance_km:.1f} km away")

    return reasons[:5]


def itm_distance_km(e1: float, n1: float, e2: float, n2: float) -> float:
    return float((((e1 - e2) ** 2) + ((n1 - n2) ** 2)) ** 0.5 / 1000.0)


def rerank_candidates(df: pd.DataFrame, query: dict[str, object]) -> pd.DataFrame:
    out = df.copy()
    query_units = safe_float(query.get("units_total_best"))
    query_easting = safe_float(query.get("ITMEasting"))
    query_northing = safe_float(query.get("ITMNorthing"))
    query_pa = clean_text(query.get("PlanningAuthority")).lower()
    query_type = clean_text(query.get("ApplicationType")).lower()
    query_tag = clean_text(query.get("case_top_primary_tag")).lower()
    query_tokens = token_set(query.get("DevelopmentDescription"))

    out["text_score"] = pd.to_numeric(out.get("similarity"), errors="coerce").fillna(0.0)
    out["authority_score"] = (
        out["PlanningAuthority"].fillna("").astype(str).str.lower().eq(query_pa).astype(float)
        if query_pa
        else 0.0
    )
    out["type_score"] = (
        out["ApplicationType"].fillna("").astype(str).str.lower().eq(query_type).astype(float)
        if query_type
        else 0.0
    )
    if query_units is not None:
        denom = np.maximum(out["units_total_num"].fillna(query_units).astype(float), query_units)
        denom = np.where(denom <= 0, 1.0, denom)
        gap = np.abs(out["units_total_num"].fillna(query_units).astype(float) - query_units)
        out["scale_score"] = np.clip(1.0 - (gap / denom), 0.0, 1.0)
    else:
        out["scale_score"] = 0.0

    if query_tag:
        out["tag_score"] = (
            out["case_top_primary_tag"].fillna("").astype(str).str.lower().eq(query_tag).astype(float)
        )
    else:
        out["tag_score"] = 0.0

    if query_tokens:
        out["token_overlap_score"] = out["DevelopmentDescription"].map(
            lambda value: token_overlap_ratio(query_tokens, token_set(value))
        )
    else:
        out["token_overlap_score"] = 0.0

    if None not in {query_easting, query_northing}:
        distances = []
        for _, row in out.iterrows():
            row_easting = safe_float(row.get("itm_easting_num"))
            row_northing = safe_float(row.get("itm_northing_num"))
            if None in {row_easting, row_northing}:
                distances.append(np.nan)
            else:
                distances.append(itm_distance_km(query_easting, query_northing, row_easting, row_northing))
        out["distance_km"] = distances
        out["geo_score"] = 1.0 - np.clip(out["distance_km"].fillna(25.0) / 25.0, 0.0, 1.0)
    else:
        out["distance_km"] = np.nan
        out["geo_score"] = 0.0

    # Rerank weights tuned against the human retrieval benchmark (rerank_weight_tuning_2026-09-05.json,
    # held-out NDCG@10 0.921 -> 0.940). See 06_copilot/current/rerank_weight_tuning_2026-09-05.json.
    tuned = {
        "text": 0.2249,
        "authority": 0.0525,
        "scale": 0.2782,
        "geo": 0.1955,
        "tag": 0.1179,
        "token": 0.1310,
    }
    out["hybrid_score"] = (
        (out["text_score"] * tuned["text"])
        + (out["authority_score"] * tuned["authority"])
        + (out["scale_score"] * tuned["scale"])
        + (out["geo_score"] * tuned["geo"])
        + (out["tag_score"] * tuned["tag"])
        + (out["token_overlap_score"] * tuned["token"])
    )
    out["match_reasons"] = out.apply(lambda row: " | ".join(compute_match_reasons(query, row)), axis=1)
    return out.sort_values(["hybrid_score", "text_score", "fi_count_num"], ascending=[False, False, False])


def token_overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union


def summarize_risk_themes(df: pd.DataFrame, limit: int = 5) -> list[tuple[str, int]]:
    tags = (
        df["case_top_primary_tag"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    tags = tags[tags != ""]
    if tags.empty:
        return []
    counts = tags.value_counts().head(limit)
    return [(str(tag), int(count)) for tag, count in counts.items()]


def weighted_theme_summary(df: pd.DataFrame, limit: int = 4) -> list[dict[str, object]]:
    if df.empty:
        return []
    weights = pd.to_numeric(df.get("hybrid_score"), errors="coerce").fillna(0.0) + 0.05
    theme_scores: dict[str, float] = {}
    theme_counts: dict[str, int] = {}
    raw_multi = df.get("case_primary_tags", pd.Series("", index=df.index)).fillna("").astype(str).tolist()
    raw_top = df.get("case_top_primary_tag", pd.Series("", index=df.index)).fillna("").astype(str).tolist()
    for weight, tags, top_tag in zip(weights.tolist(), raw_multi, raw_top, strict=False):
        if not clean_text(tags) and clean_text(top_tag):
            tags = clean_text(top_tag)
        seen = set()
        for tag in [part.strip() for part in tags.split(";") if part.strip()]:
            if tag in seen:
                continue
            seen.add(tag)
            theme_scores[tag] = theme_scores.get(tag, 0.0) + float(weight)
            theme_counts[tag] = theme_counts.get(tag, 0) + 1
    ranked = sorted(theme_scores.items(), key=lambda item: (-item[1], -theme_counts.get(item[0], 0), item[0]))
    return [
        {
            "tag": tag,
            "label": THEME_LABELS.get(tag, tag.replace("_", " ")),
            "weighted_score": round(score, 3),
            "case_count": int(theme_counts.get(tag, 0)),
        }
        for tag, score in ranked[:limit]
    ]


def classify_risk_band(score_0_100: float | None) -> str:
    if score_0_100 is None:
        return "Not scored"
    if score_0_100 >= 70:
        return "High"
    if score_0_100 >= 45:
        return "Medium"
    return "Lower"


def infer_pressure_signals(query: dict[str, object], local_cases: pd.DataFrame) -> list[str]:
    signals: list[str] = []
    description = clean_text(query.get("DevelopmentDescription")).lower()
    devtype = _infer_query_devtype_features(description, query.get("units_total_best"))
    if devtype["dev_type_apartment"]:
        signals.append("apartment-led proposal")
    if devtype["dev_type_demolition"]:
        signals.append("includes demolition")
    if devtype["dev_type_retention"]:
        signals.append("includes retention elements")
    if devtype["dev_type_change_of_use"]:
        signals.append("change-of-use element")
    if devtype["dev_type_protected_structure"]:
        signals.append("protected-structure or conservation context")
    if "basement" in description:
        signals.append("basement works mentioned")

    units = safe_float(query.get("units_total_best"))
    if units is not None and units >= 100:
        signals.append("large scheme by unit count")
    storeys = safe_float(query.get("max_storeys_best"))
    if storeys is not None and storeys >= 6:
        signals.append("taller scheme")

    granted_local = local_cases[local_cases["decision_normalized"] == "GRANTED"].copy()
    if units is not None and not granted_local.empty:
        granted_units = pd.to_numeric(granted_local.get("units_total_num"), errors="coerce").dropna()
        if not granted_units.empty and units > float(granted_units.quantile(0.75)):
            signals.append("larger than most nearby granted comparables")
    if storeys is not None and not granted_local.empty:
        granted_storeys = pd.to_numeric(granted_local.get("max_storeys_num"), errors="coerce").dropna()
        if not granted_storeys.empty and storeys > float(granted_storeys.quantile(0.75)):
            signals.append("taller than most nearby granted comparables")
    return signals[:5]


def score_submission_risk(query: dict[str, object], model) -> dict[str, object]:
    if not clean_text(query.get("PlanningAuthority")):
        return {"status": "skipped", "reason": "planning_authority_missing"}
    supported_bundle_versions = {
        "national_residential_v1",
        "national_residential_v2_history",
        "national_residential_v3_comparables",
    }
    if isinstance(model, dict) and model.get("model_version") in supported_bundle_versions:
        diagnostics: dict[str, object] = {}
        if model.get("model_version") == "national_residential_v3_comparables":
            features, diagnostics = build_v3_risk_features(query, model)
        elif model.get("model_version") == "national_residential_v2_history":
            features, diagnostics = build_v2_risk_features(query, model)
        else:
            features = build_v1_risk_features(query)
        ranking_score = float(model["ranking_model"].predict_proba(features)[:, 1][0])
        calibration_score = float(model["calibrated_base_model"].predict_proba(features)[:, 1][0])
        calibration_score = min(max(calibration_score, 1e-6), 1 - 1e-6)
        calibration_logit = np.array([[np.log(calibration_score / (1.0 - calibration_score))]])
        refusal_score = float(model["platt_calibrator"].predict_proba(calibration_logit)[:, 1][0])
        thresholds = model.get("risk_band_thresholds", {})
        low_max = float(thresholds.get("low_max", 0.10))
        medium_max = float(thresholds.get("medium_max", 0.25))
        risk_band = "Low" if refusal_score <= low_max else "Medium" if refusal_score <= medium_max else "High"
        authority = clean_text(query.get("PlanningAuthority"))
        application_bucket = str(features.iloc[0]["application_bucket"])
        authority_metadata = model.get("authority_reliability", pd.DataFrame())
        type_metadata = model.get("type_reliability", pd.DataFrame())

        score_0_100 = round(refusal_score * 100.0, 1)
        return {
            "status": "scored",
            "model_version": model["model_version"],
            "refusal_score": refusal_score,
            "ranking_score": ranking_score,
            "risk_score_0_100": score_0_100,
            "risk_band": risk_band,
            "application_bucket": application_bucket,
            "authority_reliability": reliability_lookup(authority_metadata, "PlanningAuthority", authority, risk_band),
            "application_type_reliability": reliability_lookup(type_metadata, "application_bucket", application_bucket, risk_band),
            "feature_snapshot": features.iloc[0].to_dict(),
            "history_diagnostics": diagnostics,
        }

    features = build_submission_risk_features(query)
    refusal_score = float(model.predict_proba(features)[:, 1][0])
    score_0_100 = round(refusal_score * 100.0, 1)
    return {
        "status": "scored",
        "refusal_score": refusal_score,
        "risk_score_0_100": score_0_100,
        "risk_band": classify_risk_band(score_0_100),
        "feature_snapshot": features.iloc[0].to_dict(),
    }


def build_planning_risk_report(
    query: dict[str, object],
    results: dict[str, pd.DataFrame],
    model,
) -> dict[str, object]:
    overall = results.get("overall", pd.DataFrame()).head(8).copy()
    local_cases = results.get("local", pd.DataFrame()).head(12).copy()
    refusals = results.get("refusals", pd.DataFrame()).head(12).copy()
    grants = results.get("grants", pd.DataFrame()).head(12).copy()
    fi_cases = results.get("fi", pd.DataFrame()).head(12).copy()
    score = score_submission_risk(query, model)
    top_themes = weighted_theme_summary(pd.concat([refusals, fi_cases]).drop_duplicates("case_key"), limit=4)
    return {
        "score": score,
        "pressure_signals": infer_pressure_signals(query, local_cases if not local_cases.empty else overall),
        "top_themes": top_themes,
        "closest_precedents": overall[
            [
                c for c in [
                    "case_key",
                    "PlanningAuthority",
                    "ApplicationNumber",
                    "Decision",
                    "hybrid_score",
                    "distance_km",
                    "case_top_primary_tag",
                    "match_reasons",
                ] if c in overall.columns
            ]
        ].copy(),
        "precedent_mix": {
            "closest_cases": int(len(overall)),
            "grants": int((overall.get("decision_normalized", pd.Series(dtype=str)) == "GRANTED").sum()),
            "refusals": int((overall.get("decision_normalized", pd.Series(dtype=str)) == "REFUSED").sum()),
            "fi_cases": int((pd.to_numeric(overall.get("fi_count_num"), errors="coerce").fillna(0.0) > 0).sum()),
        },
        "evidence_cases": {
            "refusals": refusals,
            "grants": grants,
            "fi": fi_cases,
        },
    }


def build_evidence_lines(df: pd.DataFrame, label: str, limit: int = 5) -> list[str]:
    lines: list[str] = []
    for _, row in df.head(limit).iterrows():
        citation = citation_label(row)
        evidence = short_text(best_evidence_text(row), 240)
        lines.append(f"- {label}: {citation}. Evidence: {evidence}")
    return lines


def citation_label(row: pd.Series) -> str:
    return (
        f"{clean_text(row.get('PlanningAuthority'))} "
        f"{clean_text(row.get('ApplicationNumber'))} "
        f"({clean_text(row.get('Decision'))})"
    ).strip()


def recommended_evidence_pack(refused: pd.DataFrame, fi_cases: pd.DataFrame) -> list[str]:
    recommendations: list[str] = []
    themes = {tag for tag, _ in summarize_risk_themes(refused, limit=4)}
    fi_themes = {tag for tag, _ in summarize_risk_themes(fi_cases, limit=4)}
    combined = themes | fi_themes
    mapping = {
        "traffic_access": "Traffic and access note with junction capacity / visibility evidence.",
        "flooding_drainage": "Drainage strategy, SuDS detail, flood risk note, and discharge agreements where relevant.",
        "density_scale": "Explicit scale justification with local precedent comparisons and unit-mix rationale.",
        "design_layout": "Layout, overlooking/daylight, open-space and streetscape justification pack.",
        "land_use_policy": "Policy compliance matrix explaining zoning / land-use fit.",
        "residential_amenity": "Amenity impact note covering overlooking, separation, open space, and noise.",
        "premature_or_info_gap": "Front-load technical reports and servicing information to avoid premature refusal.",
    }
    for key, text in mapping.items():
        if key in combined:
            recommendations.append(f"- {text}")
    if not recommendations:
        recommendations.append("- Prepare a concise planning statement citing the closest granted comparables and addressing the main refusal themes found in similar cases.")
    return recommendations[:6]


def generate_strategy_pack(
    query: dict[str, object],
    selected_cases: pd.DataFrame,
    all_cases: pd.DataFrame,
) -> str:
    granted = selected_cases[selected_cases["decision_normalized"] == "GRANTED"]
    refused = selected_cases[selected_cases["decision_normalized"] == "REFUSED"]
    fi_cases = selected_cases[selected_cases["fi_count_num"] > 0]
    risk_themes = summarize_risk_themes(pd.concat([refused, fi_cases]).drop_duplicates("case_key"), limit=5)
    uploaded = query.get("uploaded_documents") or []

    header = [
        "# Planning Precedent Copilot Strategy Pack",
        "",
        "## 1. Project Summary",
        f"- Planning authority: {clean_text(query.get('PlanningAuthority')) or 'Not specified'}",
        f"- Application type: {clean_text(query.get('ApplicationType')) or 'Not specified'}",
        f"- Proposed units: {format_number(query.get('units_total_best'))}",
        f"- Proposed storeys: {format_number(query.get('max_storeys_best'))}",
        f"- Site area (ha): {format_number(query.get('site_area_ha_best'))}",
        f"- Site/location: {clean_text(query.get('DevelopmentAddress')) or 'Not specified'}",
        f"- Proposal description: {clean_text(query.get('DevelopmentDescription')) or 'Not specified'}",
    ]
    if uploaded:
        header.append(f"- Uploaded documents reviewed in intake: {', '.join(map(str, uploaded))}")

    support_lines = build_evidence_lines(granted, "supporting precedent", limit=5)
    refusal_lines = build_evidence_lines(refused, "refusal precedent", limit=5)
    fi_lines = build_evidence_lines(fi_cases, "FI precedent", limit=5)
    theme_lines = [f"- {tag}: {count} selected precedents" for tag, count in risk_themes] or [
        "- No single risk theme dominated the selected precedents."
    ]

    draft_notes: list[str] = [
        "## 2. Best Supporting Precedents",
        *(support_lines or ["- No granted precedents were pinned/selected. Use the highest-ranked grants before issuing this memo."]),
        "",
        "## 3. Most Relevant Refusal / FI Risks",
        *(refusal_lines or ["- No refusal precedents were pinned/selected."]),
        *(fi_lines or []),
        "",
        "## 4. Likely Risk Themes",
        *theme_lines,
        "",
        "## 5. Recommended Evidence Pack",
        *recommended_evidence_pack(refused, fi_cases),
        "",
        "## 6. Drafting Notes",
        "- Lead with the closest granted comparables in the same authority or at a similar scale.",
        "- Address recurring refusal/FI themes explicitly in the planning statement rather than assuming they are implicit in the drawings.",
        "- Where evidence is mixed or sparse, say so directly and avoid overclaiming precedent support.",
        "- Check every cited case manually before final issue to confirm the extracted refusal/FI text matches the original source files.",
        "",
        "## 7. Coverage Notes",
        *coverage_lines(selected_cases),
        "",
        "## 8. Precedent Appendix",
        *appendix_lines(selected_cases if not selected_cases.empty else all_cases.head(10)),
    ]
    return "\n".join(header + [""] + draft_notes).strip() + "\n"


def coverage_lines(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return ["- No selected precedents."]
    lines = []
    for _, row in df.head(10).iterrows():
        lines.append(f"- {citation_label(row)}: {clean_text(row.get('coverage_note'))}")
    return lines


def appendix_lines(df: pd.DataFrame) -> list[str]:
    lines: list[str] = []
    for _, row in df.iterrows():
        lines.extend(
            [
                f"### {citation_label(row)}",
                f"- Case key: {clean_text(row.get('case_key'))}",
                f"- Match reasons: {clean_text(row.get('match_reasons')) or 'See case metadata.'}",
                f"- Summary: {clean_text(row.get('case_summary'))}",
                f"- Refusal/FI evidence: {short_text(best_evidence_text(row), 300)}",
                f"- Source URL: {clean_text(row.get('source_url')) or 'Not available'}",
                "",
            ]
        )
    return lines


def best_evidence_text(row: pd.Series) -> str:
    refusal = clean_text(row.get("refusal_excerpt"))
    fi_text = clean_text(row.get("fi_excerpt"))
    description = clean_text(row.get("DevelopmentDescription"))
    for candidate in [refusal, fi_text, description]:
        if candidate and "[image]" not in candidate.lower():
            return candidate
    return refusal or fi_text or description or "No evidence text available."


def format_number(value: object) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "Not specified"
    if parsed.is_integer():
        return str(int(parsed))
    return f"{parsed:.2f}"
