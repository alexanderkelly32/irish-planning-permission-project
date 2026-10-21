"""Verified site-context evidence: zoning, hard policy standards, coverage-gated."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
from pyproj import Transformer

from precedent_copilot_logic import clean_text, short_text

ROOT = Path(__file__).resolve().parents[2]
ZONING_DIR = ROOT / "05_policy" / "documents" / "zoning" / "normalized"
VERIFIED_RULES_PATH = ROOT / "05_policy" / "current" / "verified_hard_policy_rules.csv"
POLICY_CHUNKS_PATH = ROOT / "05_policy" / "current" / "policy_chunks.csv"

CURRENT_PLAN_LAYERS = {
    "dublin city council": "dublin_city_council__2022_2028",
    "dun laoghaire rathdown county council": "dun_laoghaire_rathdown_county_council__2022_2028",
    "south dublin county council": "south_dublin_county_council__2022_2028",
    "fingal county council": "fingal_county_council__2023_2029",
}
CURRENT_PLAN_PERIODS = {
    "dublin city council": "2022-2028",
    "dun laoghaire rathdown county council": "2022-2028",
    "south dublin county council": "2022-2028",
    "fingal county council": "2023-2029",
}
_ITM_TO_WGS84 = Transformer.from_crs("EPSG:2157", "EPSG:4326", always_xy=True)
ZONE_CODE_PATTERN = re.compile(r"\bZ(\d{1,2})\b")
DCC_OPEN_SPACE_ZONES = {
    "0.10": {"Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z8", "Z10", "Z14"},
    "0.25": {"Z12", "Z15"},
}


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _site_wgs84(site: dict[str, Any]) -> tuple[float, float] | None:
    easting = _number(site.get("itm_easting"))
    northing = _number(site.get("itm_northing"))
    if easting is not None and northing is not None:
        lon, lat = _ITM_TO_WGS84.transform(easting, northing)
        return float(lon), float(lat)
    lat = _number(site.get("latitude"))
    lon = _number(site.get("longitude"))
    if lat is not None and lon is not None:
        return float(lon), float(lat)
    return None


def load_current_zoning_layers() -> dict[str, Any]:
    """Load the current plan-period zoning layers for the four Dublin councils."""
    import geopandas as gpd

    layers: dict[str, Any] = {}
    for plan_key in sorted(set(CURRENT_PLAN_LAYERS.values())):
        path = ZONING_DIR / f"{plan_key}.geojson"
        if not path.exists():
            continue
        layers[plan_key] = gpd.read_file(path)
    return layers


def lookup_zoning(site: dict[str, Any], layers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Point-in-polygon zoning for the current plan period only."""
    authority = clean_text(site.get("planning_authority"))
    plan_key = CURRENT_PLAN_LAYERS.get(authority.strip().lower())
    if plan_key is None:
        return {
            "status": "no_verified_coverage",
            "note": (
                "No plan-versioned zoning layer is currently verified for this authority. "
                "Zoning coverage is limited to the four Dublin councils and their current plans."
            ),
        }
    layers = layers or {}
    layer = layers.get(plan_key)
    if layer is None or len(layer) == 0:
        return {
            "status": "layer_unavailable",
            "note": f"The current {CURRENT_PLAN_PERIODS[authority.strip().lower()]} zoning layer could not be loaded.",
        }
    coordinates = _site_wgs84(site)
    if coordinates is None:
        return {
            "status": "coordinates_missing",
            "note": "Site coordinates (ITM or latitude/longitude) are required for a zoning lookup.",
        }
    from shapely.geometry import Point

    point = Point(coordinates)
    candidates = list(layer.sindex.query(point, predicate="intersects"))
    for index in candidates:
        row = layer.iloc[index]
        if row.geometry.contains(point):
            return {
                "status": "matched",
                "authority": authority,
                "plan_period": CURRENT_PLAN_PERIODS[authority.strip().lower()],
                "plan_key": plan_key,
                "zone_code": clean_text(row.get("zone_code")),
                "zone_description": clean_text(row.get("zone_description")),
                "source_note": f"Current {CURRENT_PLAN_PERIODS[authority.strip().lower()]} development plan zoning layer.",
            }
    return {
        "status": "no_polygon_match",
        "note": (
            f"Site coordinates fall outside the current {CURRENT_PLAN_PERIODS[authority.strip().lower()]} "
            "zoning layer polygons for this authority."
        ),
    }


def load_verified_rules(path: str | Path | None = None) -> pd.DataFrame:
    source = Path(path) if path else VERIFIED_RULES_PATH
    if not source.exists():
        return pd.DataFrame()
    return pd.read_csv(source, low_memory=False)


