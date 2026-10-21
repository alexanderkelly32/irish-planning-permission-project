"""v4 brief service: turn one scoring run into a working document.

Builds the Pre-Submission Brief pieces that make a score defensible and
multiplayer:

- risk_register: every material issue with concrete evidence, a severity,
  a confidence, a mitigation, an owner and a status. Severities are derived
  only from data the project actually holds (OPW flood layers, comparable
  outcomes, calibration history, refusal-theme frequencies, plan coverage,
  measured phrase effects). Where the model has no data, the row is
  severity "unverified" with confidence "unknown" and a confirm-action -
  the register never invents a severity the model cannot support.
- next_actions: the register distilled into owner-labelled actions.
- evidence_quality: data-freshness and coverage stamps for every input
  family, so confidence intervals feel earned rather than decorative.
- transit_stops_near: named public-transit stops within a radius of the site.
- load_model_changelog: the model's own changelog, shown to users.

All rows are model-attributed sensitivity statements, not guarantees.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
for scripts_dir in (ROOT / "05_policy" / "scripts", ROOT / "06_copilot" / "scripts"):
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

from v4_evidence_service import TAG_LABELS  # noqa: E402

REFUSAL_TAG_COUNTS = ROOT / "03_refusal" / "current" / "refusal_reason_tag_counts_master.csv"
TRANSIT_STOPS = ROOT / "07_context" / "current" / "national_transit_stops.parquet"
MODEL_CHANGELOG = ROOT / "05_policy" / "current" / "model_v4" / "CHANGELOG.json"

SEVERITIES = {"low", "medium", "high", "unverified"}
CONFIDENCES = {"high", "medium", "low", "unknown"}

OWNERS = {
    "planner": "Planning consultant",
    "client": "Client / developer",
    "engineer": "Engineer (Irish Water / drainage)",
    "transport": "Transport engineer",
    "ecologist": "Ecologist",
}


@lru_cache(maxsize=1)
def _tag_counts() -> dict[str, int]:
    frame = pd.read_csv(REFUSAL_TAG_COUNTS, low_memory=False)
    counts = {str(row["primary_tag"]): int(row["reason_count"]) for _, row in frame.iterrows()}
    return counts


def _tag_share(tag: str) -> tuple[int, float]:
    counts = _tag_counts()
    total = sum(counts.values())
    count = counts.get(tag, 0)
    return count, (count / total) if total else 0.0


@lru_cache(maxsize=1)
def _transit_state():
    stops = pd.read_parquet(TRANSIT_STOPS)
    tree = cKDTree(stops[["ITMEasting", "ITMNorthing"]].to_numpy())
    return stops, tree


def transit_stops_near(easting: float, northing: float, radius: float = 800.0, limit: int = 8) -> list[dict]:
    stops, tree = _transit_state()
    if easting is None or northing is None:
        return []
    indices = tree.query_ball_point([float(easting), float(northing)], radius)
    rows = []
    for index in indices[:limit]:
        rows.append({"stop_name": str(stops.iloc[index]["stop_name"]), "distance_m": round(float(
            np.hypot(float(stops.iloc[index]["ITMEasting"]) - float(easting),
                     float(stops.iloc[index]["ITMNorthing"]) - float(northing))), 0)})
    rows.sort(key=lambda r: r["distance_m"])
    return rows


def load_model_changelog() -> list[dict]:
    if not MODEL_CHANGELOG.exists():
        return []
    payload = json.loads(MODEL_CHANGELOG.read_text(encoding="utf-8"))
    return payload.get("entries", [])


def _row(category: str, issue: str, evidence: str, severity: str, confidence: str,
         mitigation: str, owner: str, status: str = "open", source: str = "") -> dict:
    if severity not in SEVERITIES:
        raise ValueError(f"severity {severity!r} not in {SEVERITIES}")
    if confidence not in CONFIDENCES:
        raise ValueError(f"confidence {confidence!r} not in {CONFIDENCES}")
    return {
        "category": category,
        "issue": issue,
        "evidence": evidence,
        "severity": severity,
        "confidence": confidence,
        "mitigation": mitigation,
        "owner": OWNERS[owner],
        "status": status,
        "source": source,
    }


def build_risk_register(review: dict) -> dict:
    """Assemble the risk register, next actions and evidence-quality stamps."""
    proposal = review["proposal"]
    score = review["score"]
    confidence_frame = review["confidence"]
    objectives = review.get("objectives") or {}
    site = review.get("site") or {}
    calibration = review.get("calibration")
    digest = review.get("digest") or {}

    rows: list[dict] = []
    authority = proposal["authority"]
    pinned = confidence_frame is None or not any(
        "council-centre" in text for text in confidence_frame.get("fallbacks", [])
    )
    coord_confidence = "high" if pinned else "medium"

    # --- flood (data-backed) ---
    flood = site.get("flood")
    if flood:
        if flood.get("flood_any"):
            count, share = _tag_share("flooding_drainage")
            rows.append(_row(
                "flood", "Site point falls in a mapped flood zone",
                f"OPW NCFHM/NIFM layers: fluvial hit={flood.get('fluvial_hit_any')}, coastal hit={flood.get('coastal_hit_any')}; "
                f"nearest fluvial zone {flood.get('nearest_fluvial_m'):.0f} m, nearest coastal {flood.get('nearest_coastal_m'):.0f} m. "
                f"Flooding/drainage is the recorded primary ground in {count} of {sum(_tag_counts().values())} extracted refusal cases ({share * 100:.0f}%).",
                "high" if (flood.get("fluvial_depth_max_m") or 0) > 0 else "medium",
                coord_confidence,
                "Commission a flood-risk assessment; demonstrate compliance with the Flood Risk Management Guidelines before submission.",
                "engineer",
                source="OPW flood layers (NCFHM/NIFM)",
            ))
        else:
            rows.append(_row(
                "flood", "No mapped flood-zone hit at the site point",
                f"Nearest fluvial zone {flood.get('nearest_fluvial_m'):.0f} m, nearest coastal zone {flood.get('nearest_coastal_m'):.0f} m.",
                "low", coord_confidence, "No action required; confirm site extents against the OPW viewer if the boundary is approximate.", "planner",
                source="OPW flood layers (NCFHM/NIFM)",
            ))

    # --- comparable precedent risk (data-backed) ---
    from v4_evidence_service import matched_precedents

    matched = matched_precedents(proposal, k=20)
    comp_summary = matched["summary"]
    precedents = matched["precedents"]
    top20_rate = comp_summary.get("refusal_rate")
    mean_match = comp_summary.get("mean_wording_match") or 0.0
    same_authority = comp_summary.get("same_council_count") or 0
    if top20_rate is not None and precedents:
        if top20_rate >= 0.5 and mean_match >= 0.1:
            severity, confidence = "high", "medium"
            mitigation = "Redesign toward the granted matched cases in the Precedents tab (density, form, wording); test variants in the Scenarios tab."
        elif top20_rate >= 0.35:
            severity, confidence = "medium", "medium"
            mitigation = "Review the refused matched cases' rationale in the Precedents tab and address the shared grounds before submission."
        else:
            severity, confidence = "low", "medium"
            mitigation = "No action required; the nearest matched cases are mostly granted."
        rows.append(_row(
            "precedents", "Matched recent precedent set",
            f"{comp_summary['refused_count']} of {comp_summary['retrieved']} closest matched applications refused "
            f"(refusal rate {top20_rate * 100:.0f}%; {same_authority} in {authority}; "
            f"median year {comp_summary.get('median_year')}; matched on wording, unit count, density, council and recency).",
            severity, confidence, mitigation, "planner",
            source=f"recent precedent matcher ({comp_summary.get('pool', 0)} decided applications in the 5-year window)",
        ))
    if comp_summary.get("retrieved", 20) < 20:
        rows.append(_row(
            "precedents", "Few recent matched precedents for this scheme",
            f"Only {comp_summary.get('retrieved')} matched applications in the 5-year window before submission; the score leans on council and type priors.",
            "unverified", "low",
            "Widen the evidence base (search the register manually for this typology) and treat the score as lower-confidence.",
            "planner",
            source="recent precedent matcher",
        ))

    # --- density / form (data-backed via historical bands) ---
    from explain_scenario_plain import rate_tables

    units = proposal.get("units")
    site_sqm = proposal.get("site_area_sqm")
    density = None
    if units and site_sqm and float(site_sqm) > 0:
        density = min(float(units) / (float(site_sqm) / 10000.0), 1000.0)
    if density is not None:
        band = "low (below 35 homes/ha)" if density < 35 else ("medium (35-50 homes/ha)" if density <= 50 else "high (above 50 homes/ha)")
        band_rate = (rate_tables().get("density_band_rates") or {}).get(band, {}).get("rate")
        evidence = f"Scheme density {density:.0f} homes/ha ({band})."
        if band_rate:
            evidence += f" Schemes in this band historically refuse at {band_rate * 100:.0f}%."
        severity = "medium" if density > 50 else ("medium" if density < 35 and (units or 0) >= 10 else "low")
        mitigation = "Check the density guidance for this site's settlement context and the comparable outcomes in the Precedents tab."
        rows.append(_row("density", f"Density ({density:.0f} homes/ha)", evidence, severity, "medium", mitigation, "planner",
                         source="historical density-band refusal rates"))

    # --- council track record (data-backed) ---
    council_rate = None
    for factor in digest.get("factors", []):
        if "has recently been refused" in factor.get("text", "") or "recently been refused" in factor.get("text", ""):
            import re as _re2

            match = _re2.search(r"refused (\d+)% of the time", factor["text"])
            if match:
                council_rate = int(match.group(1))
    if council_rate is not None:
        rows.append(_row(
            "council", f"{authority} recent refusal rate",
            f"Applications in {authority} have recently been refused {council_rate}% of the time (12-month window used by the model).",
            "medium" if council_rate >= 15 else "low", "high",
            "Pre-application consultation with the council is the standard mitigation for a stricter-than-average authority.",
            "planner",
            source="register history (authority 12-month window)",
        ))
    council_flags = {
        "Fingal County Council": "Fingal has refused 4 of its last 6 schemes of this size (historical rate 21%) - recent outcomes are worse than the model inputs suggest.",
        "Limerick County Council": "Limerick's recent large-scheme refusals (20%) are running above its historical rate (8.5%).",
        "Cork County Council": "Cork County decisions are flagged as a data-quality issue in the register.",
    }
    if authority in council_flags:
        rows.append(_row("council", f"{authority} watch flag", council_flags[authority], "medium", "medium",
                         "Treat this score as a lower bound and verify recent council decisions manually.", "planner",
                         source="council drift check"))

    # --- specialised scheme (data-backed prior) ---
    specialised = confidence_frame.get("specialised") if confidence_frame else None
    if specialised:
        rows.append(_row(
            "scheme_type", "Specialised scheme prior (senior living / care)",
            f"Specialised schemes historically refuse at {specialised['observed_rate_pre2024'] * 100:.0f}% (n={specialised['n']}, pre-2024); "
            f"general score {specialised['general_score'] * 100:.0f}% vs specialised-prior-adjusted {specialised['specialised_prior_adjusted'] * 100:.0f}%.",
            "medium", "medium",
            "Plan around the higher historical refusal rate; review specialised comparables in the Precedents tab.",
            "planner",
            source="specialised-scheme channel (2023 calibration window)",
        ))

    # --- plan coverage gaps (data-backed) ---
    obj_summary = (objectives or {}).get("summary")
    if obj_summary and obj_summary.get("open", 0) > 0:
        flagged = obj_summary.get("flagged", 0)
        rows.append(_row(
            "policy", "Development-plan objectives not addressed in the description",
            f"{obj_summary['addressed']} of {obj_summary['objective_count']} plan objectives are engaged by the description text; "
            f"{obj_summary['open']} are carried in the plan but not mentioned" + (f"; {flagged} site-flagged" if flagged else "") + ".",
            "medium" if obj_summary["open"] > obj_summary["objective_count"] * 0.7 else "low", "medium",
            "Close the obvious text gaps with true statements (open space, materials, drainage, parking) - see the Policy tab.",
            "planner",
            source=f"development plan objective layer ({obj_summary.get('plan_period')})",
        ))

    # --- inputs the model approximated (unverified by construction) ---
    fallbacks = (confidence_frame or {}).get("fallbacks", [])
    for fallback in fallbacks:
        if "Location" in fallback:
            rows.append(_row("data_quality", "Site coordinates approximated (council centre)",
                             fallback, "unverified", "low",
                             "Pin the site (Address/Eircode or ITM) before relying on flood, small-area and nearby-history evidence.", "planner",
                             source="user inputs"))
        elif "Floor area" in fallback:
            rows.append(_row("data_quality", "Floor area not provided",
                             fallback, "unverified", "unknown",
                             "Provide total floor area; density and unit-size ratios are currently imputed.", "client",
                             source="user inputs"))
        elif "Site area" in fallback:
            rows.append(_row("data_quality", "Site area not provided",
                             fallback, "unverified", "unknown",
                             "Provide the site area; density features are currently imputed.", "client",
                             source="user inputs"))
        elif "Description" in fallback:
            rows.append(_row("data_quality", "Thin description text",
                             fallback, "unverified", "low",
                             "Add the block type, storeys and materials to give the comparable matcher more signal.", "client",
                             source="user inputs"))

    # --- constraints: data-backed where national layers exist, else unverified ---
    constraints = (site or {}).get("constraints") or {}
    wwtp = constraints.get("wwtp")
    if wwtp:
        rows.append(_row(
            "constraints", "Wastewater capacity (unverified)",
            f"No servicing-capacity data is ingested; the nearest recorded EPA urban wastewater discharge point is "
            f"'{wwtp['name']}' ({wwtp['distance_m'] / 1000:.1f} km from the site). Capacity itself is not published nationally.",
            "unverified", "low",
            "Confirm available capacity with Irish Water via a pre-connection enquiry before submission.", "engineer",
            source="EPA urban waste-water emission points (distance check only)",
        ))
    else:
        rows.append(_row("constraints", "Wastewater / water services capacity",
                         "No servicing-capacity data is ingested by the model.",
                         "unverified", "unknown",
                         "Confirm capacity with Irish Water via a pre-connection enquiry before submission.", "engineer",
                         source="no data ingested - external confirmation required"))

    niah = constraints.get("niah")
    if niah:
        rows.append(_row(
            "constraints", f"Nearest NIAH-recorded structure: '{niah['name']}' ({niah['distance_m']:.0f} m)",
            f"NIAH record {niah['reg_no']} in {niah.get('town') or niah.get('county')}, rating {niah.get('rating') or 'n/a'}, "
            f"is {niah['distance_m']:.0f} m from the site point.",
            "medium" if niah["distance_m"] < 100 else "low",
            "medium",
            "NIAH is an advisory survey - confirm the council's Record of Protected Structures (RPS) and any ACA; a built-heritage assessment may be needed if the scheme affects a protected structure's setting.",
            "planner",
            source="NIAH national buildings dataset",
        ))
    else:
        rows.append(_row("constraints", "Protected structures / architectural conservation areas",
                         "No national protected-structure layer is ingested by the model.",
                         "unverified", "unknown",
                         "Check the site against NIAH and the council record of protected structures on MyPlan.", "planner",
                         source="no data ingested - external confirmation required"))

    natura = constraints.get("natura")
    if natura:
        rows.append(_row(
            "constraints", f"Natura 2000 site: {natura['sitename']} ({natura['type']})",
            f"The nearest Natura 2000 site is {natura['sitename']} ({natura['sitecode']}, {natura['type']}), "
            f"{natura['distance_m'] / 1000:.2f} km from the site point.",
            "medium" if natura["distance_m"] < 1000 else "low",
            "high",
            "If the scheme is within the site's zone of influence, screening for Appropriate Assessment is required before submission.",
            "ecologist",
            source="NPWS protected sites (SAC/SPA boundaries)",
        ))
    else:
        rows.append(_row("constraints", "European sites (Natura 2000) / ecology",
                         "No Natura 2000 or habitat layer is ingested by the model.",
                         "unverified", "unknown",
                         "Confirm screening distance to Natura 2000 sites with an ecologist (NPWS map viewer).", "ecologist",
                         source="no data ingested - external confirmation required"))

    traffic = constraints.get("traffic")
    if traffic:
        rows.append(_row(
            "constraints", f"Traffic: {traffic['within_2km']} counters within 2 km",
            f"{traffic['within_2km']} TII/TMU traffic counters sit within 2 km of the site; nearest: "
            f"'{traffic['nearest_name']}' at {traffic['nearest_distance_m']:.0f} m.",
            "low", "high",
            "Check the TII count-point data and road schedule near the site; commission a Traffic and Transport Assessment where the authority requires one.",
            "transport",
            source="TII/TMU traffic counter locations",
        ))
    else:
        rows.append(_row("constraints", "Traffic and road-network impact",
                         "TII count-point data on file has no usable geometry; the model does not read traffic data.",
                         "unverified", "unknown",
                         "Check TII count points and the road schedule near the site; commission a TIA where the authority requires one.", "transport",
                         source="no data ingested - external confirmation required"))

    zoning = (site or {}).get("zoning")
    if authority.lower() in {
        "dublin city council", "dun laoghaire rathdown county council",
        "south dublin county council", "fingal county council",
    }:
        if zoning and zoning.get("status") == "ok":
            rows.append(_row(
                "constraints", f"Zoning: {zoning.get('zone')}",
                f"Site point falls in zoning objective {zoning.get('zone')} ({zoning.get('plan_period')}): "
                f"{zoning.get('zone_description')}",
                "low", "high",
                "Confirm the zoning objective and its permitted uses from the development plan map before submission.",
                "planner",
                source=f"plan-versioned zoning layer ({zoning.get('plan_period')})",
            ))
        else:
            rows.append(_row(
                "constraints", "Zoning not resolved at the site point",
                zoning.get("note") if zoning else "The zoning lookup did not return a zone.",
                "unverified", "low",
                "Pin the site precisely or confirm the zone from the development plan map.",
                "planner",
                source="plan-versioned zoning layer",
            ))
    else:
        rows.append(_row("constraints", "Zoning compliance outside the four Dublin councils",
                         "Verified plan-versioned zoning layers exist only for the four Dublin councils.",
                         "unverified", "unknown",
                         "Confirm the zoning objective from the development plan map before submission.", "planner",
                         source="zoning layer coverage (four Dublin councils only)"))

    # --- strengths (positive, data-backed) ---
    strengths: list[str] = []
    if top20_rate is not None and top20_rate <= 0.2 and precedents:
        strengths.append(f"Matched precedent set mostly granted: {top20_rate * 100:.0f}% refusal rate across the {comp_summary.get('retrieved')} closest matched cases.")
    if flood and not flood.get("flood_any"):
        strengths.append(f"No mapped flood-zone hit at the site point (nearest fluvial zone {flood.get('nearest_fluvial_m'):.0f} m).")
    if calibration and calibration.get("n", 0) >= 500:
        strengths.append(f"Calibration band well populated: {calibration['n']:,} historical cases scored at this level.")
    easting = proposal.get("itm_easting")
    northing = proposal.get("itm_northing")
    if easting is not None and northing is not None:
        stops = transit_stops_near(float(easting), float(northing))
        if stops:
            names = ", ".join(f"{s['stop_name']} ({s['distance_m']:.0f} m)" for s in stops[:4])
            strengths.append(f"Public transport: {len(stops)} named stop(s) within 800 m - {names}.")

    next_actions: list[dict] = []
    for row in rows:
        if row["status"] != "open":
            continue
        if row["mitigation"].startswith("No action required"):
            continue
        next_actions.append({"owner": row["owner"], "severity": row["severity"], "issue": row["issue"],
                             "action": row["mitigation"]})
    order = {"high": 0, "medium": 1, "low": 2, "unverified": 3}
    next_actions.sort(key=lambda a: order[a["severity"]])

    evidence_quality = build_evidence_quality(review)
    return {"register": rows, "next_actions": next_actions, "strengths": strengths,
            "evidence_quality": evidence_quality}


def build_evidence_quality(review: dict) -> list[dict]:
    proposal = review["proposal"]
    confidence_frame = review.get("confidence") or {}
    from v4_evidence_service import matched_precedents

    matched = matched_precedents(proposal, k=20)
    matched_summary = matched["summary"]
    matched_rows = matched["precedents"]
    objectives = (review.get("objectives") or {}).get("summary")
    site = review.get("site") or {}
    calibration = review.get("calibration")

    stamps: list[dict] = []
    stamps.append({"input": "National register", "stamp": "Decisions through 2025-12-23; later decisions not yet ingested.",
                   "status": "frozen_snapshot"})
    if calibration:
        stamps.append({"input": "Calibration band", "stamp": f"{calibration['n']:,} historical cases in the {calibration['band']} band.",
                       "status": "ok"})
    stamps.append({
        "input": "Matched precedents",
        "stamp": f"{matched_summary.get('retrieved', 0)} matched from {matched_summary.get('pool', 0)} decided applications in the 5-year window; "
                 f"{matched_summary.get('same_council_count', 0)} in {proposal['authority']}; "
                 f"median year {matched_summary.get('median_year')}.",
        "status": "ok" if matched_summary.get("retrieved", 0) >= 10 else "thin",
    })
    refused_with_reason = sum(1 for c in matched_rows if c["outcome"] == "Refused" and c.get("rationale"))
    refused = sum(1 for c in matched_rows if c["outcome"] == "Refused")
    stamps.append({"input": "Refusal rationale", "stamp": f"Inspector rationale extracted for {refused_with_reason} of {refused} refused matched cases.",
                   "status": "ok" if refused == 0 or refused_with_reason >= refused * 0.5 else "partial"})
    if objectives:
        stamps.append({"input": "Development plan", "stamp": f"{objectives['plan_period']} plan in force for submission year {proposal['submission_year']}",
                       "status": "fallback" if objectives.get("fallback_used") else "ok"})
    fallback_text = " ".join((confidence_frame or {}).get("fallbacks", []))
    if "council-centre" in fallback_text:
        stamps.append({"input": "Site coordinates", "stamp": "Council-centre approximation - site evidence is approximate until pinned.",
                       "status": "approximate"})
    else:
        stamps.append({"input": "Site coordinates", "stamp": "Site coordinates provided.", "status": "ok"})
    if (proposal.get("floor_area_sqm") or 0) > 0:
        stamps.append({"input": "Floor area", "stamp": "Provided - density and unit-size ratios computed.", "status": "ok"})
    else:
        stamps.append({"input": "Floor area", "stamp": "Missing - density ratios imputed.", "status": "approximate"})
    stamps.append({"input": "Census small-area", "stamp": "Census 2022 small areas (latest release).", "status": "ok"})
    stamps.append({"input": "Flood layers", "stamp": "OPW NCFHM / NIFM layers at the site point.", "status": "ok"})
    constraints = (site or {}).get("constraints") or {}
    loaded = [key for key in ("niah", "natura", "wwtp", "traffic") if constraints.get(key)]
    if loaded:
        labels = {"niah": "NIAH buildings", "natura": "Natura 2000", "wwtp": "EPA wastewater points", "traffic": "traffic counters"}
        stamps.append({"input": "Constraint layers", "stamp": "Loaded: " + ", ".join(labels[k] for k in loaded) + ".",
                       "status": "ok"})
    else:
        stamps.append({"input": "Constraint layers", "stamp": "National constraint layers not built - run 07_context/scripts/build_constraint_reference.py.",
                       "status": "unverified"})
    if site.get("zoning") and site["zoning"].get("status") == "ok":
        stamps.append({"input": "Zoning", "stamp": f"{site['zoning']['zone']} ({site['zoning']['plan_period']}).", "status": "ok"})
    else:
        stamps.append({"input": "Zoning", "stamp": "No verified zoning layer for this authority - confirm from the plan map.",
                       "status": "unverified"})
    return stamps
