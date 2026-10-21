"""v4 evidence service: show the machinery behind a v4-full score.

Powers the Pre-Submission Review product's evidence tabs:
  - comparable_details: the 20 nearest frozen-reference comparables with
    application reference, dates, council, units, outcome and, where
    extracted, the inspector refusal rationale (display-only; never a
    model input)
  - plan_objectives: the development plan in force with objective codes,
    titles, themes and an addressed/open/flag status
  - site_context: flood exposure, small-area census context, nearby recent
    decisions (for the map and the local track record)
  - confidence_frame: calibration band CI, fallbacks used, specialised-scheme
    prior disclosure and "few close precedents" naming

Everything here is evidence presentation around the frozen v4-full model.
"""
from __future__ import annotations

import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
for scripts_dir in (ROOT / "05_policy" / "scripts", ROOT / "06_copilot" / "scripts"):
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

from model_feature_builder import _bucket_for, _load_state, nearest_comparables  # noqa: E402
from build_dublin_submission_model import strip_text_leakage_clues  # noqa: E402
from build_specialised_channel import is_specialised  # noqa: E402
from build_v3_policy_features_challenger import THEME_ORDER, theme_of  # noqa: E402

COMPARABLE_METADATA = ROOT / "05_policy" / "current" / "model_v4" / "comparable_metadata.joblib"
RECENT_PRECEDENTS = ROOT / "05_policy" / "current" / "model_v4" / "recent_precedents_reference.joblib"
OBJECTIVE_LAYER = ROOT / "05_policy" / "current" / "objective_code_layer.csv"
SPECIALISED_ADJUSTMENT = ROOT / "05_policy" / "current" / "model_v4" / "specialised_adjustment.joblib"
CALIBRATION_BINS = ROOT / "05_policy" / "current" / "raw_planning_8020_calibration.json"
GE10_SCORED = ROOT / "05_policy" / "current" / "ge10_scored_2024_25.csv"

CONSTRAINT_NIAH = ROOT / "07_context" / "current" / "constraint_niah.parquet"
CONSTRAINT_NATURA = ROOT / "07_context" / "current" / "constraint_natura.parquet"
CONSTRAINT_WWTP = ROOT / "07_context" / "current" / "constraint_wwtp.parquet"
CONSTRAINT_TRAFFIC = ROOT / "07_context" / "current" / "constraint_traffic.parquet"

_ITM_TO_WGS84 = Transformer.from_crs("EPSG:2157", "EPSG:4326", always_xy=True)
_WGS84_TO_ITM = Transformer.from_crs("EPSG:4326", "EPSG:2157", always_xy=True)

THEME_LABELS = {
    "housing": "Housing & supply",
    "design": "Design & quality",
    "zoning": "Zoning & land use",
    "rural": "Rural development",
    "transport": "Transport & movement",
    "economic": "Economic development",
    "environment": "Environment & climate",
    "flood_water": "Flood & water",
    "heritage": "Heritage & archaeology",
    "community": "Community & social",
    "core": "Core strategy",
    "other": "Other",
}

TAG_LABELS = {
    "density_scale": "Density / scale out of character",
    "design_layout": "Design & layout concerns",
    "design_amenity": "Design & amenity concerns",
    "land_use_policy": "Land-use policy conflict",
    "traffic_access": "Traffic & access",
    "flood_drainage": "Flooding & drainage",
    "flooding_drainage": "Flooding & drainage",
    "water_wastewater": "Water & wastewater capacity",
    "services_capacity": "Services capacity",
    "open_space": "Open space & recreation",
    "zoning_land_use": "Zoning / land-use conflict",
    "heritage": "Heritage impact",
    "heritage_archaeology": "Heritage & archaeology",
    "environment_ecology": "Environmental / ecological",
    "ecology_trees": "Ecology & trees",
    "parking": "Parking provision",
    "housing_mix": "Housing mix / unit types",
    "residential_amenity": "Residential amenity",
    "premature_or_info_gap": "Premature / information gap",
    "other": "Other grounds",
}


@lru_cache(maxsize=1)
def _metadata_state() -> dict:
    meta = joblib.load(COMPARABLE_METADATA)
    objectives = pd.read_csv(OBJECTIVE_LAYER, low_memory=False)
    objectives["council"] = objectives["council"].replace("Limerick City and County Council", "Limerick County Council")
    objectives["start"] = pd.to_numeric(objectives["plan_period"].str.split("-").str[0], errors="coerce")
    objectives["end"] = pd.to_numeric(objectives["plan_period"].str.split("-").str[1], errors="coerce")
    objectives["theme"] = objectives["objective_code"].map(theme_of)
    specialised = joblib.load(SPECIALISED_ADJUSTMENT)
    calibration = json.loads(CALIBRATION_BINS.read_text(encoding="utf-8"))
    return {
        "meta": meta,
        "objectives": objectives,
        "specialised": specialised,
        "calibration": calibration,
    }