def load_policy_chunks(path: str | Path | None = None) -> pd.DataFrame:
    source = Path(path) if path else POLICY_CHUNKS_PATH
    if not source.exists():
        return pd.DataFrame()
    return pd.read_csv(source, low_memory=False)


def current_authority_rules(rules: pd.DataFrame, authority: str) -> pd.DataFrame:
    """Verified rules for the authority's current plan period only."""
    if rules.empty:
        return rules.iloc[0:0].copy()
    plan_key = CURRENT_PLAN_LAYERS.get(clean_text(authority).strip().lower())
    if plan_key is None:
        return rules.iloc[0:0].copy()
    return rules[
        (rules["plan_key"] == plan_key)
        & (rules.get("review_status", "approved").fillna("approved").astype(str).str.strip().str.lower() == "approved")
    ].copy()


def _zone_tokens(zone_code: object) -> set[str]:
    matches = ZONE_CODE_PATTERN.findall(str(zone_code or ""))
    return {f"Z{match}" for match in matches}


def compare_open_space_ratio(site: dict[str, Any], scheme: dict[str, Any], rules: pd.DataFrame, zone_code: str = "") -> dict[str, Any]:
    """Compare scheme open space against the verified current-plan ratio, when the zone applies."""
    authority = clean_text(site.get("planning_authority"))
    plan_key = CURRENT_PLAN_LAYERS.get(authority.strip().lower())
    if plan_key != "dublin_city_council__2022_2028":
        return {"status": "not_applicable_authority"}
    applicable = rules[rules["rule_family"] == "open_space_min_site_ratio"]
    if applicable.empty:
        return {"status": "no_verified_rule"}
    zone_tokens = _zone_tokens(zone_code)
    threshold_row = None
    for threshold, zones in DCC_OPEN_SPACE_ZONES.items():
        if zone_tokens & zones:
            matching = applicable[applicable["threshold_value"].astype(float) == float(threshold)]
            if not matching.empty:
                threshold_row = matching.iloc[0]
                break
    if threshold_row is None:
        return {
            "status": "zone_not_covered",
            "note": "The verified open-space ratio applies only to specified residential zones; this zone is not covered.",
        }
    site_area = _number(scheme.get("site_area_sqm"))
    communal = _number(scheme.get("communal_open_space_sqm"))
    private = _number(scheme.get("private_open_space_sqm"))
    if site_area is None or site_area <= 0 or (communal is None and private is None):
        return {
            "status": "not_comparable_missing_fields",
            "threshold": float(threshold_row["threshold_value"]),
            "threshold_unit": clean_text(threshold_row.get("threshold_unit")),
            "source_document_label": clean_text(threshold_row.get("source_document_label")),
            "source_page_range": clean_text(threshold_row.get("source_page_range")),
            "note": "Comparison needs site area and open-space fields; fill them to run the check.",
        }
    open_space = (communal or 0.0) + (private or 0.0)
    observed_ratio = open_space / site_area
    threshold = float(threshold_row["threshold_value"])
    return {
        "status": "compared",
        "threshold": threshold,
        "threshold_unit": clean_text(threshold_row.get("threshold_unit")),
        "observed_ratio": round(observed_ratio, 4),
        "site_area_sqm": site_area,
        "open_space_sqm": open_space,
        "meets_threshold": bool(observed_ratio >= threshold),
        "zone_code": zone_code,
        "source_document_label": clean_text(threshold_row.get("source_document_label")),
        "source_page_range": clean_text(threshold_row.get("source_page_range")),
        "verbatim_quote": short_text(threshold_row.get("verbatim_quote"), 240),
        "note": (
            "This compares the scheme's open-space ratio with a verified current-plan standard. "
            "It is a policy comparison, not a probability or refusal prediction."
        ),
    }


def _standards_table(rules: pd.DataFrame, rule_family: str) -> list[dict[str, Any]]:
    rows = rules[rules["rule_family"] == rule_family].sort_values("threshold_value")
    standards: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        standards.append({
            "subject_type": clean_text(row.get("subject_type")),
            "threshold_kind": clean_text(row.get("threshold_kind")),
            "threshold_value": _number(row.get("threshold_value")),
            "threshold_unit": clean_text(row.get("threshold_unit")),
        })
    return standards


def policy_standards_for_scheme(site: dict[str, Any], scheme: dict[str, Any], rules: pd.DataFrame, zone_code: str = "") -> dict[str, Any]:
    """Verified current-plan standards relevant to the scheme, with comparability status."""
    authority = clean_text(site.get("planning_authority"))
    current = current_authority_rules(rules, authority)
    if current.empty:
        return {
            "status": "no_verified_rules",
            "note": "No verified hard-policy rules exist for this authority's current plan.",
        }
    families = set(current["rule_family"])
    output: dict[str, Any] = {
        "status": "available",
        "authority": authority,
        "plan_period": CURRENT_PLAN_PERIODS.get(authority.strip().lower(), ""),
        "apartment_min_floor_area": {
            "standards": _standards_table(current, "apartment_min_floor_area"),
            "comparison_status": "not_comparable_missing_fields",
            "comparison_note": (
                "Comparison needs per-type apartment floor areas, which the structured form "
                "does not yet capture; unit_mix text is not parsed."
            ),
        } if "apartment_min_floor_area" in families else None,
        "communal_amenity_min_per_unit": {
            "standards": _standards_table(current, "communal_amenity_min_per_unit"),
            "comparison_status": "not_comparable_missing_fields",
            "comparison_note": (
                "Comparison needs unit-type counts plus communal open space; the structured form "
                "does not yet capture unit-type counts."
            ),
        } if "communal_amenity_min_per_unit" in families else None,
        "open_space_min_site_ratio": compare_open_space_ratio(site, scheme, current, zone_code),
        "source_document_label": clean_text(current.iloc[0].get("source_document_label")),
        "note": (
            "Standards are manually verified extracts from the current development plan with "
            "document and page citations. Where fields are missing the standard is shown "
            "without a comparison; no missing-field gap should be read as compliance."
        ),
    }
    return output


def retrieve_policy_passages(
    chunks: pd.DataFrame,
    authority: str,
    terms: list[str] | tuple[str, ...] | set[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Keyword-retrieval over current-plan chunks with document/page citations."""
    if chunks.empty or not terms:
        return []
    current = chunks[
        chunks["authority"].fillna("").astype(str).str.strip().str.lower()
        == clean_text(authority).strip().lower()
    ]
    plan_period = CURRENT_PLAN_PERIODS.get(clean_text(authority).strip().lower())
    if plan_period:
        start, end = plan_period.split("-")
        current = current[
            (pd.to_numeric(current.get("plan_start_year"), errors="coerce") == float(start))
            & (pd.to_numeric(current.get("plan_end_year"), errors="coerce") == float(end))
        ]
    if current.empty:
        return []
    pattern = re.compile("|".join(re.escape(clean_text(term).lower()) for term in terms if clean_text(term)), re.IGNORECASE)
    scored = current.copy()
    scored["_score"] = scored["chunk_text"].fillna("").astype(str).map(
        lambda text: len(pattern.findall(text.lower())) if pattern.pattern else 0
    )
    scored = scored[scored["_score"] > 0].sort_values("_score", ascending=False)
    passages: list[dict[str, Any]] = []
    seen_sections: set[str] = set()
    for _, row in scored.iterrows():
        section = clean_text(row.get("section_title"))
        if section in seen_sections:
            continue
        seen_sections.add(section)
        passages.append({
            "section_title": section,
            "page_range": clean_text(row.get("page_range")),
            "document_label": clean_text(row.get("document_label")),
            "excerpt": short_text(row.get("chunk_text"), 320),
        })
        if len(passages) >= limit:
            break
    return passages


def summarize_site_evidence(
    site: dict[str, Any],
    scheme: dict[str, Any],
    zoning_layers: dict[str, Any] | None = None,
    rules: pd.DataFrame | None = None,
    policy_chunks: pd.DataFrame | None = None,
    passage_terms: list[str] | None = None,
) -> dict[str, Any]:
    """Coverage-gated site evidence for display; never a prediction input."""
    zoning = lookup_zoning(site, zoning_layers)
    rules = rules if rules is not None else pd.DataFrame()
    policy = policy_standards_for_scheme(site, scheme, rules, zone_code=zoning.get("zone_code", ""))
    passages = []
    if policy_chunks is not None and passage_terms:
        passages = retrieve_policy_passages(policy_chunks, clean_text(site.get("planning_authority")), passage_terms)
    return {
        "zoning": zoning,
        "policy_standards": policy,
        "policy_passages": passages,
        "flood": {
            "status": "no_site_level_coverage",
            "note": (
                "Site-level flood-extent coverage is not currently available for new sites. "
                "Flood/drainage themes for comparable refused cases appear in the refusal-theme evidence."
            ),
        },
        "caveat": (
            "Zoning and policy standards are verified extracts for the authority's current plan "
            "period only. Unavailable coverage is stated explicitly and is never assumed."
        ),
    }