def _wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _short(value: str, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


def _sentence(value: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    text = re.sub(r"={2,}\s*PAGE\s*\d+\s*={2,}", " ", text)
    first = re.split(r"(?<=[.;])\s+", text)[0]
    first = re.sub(r"^(?:it is )?(?:an )?objective (?:of [^:]{0,80})?(?:to )?|^(?:policy )", "", first, flags=re.IGNORECASE)
    return first if len(first) <= limit else text[: limit - 1].rstrip() + "\u2026"


def _objective_title(code: str, context: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(context or "")).strip()
    text = re.sub(r"={2,}\s*PAGE\s*\d+\s*={2,}", " ", text)
    if not text:
        return ""
    if len(str(code)) >= 3:
        match = re.search(re.escape(str(code)), text, flags=re.IGNORECASE)
        if match:
            text = text[match.start():]
    return _sentence(text, limit)


@lru_cache(maxsize=1)
def _recent_state() -> dict:
    return joblib.load(RECENT_PRECEDENTS)


@lru_cache(maxsize=1)
def _constraint_state() -> dict:
    """Constraint lookup tables: NIAH buildings, Natura 2000 sites, EPA
    wastewater discharge points, TII traffic counters."""
    state: dict = {"niah": None, "natura": None, "wwtp": None, "traffic": None}
    if CONSTRAINT_NIAH.exists():
        niah = pd.read_parquet(CONSTRAINT_NIAH)
        state["niah"] = {"frame": niah,
                         "tree": cKDTree(niah[["itm_easting", "itm_northing"]].to_numpy())}
    if CONSTRAINT_NATURA.exists():
        import geopandas as gpd

        state["natura"] = gpd.read_parquet(CONSTRAINT_NATURA)
    if CONSTRAINT_WWTP.exists():
        wwtp = pd.read_parquet(CONSTRAINT_WWTP)
        state["wwtp"] = {"frame": wwtp,
                         "tree": cKDTree(wwtp[["itm_easting", "itm_northing"]].to_numpy())}
    if CONSTRAINT_TRAFFIC.exists():
        traffic = pd.read_parquet(CONSTRAINT_TRAFFIC)
        state["traffic"] = {"frame": traffic,
                            "tree": cKDTree(traffic[["itm_easting", "itm_northing"]].to_numpy())}
    return state


def constraints_for(easting: float, northing: float) -> dict:
    """Nearest/within checks for the four national constraint layers."""
    state = _constraint_state()
    out: dict = {"niah": None, "natura": None, "wwtp": None, "traffic": None}
    if easting is None or northing is None:
        return out
    easting, northing = float(easting), float(northing)

    if state["niah"] is not None:
        distance, index = state["niah"]["tree"].query([easting, northing], k=1)
        row = state["niah"]["frame"].iloc[int(index)]
        out["niah"] = {
            "name": str(row["name"]),
            "reg_no": str(row["reg_no"]),
            "town": str(row["town"]) if pd.notna(row["town"]) else None,
            "county": str(row["county"]) if pd.notna(row["county"]) else None,
            "rating": str(row["rating"]) if pd.notna(row["rating"]) else None,
            "distance_m": round(float(distance), 0),
        }

    if state["natura"] is not None:
        try:
            from shapely.geometry import Point

            point = Point(easting, northing)
            distances = state["natura"].geometry.distance(point)
            min_index = int(distances.idxmin())
            nearest = state["natura"].iloc[min_index]
            out["natura"] = {
                "sitename": str(nearest["sitename"]),
                "sitecode": str(nearest["sitecode"]),
                "type": str(nearest["type"]),
                "distance_m": round(float(distances.min()), 0),
            }
        except Exception:
            out["natura"] = None

    if state["wwtp"] is not None:
        distance, index = state["wwtp"]["tree"].query([easting, northing], k=1)
        row = state["wwtp"]["frame"].iloc[int(index)]
        out["wwtp"] = {
            "name": str(row["name"]),
            "emission_id": str(row["emission_id"]),
            "distance_m": round(float(distance), 0),
        }

    if state["traffic"] is not None:
        indices = state["traffic"]["tree"].query_ball_point([easting, northing], 2000.0)
        within = state["traffic"]["frame"].iloc[indices]
        distance, index = state["traffic"]["tree"].query([easting, northing], k=1)
        nearest = state["traffic"]["frame"].iloc[int(index)]
        out["traffic"] = {
            "within_2km": int(len(within)),
            "nearest_name": str(nearest["name"]),
            "nearest_distance_m": round(float(distance), 0),
        }
    return out


def _wording_match_label(similarity: float) -> str:
    if similarity >= 0.35:
        return "Close"
    if similarity >= 0.2:
        return "Partial"
    return "Distant"


def matched_precedents(proposal: dict, k: int = 20) -> dict:
    """The 20 closest past applications using ALL the data we hold.

    Matched on description wording (TF-IDF cosine), unit count, site density,
    same-council and recency, restricted to the last 5 years before the
    submission year. Undecided applications are excluded. This is the
    display/precedent engine; the frozen scoring path is unchanged.
    """
    state = _load_state()
    recent = _recent_state()
    description = strip_text_leakage_clues(proposal.get("description") or "") or ""
    units = proposal.get("units")
    units = float(units) if units is not None else np.nan
    bucket = proposal.get("application_type") or _bucket_for(description, units)
    submission_year = int(proposal.get("submission_year") or 2026)
    authority = str(proposal.get("authority") or "")

    bucket_data = recent["buckets"].get(bucket)
    if bucket_data is None or not description:
        return {"bucket": bucket, "summary": {"retrieved": 0}, "precedents": []}

    query_vec = state["comparable"]["vectorizer"].transform([description])
    query_unit = np.log1p(units) if not pd.isna(units) and units > 0 else np.nan
    query_site = proposal.get("site_area_sqm")
    query_site = float(query_site) if query_site else np.nan
    query_density = np.log(units / query_site) if (not pd.isna(units) and not pd.isna(query_site) and units > 0 and query_site > 0) else np.nan

    matrix = bucket_data["matrix"]
    from sklearn.metrics.pairwise import cosine_similarity

    text_sims = np.asarray(cosine_similarity(query_vec, matrix)).ravel()
    years = bucket_data["received_year"]
    authorities = bucket_data["authority"]
    unit_rows = bucket_data["units"]
    site_rows = bucket_data["site_sqm"]

    scores = np.zeros(len(text_sims))
    reasons: dict[int, list[str]] = {}
    for index in range(len(text_sims)):
        reasons[index] = []
    age = submission_year - years
    window_ok = (years <= submission_year) & (years >= submission_year - 5)
    if not window_ok.any():
        return {"bucket": bucket,
                "summary": {"retrieved": 0, "pool": 0, "note": "No decided applications in the 5-year window before the submission year."},
                "precedents": []}

    recency = np.exp(-np.clip(age, 0, 5) / 2.5)
    council_boost = (authorities == authority).astype(float)

    unit_close = np.full(len(text_sims), 0.5)
    if not np.isnan(query_unit):
        row_units = unit_rows.astype(float)
        known = ~np.isnan(row_units) & (row_units > 0)
        log_u = np.log1p(np.where(known, row_units, 1.0))
        unit_close = np.where(known, np.exp(-0.6 * np.abs(log_u - query_unit)), 0.5)
    density_close = np.full(len(text_sims), 0.5)
    if not np.isnan(query_density):
        known_d = ~np.isnan(site_rows) & (site_rows > 0) & ~np.isnan(unit_rows) & (unit_rows > 0)
        log_d = np.log(np.where(known_d, unit_rows / np.where(known_d, site_rows, 1.0), 1.0))
        density_close = np.where(known_d, np.exp(-0.6 * np.abs(log_d - query_density)), 0.5)

    combined = (0.45 * text_sims + 0.20 * unit_close + 0.10 * density_close + 0.15 * recency + 0.10 * council_boost) * window_ok
    order = np.argsort(-combined)
    selected = []
    year_list = []
    for index in order:
        if len(selected) >= k:
            break
        if not window_ok[index] or combined[index] <= 0:
            continue
        target = bucket_data["target"][index]
        if np.isnan(target):
            continue
        year_list.append(int(years[index]))
        match_reasons = []
        if text_sims[index] >= 0.35:
            match_reasons.append("close wording")
        elif text_sims[index] >= 0.2:
            match_reasons.append("similar wording")
        if council_boost[index]:
            match_reasons.append("same council")
        if unit_close[index] >= 0.85:
            match_reasons.append("similar unit count")
        if density_close[index] >= 0.85:
            match_reasons.append("similar density")
        match_reasons.append(f"received {int(years[index])}")
        row_units_val = bucket_data["units"][index]
        selected.append({
            "rank": len(selected) + 1,
            "case_key": str(bucket_data["case_key"][index]),
            "application_number": str(bucket_data["application_number"][index]),
            "council": str(authorities[index]),
            "received_date": str(bucket_data["received_date"][index]),
            "decision_date": str(bucket_data["decision_date"][index]) or None,
            "decision": str(bucket_data["decision"][index]),
            "units": float(row_units_val) if pd.notna(row_units_val) else None,
            "outcome": "Refused" if int(target) == 1 else "Granted",
            "wording_match": round(float(text_sims[index]), 3),
            "wording_label": _wording_match_label(float(text_sims[index])),
            "match_score": round(float(combined[index]), 3),
            "match_reasons": match_reasons,
            "description": _short(str(bucket_data["description"][index]), 200),
            "rationale": _short(str(bucket_data["reasons_joined"][index]), 280) or None,
            "rationale_tag": str(bucket_data["top_primary_tag"][index]) or None,
            "rationale_label": TAG_LABELS.get(str(bucket_data["top_primary_tag"][index]), str(bucket_data["top_primary_tag"][index])) if bucket_data["top_primary_tag"][index] else None,
        })

    targets = np.array([1 if r["outcome"] == "Refused" else 0 for r in selected])
    same_council = sum(1 for r in selected if r["council"] == authority)
    pool_in_bucket = int(window_ok.sum()) if window_ok.any() else 0
    pool_same_council = int(((authorities == authority) & window_ok).sum())
    summary = {
        "bucket": bucket,
        "window": f"{submission_year - 5}-{submission_year}",
        "retrieved": len(selected),
        "pool": pool_in_bucket,
        "pool_same_council": pool_same_council,
        "refusal_rate": round(float(targets.mean()), 3) if len(targets) else None,
        "refused_count": int(targets.sum()),
        "granted_count": int(len(targets) - targets.sum()),
        "same_council_count": same_council,
        "mean_wording_match": round(float(np.mean([r["wording_match"] for r in selected])), 3) if selected else None,
        "median_year": int(np.median(year_list)) if year_list else None,
        "units_range": (min([r["units"] for r in selected if r["units"] is not None], default=None),
                        max([r["units"] for r in selected if r["units"] is not None], default=None)),
    }
    return {"bucket": bucket, "summary": summary, "precedents": selected}


def comparable_details(proposal: dict, k: int = 20) -> dict:
    """Top-k frozen-reference comparables with full display metadata."""
    meta = _metadata_state()["meta"]
    nearest = nearest_comparables(proposal, k=k)
    bucket = nearest["bucket"]
    bucket_meta = meta["buckets"].get(bucket)
    rows: list[dict] = []
    if bucket_meta is not None:
        for position, (index, similarity) in enumerate(zip(nearest["indices"], nearest["similarities"])):
            target = int(bucket_meta["target"][index])
            units = bucket_meta["units"][index]
            units_value = float(units) if pd.notna(units) else None
            reason = _short(bucket_meta["reasons_joined"][index], 280)
            tag = str(bucket_meta["top_primary_tag"][index])
            rows.append({
                "rank": position + 1,
                "case_key": str(bucket_meta["case_key"][index]),
                "application_number": str(bucket_meta["application_number"][index]),
                "council": str(bucket_meta["authority"][index]),
                "received_date": str(bucket_meta["received_date"][index]),
                "decision_date": str(bucket_meta["decision_date"][index]) or None,
                "decision": str(bucket_meta["decision"][index]),
                "units": units_value,
                "outcome": "Refused" if target == 1 else "Granted",
                "similarity": round(float(similarity), 3),
                "description": _short(bucket_meta["description"][index], 200),
                "rationale": reason or None,
                "rationale_tag": tag or None,
                "rationale_label": TAG_LABELS.get(tag, tag) if tag else None,
            })
    targets = np.array([1 if r["outcome"] == "Refused" else 0 for r in rows])
    sims = np.array([r["similarity"] for r in rows])
    refused_sim = np.where(targets == 1, sims, np.nan)
    granted_sim = np.where(targets == 0, sims, np.nan)
    summary = {
        "bucket": bucket,
        "available_in_bucket": nearest["available"],
        "retrieved": len(rows),
        "refusal_rate": round(float(targets.mean()), 3) if len(targets) else None,
        "refused_count": int(targets.sum()),
        "granted_count": int(len(targets) - targets.sum()),
        "mean_similarity": round(float(sims.mean()), 3) if len(sims) else None,
        "max_refused_similarity": round(float(np.nanmax(refused_sim)), 3) if np.isfinite(refused_sim).any() else None,
        "max_granted_similarity": round(float(np.nanmax(granted_sim)), 3) if np.isfinite(granted_sim).any() else None,
    }
    return {"bucket": bucket, "summary": summary, "comparables": rows}


def _description_tokens(description: str) -> set[str]:
    words = re.findall(r"[a-z\u00e9\u00ed\u00fa\u00e1\u00f3]+", (description or "").lower())
    tokens = {w for w in words if len(w) >= 4}
    bigrams = set()
    for pair in zip(words, words[1:]):
        bigrams.add(f"{pair[0]} {pair[1]}")
    return tokens | bigrams


def plan_objectives(authority: str, year: int, description: str = "", flood_any: bool = False) -> dict:
    """Development plan in force: objective list with statuses and a plan summary."""
    state = _metadata_state()
    objectives = state["objectives"]
    council_rows = objectives[objectives["council"] == authority]
    plan = None
    period = None
    fallback = False
    in_force = council_rows[
        (council_rows["start"] <= year) & (council_rows["end"] >= year)
    ].dropna(subset=["start", "end"])
    if len(in_force):
        latest_start = in_force["start"].max()
        plan = in_force[in_force["start"] == latest_start]
        period = str(plan["plan_period"].mode().iloc[0]) if len(plan) else None
    else:
        fallback = True
        if len(council_rows):
            best_start = council_rows.dropna(subset=["start"])["start"].max()
            plan = council_rows[council_rows["start"] == best_start]
            period = str(plan["plan_period"].mode().iloc[0]) if len(plan) else None
    if plan is None or len(plan) == 0:
        return {
            "status": "no_plan_on_file",
            "note": "No development-plan objective extraction is on file for this authority.",
            "objectives": [],
            "summary": None,
        }
    original_len = len(plan)
    description_tokens = _description_tokens(description) if description else set()
    plan = plan[~plan["objective_code"].astype(str).str.fullmatch(r"\d+")]
    dropped = int(original_len - len(plan))
    rows: list[dict] = []
    for _, row in plan.sort_values("mentions", ascending=False).iterrows():
        context = str(row["context"] or "")
        title = _objective_title(str(row["objective_code"]), context)
        tokens = _description_tokens(title)
        theme = str(row["theme"])
        if description_tokens and tokens & description_tokens:
            status = "addressed"
        elif theme == "flood_water" and flood_any:
            status = "flag"
        else:
            status = "open"
        rows.append({
            "code": str(row["objective_code"]),
            "title": title,
            "theme": theme,
            "theme_label": THEME_LABELS.get(theme, theme),
            "mentions": int(row["mentions"]) if pd.notna(row["mentions"]) else 0,
            "status": status,
            "plan_period": str(row["plan_period"]),
        })
    summary = {
        "council": authority,
        "plan_period": period,
        "plan_document": str(plan["plan_document"].mode().iloc[0]) if len(plan) else "",
        "objective_count": int(plan["objective_code"].nunique()),
        "mention_count": int(plan["mentions"].fillna(0).sum()),
        "addressed": sum(1 for r in rows if r["status"] == "addressed"),
        "open": sum(1 for r in rows if r["status"] == "open"),
        "flagged": sum(1 for r in rows if r["status"] == "flag"),
        "fallback_used": fallback,
        "dropped_junk_codes": dropped,
    }
    return {"status": "ok", "summary": summary, "objectives": rows}


def _to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    lon, lat = _ITM_TO_WGS84.transform(easting, northing)
    return float(lon), float(lat)


def boundary_evidence(proposal: dict, polygon_wgs84: list) -> dict | None:
    """Boundary-draw ingestion: site area, density and constraints inside a
    user-drawn polygon (WGS84 coordinates). The polygon does not feed the
    frozen scoring path - it supplies the site area and site-context counts."""
    try:
        from shapely.geometry import Point, Polygon
    except Exception:
        return None
    if not polygon_wgs84 or len(polygon_wgs84) < 3:
        return None
    ring = polygon_wgs84 if isinstance(polygon_wgs84[0], (list, tuple)) else polygon_wgs84[0]
    try:
        coords = [tuple(map(float, point)) for point in ring if len(point) >= 2]
    except (TypeError, ValueError):
        return None
    if len(coords) < 3:
        return None
    try:
        itm_ring = [_WGS84_TO_ITM.transform(lon, lat) for lon, lat in coords]
        polygon = Polygon(itm_ring)
        area_sqm = float(polygon.area)
    except Exception:
        return None
    if not polygon.is_valid or area_sqm <= 0:
        return None
    units = proposal.get("units")
    units = float(units) if units is not None else 0.0
    area_ha = area_sqm / 10000.0
    density = units / area_ha if area_ha > 0 else None

    state = _constraint_state()
    inside = {}

    def _points_inside(frame: pd.DataFrame) -> pd.Series:
        points = [Point(float(x), float(y)) for x, y in zip(frame["itm_easting"], frame["itm_northing"])]
        return pd.Series([polygon.contains(point) for point in points], index=frame.index)

    if state["niah"] is not None:
        frame = state["niah"]["frame"]
        mask = _points_inside(frame)
        niah_in = frame[mask]
        inside["niah_inside"] = [
            {"name": str(r["name"]), "reg_no": str(r["reg_no"])} for _, r in niah_in.head(10).iterrows()
        ]
        inside["niah_count"] = int(len(niah_in))
    if state["natura"] is not None:
        natura = state["natura"]
        intersects = natura[natura.geometry.intersects(polygon)]
        inside["natura_inside"] = [
            {"sitename": str(r["sitename"]), "type": str(r["type"])} for _, r in intersects.head(10).iterrows()
        ]
        inside["natura_count"] = int(len(intersects))
    if state["wwtp"] is not None:
        frame = state["wwtp"]["frame"]
        inside["wwtp_inside_count"] = int(_points_inside(frame).sum())
    if state["traffic"] is not None:
        frame = state["traffic"]["frame"]
        inside["traffic_inside_count"] = int(_points_inside(frame).sum())

    centroid = polygon.centroid
    centroid_wgs84 = _to_wgs84(centroid.x, centroid.y)
    return {
        "area_sqm": round(area_sqm, 1),
        "area_ha": round(area_ha, 3),
        "density_units_per_ha": round(density, 1) if density is not None else None,
        "units": units,
        "centroid": {"lon": centroid_wgs84[0], "lat": centroid_wgs84[1],
                     "itm_easting": round(centroid.x, 1), "itm_northing": round(centroid.y, 1)},
        "inside": inside,
    }


def site_context(proposal: dict) -> dict:
    """Flood, small-area census, zoning (Dublin) and nearby recent decisions."""
    state = _load_state()
    easting = proposal.get("itm_easting")
    northing = proposal.get("itm_northing")
    out: dict = {"coordinates": {"itm_easting": easting, "itm_northing": northing}, "flood": None, "small_area": None, "nearby": None, "zoning": None, "constraints": None}
    if easting is None or northing is None:
        return out
    easting, northing = float(easting), float(northing)

    dist, idx = state["sa_tree"].query([easting, northing], k=1)
    sa = state["sa_ref"].iloc[int(idx)]
    out["small_area"] = {
        "pop_density_per_sqkm": round(float(sa["pop_density_per_sqkm"]), 0),
        "is_urban": bool(int(sa["is_urban"])),
        "urban_area_name": str(sa.get("SA_URBAN_AREA_NAME", "")) or None,
        "nuts3": str(sa.get("SA_NUTS3_NAME", "")) or None,
        "owner_share": round(float(sa["owner_share"]) * 100, 0),
        "private_rent_share": round(float(sa["private_rent_share"]) * 100, 0),
        "la_rent_share": round(float(sa["la_rent_share"]) * 100, 0),
        "septic_share": round(float(sa["septic_share"]) * 100, 0),
        "cars_per_hh": round(float(sa["cars_per_hh"]), 2),
        "no_car_share": round(float(sa["no_car_share"]) * 100, 0),
    }

    fdist, fidx = state["flood_tree"].query([easting, northing], k=1)
    flood_row = state["flood"].iloc[int(fidx)]
    out["flood"] = {
        "nearest_reference_point_m": round(float(fdist), 0),
        "fluvial_hit_any": bool(flood_row["fluvial_hit_any"]),
        "coastal_hit_any": bool(flood_row["coastal_hit_any"]),
        "flood_any": bool(flood_row["fluvial_hit_any"]) or bool(flood_row["coastal_hit_any"]),
        "fluvial_depth_max_m": float(flood_row["fluvial_depth_max_m"]) if pd.notna(flood_row["fluvial_depth_max_m"]) else None,
        "coastal_depth_max_m": float(flood_row["coastal_depth_max_m"]) if pd.notna(flood_row["coastal_depth_max_m"]) else None,
        "nearest_fluvial_m": float(flood_row["fluvial_min_dist_m"]) if pd.notna(flood_row["fluvial_min_dist_m"]) else None,
        "nearest_coastal_m": float(flood_row["coastal_min_dist_m"]) if pd.notna(flood_row["coastal_min_dist_m"]) else None,
    }

    hist = state["history"]
    latest = pd.to_datetime(hist["received_date_dt"]).max()
    horizon = latest - pd.DateOffset(months=24)
    for radius, tag in ((1000.0, "within_1km"), (3000.0, "within_3km")):
        near = hist.iloc[state["hist_tree"].query_ball_point([easting, northing], radius)]
        recent = near[near["received_date_dt"] >= horizon]
        out.setdefault("nearby_rates", {})[tag] = {
            "recent_24m_count": int(len(recent)),
            "recent_24m_refusal_rate": round(float(recent["target_refused"].fillna(0).mean()), 3) if len(recent) else None,
            "all_time_count": int(len(near)),
        }
    points = hist.iloc[state["hist_tree"].query_ball_point([easting, northing], 3000.0)]
    points = points[points["received_date_dt"] >= horizon].sort_values("received_date_dt", ascending=False).head(400)
    out["nearby"] = {
        "points": [
            {
                "case_key": str(row["case_key"]),
                "lat": _to_wgs84(float(row["ITMEasting"]), float(row["ITMNorthing"]))[1],
                "lon": _to_wgs84(float(row["ITMEasting"]), float(row["ITMNorthing"]))[0],
                "outcome": "Refused" if int(row["target_refused"]) == 1 else "Granted",
                "received": str(pd.to_datetime(row["received_date_dt"]).date()),
            }
            for _, row in points.iterrows()
        ],
        "cap_note": "Showing up to 400 most recent decisions within 3km (last 24 months)" if len(points) >= 400 else f"All decisions within 3km, last 24 months: {len(points)}",
    }
    try:
        out["constraints"] = constraints_for(easting, northing)
    except Exception:
        out["constraints"] = None

    authority = str(proposal.get("authority") or "")
    if authority.lower() in {
        "dublin city council", "dun laoghaire rathdown county council",
        "south dublin county council", "fingal county council",
    }:
        try:
            from site_evidence_service import CURRENT_PLAN_LAYERS, lookup_zoning, load_current_zoning_layers

            layers = load_current_zoning_layers()
            zoning = lookup_zoning({"planning_authority": authority, "itm_easting": easting, "itm_northing": northing}, layers=layers)
            if zoning.get("status") == "matched":
                out["zoning"] = {
                    "status": "ok",
                    "zone": zoning.get("zone_code"),
                    "zone_description": zoning.get("zone_description"),
                    "plan_period": zoning.get("plan_period"),
                    "source_note": zoning.get("source_note"),
                }
            elif zoning.get("status") == "no_polygon_match":
                plan_key = CURRENT_PLAN_LAYERS.get(authority.strip().lower())
                nearest_note = None
                try:
                    layer = layers.get(plan_key)
                    if layer is not None and len(layer):
                        from shapely.geometry import Point

                        point = Point(_ITM_TO_WGS84.transform(easting, northing))
                        distances = layer.geometry.distance(point)
                        nearest_index = int(distances.idxmin())
                        nearest_zone = str(layer.iloc[nearest_index].get("zone_code") or "")
                        nearest_km = float(distances.min()) * 111.0
                        nearest_note = f"Closest mapped zone: {nearest_zone} (roughly {nearest_km:.1f} km away)."
                except Exception:
                    nearest_note = None
                out["zoning"] = {
                    "status": "outside_coverage",
                    "note": "The site point falls outside the mapped zoning polygons for this authority. "
                            "Pin the site precisely or check the plan map."
                            + (f" {nearest_note}" if nearest_note else ""),
                }
            else:
                out["zoning"] = {"status": zoning.get("status"), "note": zoning.get("note")}
        except Exception as exc:  # geopandas/shapely failure must not break scoring UI
            out["zoning"] = {"status": "lookup_failed", "note": str(type(exc).__name__)}

    site_lon, site_lat = _to_wgs84(easting, northing)
    out["map"] = {"lat": site_lat, "lon": site_lon, "flood_any": out["flood"]["flood_any"]}
    return out


def _specialised_risk(risk: float) -> dict | None:
    state = _metadata_state()
    specialised = state["specialised"]
    if not specialised:
        return None
    shift = float(specialised.get("logit_shift", 0.0))
    logit = math.log(max(risk, 1e-6) / (1 - max(risk, 1e-6)))
    adjusted = 1.0 / (1.0 + math.exp(-(logit + shift)))
    return {
        "general_score": risk,
        "specialised_prior_adjusted": round(min(0.99, adjusted), 3),
        "observed_rate_pre2024": round(float(specialised.get("observed_rate", 0.0)), 3),
        "n": int(specialised.get("n", 0)),
        "note": (
            f"Specialised schemes (senior living / care / retirement) historically refuse at "
            f"{float(specialised.get('observed_rate', 0)) * 100:.0f}% (n={int(specialised.get('n', 0))}), above what "
            f"the general score suggests. Both numbers are shown; the adjusted figure is a prior, not a replacement score."
        ),
    }


def council_check(easting: float, northing: float, authority: str, radius: float = 5000.0) -> dict | None:
    """Check that the chosen coordinates sit inside the chosen council area.

    Uses the distribution of historical applications near the point: if the
    chosen authority is essentially absent among nearby applications while
    another council dominates, the site is probably in the wrong council.
    """
    if easting is None or northing is None:
        return None
    state = _load_state()
    hist = state["history"]
    near = hist.iloc[state["hist_tree"].query_ball_point([float(easting), float(northing)], radius)]
    recent = near[pd.to_datetime(near["received_date_dt"]).dt.year >= 2015]
    pool = recent if len(recent) >= 15 else near
    if len(pool) < 10:
        return {"status": "insufficient_data",
                "note": "Too few historical applications near these coordinates to verify the council."}
    shares = pool["PlanningAuthority"].value_counts(normalize=True)
    top = str(shares.index[0])
    chosen_share = float(shares.get(authority, 0.0))
    if authority == top:
        return {"status": "ok", "dominant": authority, "share": chosen_share,
                "note": f"{authority} is the dominant council among {len(pool)} nearby applications ({chosen_share * 100:.0f}%)."}
    if chosen_share < 0.05 and float(shares.iloc[0]) > 0.5:
        return {"status": "mismatch", "dominant": top, "dominant_share": float(shares.iloc[0]),
                "chosen_share": chosen_share,
                "note": f"These coordinates look like they are in {top} ({shares.iloc[0] * 100:.0f}% of {len(pool)} nearby applications), not {authority} ({chosen_share * 100:.0f}%). Check the council or the site."}
    return {"status": "ok", "dominant": top, "share": chosen_share,
            "note": f"Nearby applications are mostly {top}; {authority} accounts for {chosen_share * 100:.0f}% - worth a manual check."}


@lru_cache(maxsize=1)
def _ge10_scores() -> pd.DataFrame:
    return pd.read_csv(GE10_SCORED, low_memory=False)


def ge10_position(probability: float, units: float | None) -> dict | None:
    """Where this score sits among the 464 large schemes decided 2024-2025."""
    if not units or units < 10:
        return None
    frame = _ge10_scores()
    risks = frame["model_risk"].astype(float)
    percentile = float((risks < probability).mean() * 100)
    decile = min(int(percentile // 10) + 1, 10)
    band = frame.copy()
    band["decile"] = (risks.rank(method="first", ascending=True) - 1) // (len(risks) // 10) + 1
    band["decile"] = band["decile"].clip(1, 10)
    refused = band["outcome"].astype(str).str.upper().str.contains("REFUS")
    decile_rate = float(refused[band["decile"] == decile].mean()) if len(band[band["decile"] == decile]) else None
    suffix = "th" if 10 <= int(percentile) % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(int(percentile) % 10, "th")
    return {
        "n": int(len(risks)),
        "percentile": round(percentile, 0),
        "decile": decile,
        "decile_refusal_rate": round(decile_rate, 3) if decile_rate is not None else None,
        "median": round(float(risks.median()), 3),
        "note": (
            f"Among {len(risks)} large schemes (10+ units) decided in 2024-2025, this score sits at the "
            f"{percentile:.0f}{suffix} percentile. Schemes in that decile were refused "
            f"{decile_rate * 100:.0f}% of the time." if decile_rate is not None else ""
        ),
    }


def calibration_band(probability: float) -> dict | None:
    bins = _metadata_state()["calibration"]["E8020"]["calibrated_isotonic"]["reliability_bins"]
    for entry in bins:
        lo = entry["lo"]
        hi = lo + 0.1
        if lo <= probability < hi and entry["n"] >= 30:
            ci_lo, ci_hi = _wilson_ci(entry["obs"], entry["n"])
            return {
                "band": f"{int(lo * 100)}-{int(hi * 100)}%",
                "n": int(entry["n"]),
                "observed_rate": round(float(entry["obs"]), 3),
                "ci_lo": round(ci_lo, 3),
                "ci_hi": round(ci_hi, 3),
            }
    return None


def confidence_frame(proposal: dict, centre_coords: tuple[float, float] | None = None) -> dict:
    """Fallbacks used, precedent strength, calibration band and specialised prior."""
    notes: list[str] = []
    fallbacks: list[str] = []
    easting = proposal.get("itm_easting")
    northing = proposal.get("itm_northing")
    if centre_coords is not None and easting is not None and northing is not None:
        if abs(float(easting) - centre_coords[0]) < 1 and abs(float(northing) - centre_coords[1]) < 1:
            fallbacks.append("Location: council-centre coordinates were used (not the exact site). Nearby-history and flood lookups are therefore approximate.")
    if (proposal.get("floor_area_sqm") or 0) <= 0:
        fallbacks.append("Floor area: not provided, so density and unit-size ratios are partially imputed.")
    if (proposal.get("site_area_sqm") or 0) <= 0:
        fallbacks.append("Site area: not provided, so density features are imputed.")
    if len((proposal.get("description") or "").split()) < 20:
        fallbacks.append("Description: short text gives the comparable matcher less to work with - add the block type, storeys and materials if known.")

    comparable = matched_precedents(proposal, k=20)
    summary = comparable["summary"]
    mean_match = summary.get("mean_wording_match")
    if summary["retrieved"] < 20:
        notes.append(
            f"Few recent precedents: only {summary['retrieved']} matched applications in the 5-year window before submission "
            f"(from {summary.get('pool', 0)} in this scheme type). The score leans more on council and type priors here, so it is less certain than usual."
        )
    else:
        notes.append(
            f"Precedents: {summary['retrieved']} matched past applications ({summary.get('same_council_count', 0)} in "
            f"{proposal.get('authority')}, median year {summary.get('median_year')}) - {summary['refused_count']} refused and "
            f"{summary['granted_count']} granted."
        )

    description = str(proposal.get("description") or "").lower()
    specialised = None
    if is_specialised(description):
        from model_feature_builder import score_proposal

        risk = score_proposal(proposal)["refusal_probability"]
        specialised = _specialised_risk(risk)

    return {"confidence_notes": notes, "fallbacks": fallbacks, "comparable_summary": summary, "specialised": specialised}


def evidence_snapshot(proposal: dict) -> dict:
    """Compact, comparable evidence digest for portfolio monitoring and alerts."""
    comparable = matched_precedents(proposal, k=20)
    site = site_context(proposal)
    rates = site.get("nearby_rates", {})
    import datetime as _dt

    return {
        "scored_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "comp_top20": {
            "refusal_rate": comparable["summary"].get("refusal_rate"),
            "mean_similarity": comparable["summary"].get("mean_wording_match"),
            "retrieved": comparable["summary"].get("retrieved"),
        },
        "nearby_1km": rates.get("within_1km"),
        "nearby_3km": rates.get("within_3km"),
        "flood_any": site.get("flood", {}).get("flood_any"),
    }
