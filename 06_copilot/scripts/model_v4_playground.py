"""Planning Intelligence - Pre-Submission Review (model v4-full).

A submission-time planning-risk product for Irish residential schemes:
score a proposal, see the full evidence machinery behind the number
(20 named comparables with inspector rationale, the development-plan
crosswalk, the site/flood/nearby-decisions map, wording analysis),
download a branded PDF review, and keep a portfolio of schemes with
monitoring alerts.

Run:
  $env:PYTHONPATH = (Resolve-Path .vendor).Path + ";" + (Resolve-Path 05_policy\scripts).Path + ";" + (Resolve-Path 06_copilot\scripts).Path
  streamlit run 06_copilot\scripts\model_v4_playground.py

Every scored event records model version, inputs and timestamp in the
append-only score log (06_copilot/current/portfolio.sqlite). Nothing is
overwritten. All deltas are model-attributed sensitivity statements -
not guarantees and not planning advice.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
for scripts_dir in (ROOT / "05_policy" / "scripts", ROOT / "06_copilot" / "scripts"):
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

from explain_proposal import explain_proposal  # noqa: E402
from explain_scenario_plain import plain_language  # noqa: E402
from model_feature_builder import score_proposal  # noqa: E402
from description_checks import check_vocabulary, cross_check_numbers  # noqa: E402
import v4_evidence_service as evidence  # noqa: E402
import v4_portfolio_store as portfolio  # noqa: E402
import v4_wording_service as wording  # noqa: E402
import v4_brief_service as brief  # noqa: E402
from v4_report import build_report_pdf  # noqa: E402

MODEL_PATH = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"
MANIFEST_PATH = ROOT / "05_policy" / "current" / "model_v4" / "manifest.json"

DESCRIPTION_TEMPLATES = {
    "Thin": {
        "description": "construction of 12 apartments",
        "units": 12, "site_area_sqm": 4000.0, "floor_area_sqm": 2400.0,
    },
    "Standard": {
        "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
        "units": 12, "site_area_sqm": 4000.0, "floor_area_sqm": 2400.0,
    },
    "Detailed (mixed 47-unit)": {
        "description": (
            "Construction of a residential development comprising 47 No. dwellings in total, consisting of "
            "11 No. two-bedroom two storey houses and 10 No. three-bedroom three storey houses (21 No. houses in total) "
            "including rear private open spaces; 13 No. one bedroom apartments and 13 No. two-bedroom apartments "
            "(26 No. three storey duplex apartments) with balconies or terraces; provision of surface car parking spaces "
            "and bicycle parking; vehicular access from the adjoining road; landscaped open space and boundary treatments; "
            "connection to the public water main, foul and surface water drainage; and all associated site development works."
        ),
        "units": 47, "site_area_sqm": 19900.0, "floor_area_sqm": 6110.0,
    },
    "SHD exemplar (314-unit, real)": {
        "description": (
            "STRATEGIC HOUSING DEVELOPMENT - the demolition of an existing dwelling and agricultural buildings on the "
            "subject site and the construction of a residential development of 314 no. dwellings as follows: (a) 208 no. "
            "houses comprising; 14 no. 2 bedroom houses, 172 no. 3 bedroom houses, and 22 no. 4 bedroom houses (Houses "
            "provided with two car parking spaces and solar panels all house types 2 storey); (b) 78 no. apartments "
            "(38 no. 1 bedroom, 40 no. 2 bedroom with balconies or terraces) in 4 no. 4 storey apartment buildings with "
            "basement car parking; (c) a creche (c. 610sqm) and a retail unit (c. 169sqm); provision of landscaped "
            "open space, boundary treatments, connection to public services, and all associated site development works."
        ),
        "units": 314, "site_area_sqm": 64000.0, "floor_area_sqm": 32000.0,
    },
}

AUTHORITIES = sorted([
    "Carlow County Council", "Cavan County Council", "Clare County Council", "Cork City Council",
    "Cork County Council", "Donegal County Council", "Dublin City Council",
    "Dun Laoghaire Rathdown County Council", "Fingal County Council", "Galway City Council",
    "Galway County Council", "Kerry County Council", "Kildare County Council", "Kilkenny County Council",
    "Laois County Council", "Leitrim County Council", "Limerick County Council", "Longford County Council",
    "Louth County Council", "Mayo County Council", "Meath County Council", "Monaghan County Council",
    "Offaly County Council", "Roscommon County Council", "Sligo County Council", "South Dublin County Council",
    "Tipperary County Council", "Waterford City and County Council", "Westmeath County Council",
    "Wexford County Council", "Wicklow County Council",
])

RISK_COLOURS = {"LOW": "#1e8449", "MEDIUM": "#b47800", "HIGH": "#c0392b"}


@st.cache_resource
def load_artifact():
    return joblib.load(MODEL_PATH)


@st.cache_resource
def load_council_centres() -> dict[str, tuple[float, float]]:
    history = pd.read_parquet(ROOT / "07_context" / "current" / "history_reference.parquet")
    centres = {}
    for authority, group in history.groupby("PlanningAuthority"):
        centres[str(authority)] = (float(group["ITMEasting"].median()), float(group["ITMNorthing"].median()))
    return centres


def init_state() -> None:
    defaults = {
        "authority": "Dun Laoghaire Rathdown County Council",
        "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
        "units": 12,
        "site_area_sqm": 4000.0,
        "floor_area_sqm": 2400.0,
        "submission_year": 2026,
        "project_name": "",
        "nav": "Review a scheme",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def proposal_from_state() -> dict:
    return {
        "name": st.session_state.get("project_name") or "",
        "authority": st.session_state.authority,
        "description": st.session_state.description,
        "units": st.session_state.units,
        "site_area_sqm": st.session_state.site_area_sqm,
        "floor_area_sqm": st.session_state.floor_area_sqm,
        "itm_easting": st.session_state.get("itm_easting"),
        "itm_northing": st.session_state.get("itm_northing"),
        "submission_year": st.session_state.submission_year,
    }


def set_state_from_proposal(proposal: dict) -> None:
    st.session_state["authority"] = proposal["authority"]
    st.session_state["description"] = proposal["description"]
    st.session_state["units"] = int(proposal["units"] or 0)
    st.session_state["site_area_sqm"] = float(proposal["site_area_sqm"] or 0)
    st.session_state["floor_area_sqm"] = float(proposal["floor_area_sqm"] or 0)
    st.session_state["itm_easting"] = proposal.get("itm_easting")
    st.session_state["itm_northing"] = proposal.get("itm_northing")
    st.session_state["submission_year"] = int(proposal.get("submission_year") or 2026)
    st.session_state["project_name"] = proposal["name"]


def render_scheme_form(centres: dict[str, tuple[float, float]]) -> dict:
    with st.expander("Scheme details", expanded=not st.session_state.get("review")):
        col_name, col_auth, col_year = st.columns([2, 2, 1])
        with col_name:
            st.text_input("Project name (for your portfolio)", key="project_name")
        with col_auth:
            st.selectbox("Planning authority", AUTHORITIES, key="authority")
        with col_year:
            st.number_input("Submission year", min_value=2024, max_value=2030, key="submission_year")

        location = st.radio("Location", ["Use council centre", "Address / Eircode", "Custom ITM coordinates"], index=0)
        itm_easting, itm_northing = None, None
        if location == "Use council centre":
            easting, northing = centres[st.session_state.authority]
            itm_easting, itm_northing = float(easting), float(northing)
            st.caption(f"Using the council-centre coordinates ({easting:.0f}, {northing:.0f}) - site-specific flood, "
                       f"small-area and nearby-history lookups will be approximate until you pin the site.")
        elif location == "Address / Eircode":
            address_query = st.text_input("Address or Eircode (e.g. 'D02 X285' or 'Main Street, Howth')", value="")
            if st.button("Look up coordinates", key="geocode"):
                if not address_query.strip():
                    st.warning("Enter an address or Eircode first.")
                else:
                    try:
                        import re as _re

                        import requests
                        from pyproj import Transformer

                        looks_like_eircode = bool(_re.fullmatch(r"[A-Za-z0-9]{3}\s?[A-Za-z0-9]{4}", address_query.strip()))
                        query = address_query.strip()
                        if not looks_like_eircode:
                            query = f"{query}, Ireland"
                        response = requests.get(
                            "https://nominatim.openstreetmap.org/search",
                            params={"q": query, "format": "json", "limit": 3, "bounded": 1,
                                    "viewbox": "-11.2,51.2,-5.5,55.6", "accept-language": "en"},
                            headers={"User-Agent": "planning-risk-review/1.0 (local personal use)"},
                            timeout=20,
                        )
                        results = response.json() or []
                        ireland_results = [
                            r for r in results
                            if -11.2 <= float(r.get("lat", 0)) <= 55.6 and -11.2 <= float(r.get("lon", 0)) <= -5.4
                            and ("ireland" in str(r.get("display_name", "")).lower() or "ireland" in str(r.get("address", {})).lower())
                        ]
                        if ireland_results:
                            hit = ireland_results[0]
                            transformer = Transformer.from_crs("EPSG:4326", "EPSG:2157", always_xy=True)
                            easting, northing = transformer.transform(float(hit["lon"]), float(hit["lat"]))
                            st.session_state.geo_easting = float(easting)
                            st.session_state.geo_northing = float(northing)
                            st.session_state.geo_label = str(hit.get("display_name", ""))
                            st.success(f"Resolved: {st.session_state.geo_label}")
                        else:
                            st.error("No Irish match found for that address - try adding the town or county.")
                    except Exception as exc:
                        st.error(f"Lookup failed: {type(exc).__name__}")
            if st.session_state.get("geo_easting") is not None:
                itm_easting = float(st.session_state.geo_easting)
                itm_northing = float(st.session_state.geo_northing)
                st.caption(f"Using ({itm_easting:.0f}, {itm_northing:.0f}) from lookup")
        else:
            c1, c2 = st.columns(2)
            with c1:
                itm_easting = float(st.number_input("ITM easting", value=722000, step=100))
            with c2:
                itm_northing = float(st.number_input("ITM northing", value=726500, step=100))

        template_key = st.selectbox("Example descriptions", ["Custom", *DESCRIPTION_TEMPLATES.keys()], index=0)
        if template_key != "Custom" and st.session_state.get("active_template") != template_key:
            template = DESCRIPTION_TEMPLATES[template_key]
            st.session_state["active_template"] = template_key
            st.session_state["_tpl_description"] = template["description"]
            st.session_state["_tpl_units"] = template["units"]
            st.session_state["_tpl_site"] = template["site_area_sqm"]
            st.session_state["_tpl_floor"] = template["floor_area_sqm"]

        st.text_area(
            "Development description",
            key="description",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.number_input("Residential units", min_value=0, max_value=5000, key="units")
        with c2:
            st.number_input("Site area (m2)", min_value=0.0, max_value=10_000_000.0, step=100.0, key="site_area_sqm")
        with c3:
            st.number_input("Total floor area (m2, 0 if unknown)", min_value=0.0, max_value=10_000_000.0, step=100.0, key="floor_area_sqm")

    proposal = proposal_from_state()
    proposal["itm_easting"] = itm_easting
    proposal["itm_northing"] = itm_northing

    if location != "Use council centre" and itm_easting is not None:
        check = evidence.council_check(itm_easting, itm_northing, st.session_state.authority)
        if check and check.get("status") == "mismatch":
            st.error(f":red[**Council mismatch**:] {check['note']}")
        elif check and check.get("status") == "ok" and check.get("dominant") != st.session_state.authority:
            st.warning(check["note"])
        elif check and check.get("status") == "ok":
            st.caption(f"Council check: {check['note']}")

    st.markdown("**Pre-flight checks**")
    number_warnings = cross_check_numbers(proposal["description"], int(proposal["units"] or 0),
                                          float(proposal["site_area_sqm"] or 0), float(proposal["floor_area_sqm"] or 0))
    if number_warnings:
        for warning in number_warnings:
            st.warning(warning)
    else:
        st.success("Numbers in the description agree with the fields.")
    artifact = load_artifact()
    try:
        vocab = artifact["ranking_model"].named_steps["preprocessor"].named_transformers_["txt"].vocabulary_
    except (KeyError, AttributeError):
        vocab = set()
    flagged_words = check_vocabulary(proposal["description"], set(vocab) if vocab else set())
    if flagged_words:
        for item in flagged_words:
            suggestion = f" (did you mean '{item['suggestion']}'?)" if item["suggestion"] else ""
            st.warning(f"'{item['word']}' is not in the model's vocabulary{suggestion}")
    else:
        st.caption("All words are known to the model.")
    return proposal


def run_review(proposal: dict, centres: dict[str, tuple[float, float]]) -> dict:
    artifact = load_artifact()
    score = score_proposal(proposal)
    digest = explain_proposal(artifact, proposal)
    centre = centres.get(proposal["authority"])
    confidence = evidence.confidence_frame(proposal, centre_coords=centre)
    calibration = evidence.calibration_band(score["refusal_probability"])
    precedents = evidence.matched_precedents(proposal, k=20)
    objectives = evidence.plan_objectives(proposal["authority"], int(proposal["submission_year"] or 2026), proposal["description"])
    site = evidence.site_context(proposal)
    portfolio.record_event(
        score["model_version"], "review", proposal, score["refusal_probability"],
        {"band": score["risk_band"], "matched_summary": precedents["summary"]},
    )
    review = {
        "score": score,
        "digest": digest,
        "confidence": confidence,
        "calibration": calibration,
        "precedents": precedents,
        "objectives": objectives,
        "site": site,
        "proposal": proposal,
    }
    review["brief"] = brief.build_risk_register(review)
    return review


def render_brief_tab(review: dict) -> None:
    """The working document: risk register, unknowns, next actions, evidence quality, planner override."""
    brief_payload = review["brief"]
    score = review["score"]
    st.markdown(
        f"**The brief** - a working document for this scheme. Model risk **{score['refusal_probability'] * 100:.0f}%** "
        f"(band {score['risk_band'].upper()}). Every row below is either data-backed or explicitly marked unverified - "
        "nothing here invents a severity the model cannot support."
    )

    strengths = brief_payload.get("strengths") or []
    if strengths:
        st.markdown("**Site and scheme strengths**")
        for strength in strengths:
            st.markdown(f"- :green[{strength}]")

    register = brief_payload.get("register") or []
    if register:
        st.markdown("**Risk register**")
        severity_icon = {"high": ":red[**HIGH**]", "medium": ":orange[**MEDIUM**]", "low": "**LOW**", "unverified": "**UNVERIFIED**"}
        order = {"high": 0, "medium": 1, "low": 2, "unverified": 3}
        summary = pd.DataFrame([
            {"Issue": row["issue"], "Severity": row["severity"].upper(), "Confidence": row["confidence"],
             "Owner": row["owner"], "Status": row["status"]}
            for row in sorted(register, key=lambda r: order[r["severity"]])
        ])
        st.dataframe(summary, use_container_width=True, hide_index=True)
        for row in sorted(register, key=lambda r: order[r["severity"]]):
            title = f"{severity_icon.get(row['severity'], row['severity'])} | {row['issue']}"
            with st.expander(title, expanded=row["severity"] in ("high", "medium")):
                st.markdown(f"**Evidence**: {row['evidence']}")
                st.markdown(f"**Severity**: {row['severity']} | **Confidence**: {row['confidence']} | **Source**: {row['source']}")
                st.markdown(f"**Mitigation**: {row['mitigation']}")
                st.markdown(f"**Owner**: {row['owner']} | **Status**: {row['status']}")
        st.caption("Severity is derived from historical rates and site layers; confidence reflects how much data backs the row. "
                   "'Unverified' rows are the model saying what it does not know - they are a feature, not a gap.")

    next_actions = brief_payload.get("next_actions") or []
    if next_actions:
        st.markdown("**Next actions by owner**")
        owners: list[str] = []
        for action in next_actions:
            if action["owner"] not in owners:
                owners.append(action["owner"])
        for owner in owners:
            st.markdown(f"*{owner}*")
            for action in [a for a in next_actions if a["owner"] == owner]:
                severity = action["severity"]
                marker = ":red[" if severity in ("high", "medium") else ""
                st.markdown(f"- {marker}{action['issue']}" + ("]" if marker else "") + f" - {action['action']}")

    evidence_quality = brief_payload.get("evidence_quality") or []
    with st.expander("Evidence-quality stamps"):
        for stamp in evidence_quality:
            icon = {"ok": ":green[ok]", "thin": ":orange[thin]", "partial": ":orange[partial]",
                    "approximate": ":orange[approx]", "unverified": ":red[unverified]",
                    "fallback": ":orange[fallback]", "frozen_snapshot": ":blue[frozen]"}.get(stamp["status"], stamp["status"])
            st.markdown(f"- {icon} **{stamp['input']}** - {stamp['stamp']}")

    st.divider()
    render_override_panel(review)


def render_override_panel(review: dict) -> None:
    """Planner override with a permanent audit trail - the model value is never overwritten."""
    st.markdown("**Planner override & audit trail**")
    project_id = st.session_state.get("saved_project_id")
    if project_id is None:
        st.caption("Save the project to your portfolio first - overrides are recorded against the saved project and never replace the model value.")
        return
    overrides = portfolio.list_overrides(project_id)
    register = review["brief"].get("register") or []
    targets = [
        "Risk band",
        "Refusal probability",
        *[f"Register severity: {row['issue']}" for row in register],
    ]
    with st.form("override"):
        c1, c2, c3 = st.columns(3)
        with c1:
            target = st.selectbox("What is being overridden", targets)
            planner_name = st.text_input("Planner name", value="")
        with c2:
            original_value = {
                "Risk band": review["score"]["risk_band"].upper(),
                "Refusal probability": f"{review['score']['refusal_probability'] * 100:.0f}%",
            }
            original = original_value.get(target, "")
            if target.startswith("Register severity:"):
                issue = target.split(": ", 1)[1]
                row = next(r for r in register if r["issue"] == issue)
                original = row["severity"]
            st.text_input("Model value (read-only)", value=original, disabled=True)
            if target == "Risk band":
                override_value = st.selectbox("Planner value", ["LOW", "MEDIUM", "HIGH"])
            elif target == "Refusal probability":
                override_value = f"{st.slider('Planner probability', 0, 100, int(review['score']['refusal_probability'] * 100))}%"
            else:
                override_value = st.selectbox("Planner value", ["low", "medium", "high", "unverified"])
        with c3:
            rationale = st.text_area("Rationale (recorded in the audit trail)", value="")
        submitted = st.form_submit_button("Record override")
    if submitted:
        if not rationale.strip():
            st.warning("A rationale is required - the audit trail must explain why the model value was set aside.")
        else:
            portfolio.save_override(project_id, None, target, original, override_value, rationale, planner_name)
            st.success("Override recorded. The model value remains unchanged in the scoring log.")
            overrides = portfolio.list_overrides(project_id)
    if overrides:
        st.markdown("**Audit trail**")
        for override in overrides:
            st.markdown(
                f"- `{override['created_at'][:16]}` {override['planner_name']} overrode **{override['target']}**: "
                f"{override['original_value']} -> **{override['override_value']}**. Rationale: {override['rationale']}"
            )
    else:
        st.caption("No overrides recorded for this project yet.")


def render_verdict_tab(review: dict) -> None:
    score = review["score"]
    calibration = review["calibration"]
    confidence = review["confidence"]
    digest = review["digest"]
    risk = score["refusal_probability"]
    band = score["risk_band"].upper()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Estimated refusal probability", f"{risk * 100:.0f}%")
    with col2:
        st.metric("Risk band", band)
    with col3:
        grant = score["grant_probability"]
        st.metric("Estimated grant probability", f"{grant * 100:.0f}%")
    st.caption("Bands are calibrated across all residential schemes: low <= 3.8%, medium 3.8-11.4%, high > 11.4%. "
               "Larger schemes are genuinely riskier on average, so most 10+ unit schemes land in the high band - "
               "the percentile line below shows where this scheme sits against other large schemes specifically.")

    if calibration:
        st.info(
            f"**Calibration**: schemes the model scored in the {calibration['band']} band historically refused at "
            f"{calibration['observed_rate'] * 100:.0f}% (95% CI {calibration['ci_lo'] * 100:.0f}-{calibration['ci_hi'] * 100:.0f}%, "
            f"n={calibration['n']:,}). This is the empirical range for scores like this one - not the range for your site alone."
        )
    position = evidence.ge10_position(risk, proposal_units(review))
    if position:
        st.info(position["note"])
    if confidence.get("specialised"):
        spec = confidence["specialised"]
        st.warning(
            f"**Specialised scheme disclosure**: senior-living / care / retirement schemes historically refuse at "
            f"{spec['observed_rate_pre2024'] * 100:.0f}% (n={spec['n']}), above what the general score suggests. "
            f"General score {spec['general_score'] * 100:.0f}% / specialised-prior-adjusted {spec['specialised_prior_adjusted'] * 100:.0f}%."
        )

    st.markdown(f"**{digest['summary']}**")
    for factor in digest["factors"]:
        st.markdown(f"- {factor['text']}")

    for note in confidence["confidence_notes"]:
        st.info(note)
    if confidence["fallbacks"]:
        with st.expander("Inputs the model approximated (fallbacks)"):
            for fallback in confidence["fallbacks"]:
                st.markdown(f"- {fallback}")

    with st.expander("The machinery behind this score - what the model actually consulted"):
        matched_summary = review["precedents"]["summary"]
        obj_summary = review["objectives"].get("summary") or {}
        site = review["site"]
        rates = site.get("nearby_rates", {})
        flood = site.get("flood") or {}
        small_area = site.get("small_area") or {}
        st.markdown(
            f"- **{matched_summary.get('retrieved', 0)} matched past applications** drawn from {matched_summary.get('pool', 0)} decided "
            f"applications of this scheme type in the last 5 years ({matched_summary['refused_count']} refused, "
            f"{matched_summary['granted_count']} granted, {matched_summary.get('same_council_count', 0)} in {review['proposal']['authority']}). "
            "See the Precedents tab for each one by reference."
        )
        if obj_summary:
            st.markdown(
                f"- **{obj_summary['objective_count']} objectives** from the {obj_summary['plan_period']} "
                f"{obj_summary['council']} development plan (theme profile). See the Policy tab for the crosswalk."
            )
        st.markdown(
            f"- **OPW flood layers**: {'site point in a mapped flood zone' if flood.get('flood_any') else 'no flood-zone hit'} "
            f"(nearest fluvial zone {flood.get('nearest_fluvial_m', 0):.0f} m, nearest coastal {flood.get('nearest_coastal_m', 0):.0f} m)."
        )
        if small_area:
            st.markdown(
                f"- **Census small-area context**: {small_area.get('pop_density_per_sqkm', 0):.0f} people/km2, "
                f"owner-occupied {small_area.get('owner_share', 0):.0f}%, urban={small_area.get('is_urban')}."
            )
        km1 = rates.get("within_1km") or {}
        km3 = rates.get("within_3km") or {}
        st.markdown(
            f"- **Refusal history at three scales**: national 24-month rate, council 12/24-month rates, and nearby rates "
            f"(1km: {km1.get('recent_24m_count', 0)} applications at {km1.get('recent_24m_refusal_rate', 0) * 100:.0f}%; "
            f"3km: {km3.get('recent_24m_count', 0)} at {km3.get('recent_24m_refusal_rate', 0) * 100:.0f}%)."
        )
        st.caption("Post-submission information (FI requests, refusal reasons, appeals) is excluded from the model inputs by construction.")


def proposal_units(review: dict) -> float | None:
    units = review["proposal"].get("units")
    try:
        return float(units) if units is not None else None
    except (TypeError, ValueError):
        return None


def render_precedents_tab(review: dict) -> None:
    precedents = review["precedents"]
    summary = precedents["summary"]
    if not summary.get("retrieved"):
        st.info(summary.get("note", "No matched precedents in the 5-year window before the submission year."))
        return
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Refused", f"{summary['refused_count']} / {summary['retrieved']}")
    col2.metric("Granted", f"{summary['granted_count']} / {summary['retrieved']}")
    col3.metric("In your council", f"{summary['same_council_count']} / {summary['retrieved']}")
    col4.metric("Median year", f"{summary['median_year']}")
    st.markdown(
        f"**The {summary['retrieved']} closest past applications** to this scheme, matched on wording, unit count, density, "
        f"council and recency - decided applications received in the last 5 years only "
        f"({summary.get('pool', 0)} on file for this scheme type). "
        f"Of these, **{summary['refused_count']} were refused and {summary['granted_count']} were granted**."
    )
    if summary.get("units_range") and summary["units_range"][0] is not None:
        st.caption(f"Matched schemes range from {summary['units_range'][0]:.0f} to {summary['units_range'][1]:.0f} units - "
                   f"your scheme has {proposal_units(review):.0f}.")

    rows = []
    for item in precedents["precedents"]:
        rows.append({
            "App ref": item["application_number"],
            "Council": item["council"],
            "Received": item["received_date"],
            "Decided": item["decision_date"] or "-",
            "Units": item["units"] if item["units"] is not None else "-",
            "Outcome": item["outcome"],
            "Wording match": item["wording_label"],
            "Why it matched": ", ".join(item["match_reasons"]),
        })
    frame = pd.DataFrame(rows)

    def _colour_outcome(value: str) -> str:
        if value == "Refused":
            return "color: #c0392b; font-weight: bold"
        if value == "Granted":
            return "color: #1e8449; font-weight: bold"
        return ""

    st.dataframe(frame.style.map(_colour_outcome, subset=["Outcome"]), use_container_width=True, hide_index=True)

    st.markdown("**Inspector rationale** (refused matches with extracted reasons)")
    rationale_rows = [c for c in precedents["precedents"] if c["outcome"] == "Refused" and c.get("rationale")]
    if not rationale_rows:
        st.caption("No extracted refusal rationale on file for these particular cases.")
    for item in rationale_rows:
        with st.expander(f"{item['application_number']} - {item['council']} - {item['rationale_label'] or item['rationale_tag']}"):
            st.caption(f"Refused {item['decision_date'] or item['received_date']} | {item['units']} units | "
                       f"wording match {item['wording_label'].lower()}")
            st.write(item["rationale"])
            st.caption(f"Full description on file: {item['description']}")
    st.caption("Rationales are quoted from published refusal documents of historical cases - evidence context, not a model input.")


def render_policy_tab(review: dict) -> None:
    objectives = review["objectives"]
    summary = objectives.get("summary")
    if not summary:
        st.info(objectives.get("note", "No development-plan objective extraction on file for this authority."))
        return
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Objectives in plan", f"{summary['objective_count']}")
    col2.metric("Addressed in your text", f"{summary['addressed']}")
    col3.metric("Not addressed", f"{summary['open']}")
    col4.metric("Site-flagged", f"{summary['flagged']}")
    st.markdown(
        f"**Plan in force**: {summary['plan_document']} ({summary['plan_period']}). "
        f"This is the full objective list - {summary['objective_count']} objectives - sorted by how often the plan text cites them. "
        f"Green = your description text engages the objective. Amber = carried in the plan but not mentioned in your text "
        f"(a submission gap you can close). Red = site-level conflict (e.g. flood-related objective on a flood-affected site)."
        + (" Nearest plan used - no plan period matched the submission year." if summary.get("fallback_used") else "")
    )
    if summary.get("dropped_junk_codes"):
        st.caption(f"{summary['dropped_junk_codes']} extraction artifacts (numeric-only codes) were dropped from the list.")

    all_rows = []
    for item in objectives["objectives"]:
        status = {"addressed": "Addressed", "open": "Open", "flag": "FLAG"}[item["status"]]
        all_rows.append({
            "Code": item["code"],
            "Objective": item["title"][:260],
            "Theme": item["theme_label"],
            "Mentions": item["mentions"],
            "Status": status,
        })
    frame = pd.DataFrame(all_rows)

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        status_filter = st.multiselect("Status", ["Addressed", "Open", "FLAG"], default=["Addressed", "Open", "FLAG"])
    with filter_col2:
        theme_filter = st.multiselect("Theme", sorted(frame["Theme"].unique().tolist()))
    search = st.text_input("Search objectives", value="")
    shown = frame
    if status_filter:
        shown = shown[shown["Status"].isin(status_filter)]
    if theme_filter:
        shown = shown[shown["Theme"].isin(theme_filter)]
    if search.strip():
        shown = shown[shown["Objective"].str.contains(search.strip(), case=False, na=False)]

    def _colour_status(value: str) -> str:
        if value == "Addressed":
            return "color: #1e8449; font-weight: bold"
        if value == "FLAG":
            return "color: #c0392b; font-weight: bold"
        return "color: #8a6d00"

    st.caption(f"Showing {len(shown)} of {len(all_rows)} objectives.")
    st.dataframe(shown.style.map(_colour_status, subset=["Status"]), use_container_width=True, hide_index=True)


def render_site_tab(review: dict) -> None:
    site = review["site"]
    if site["coordinates"]["itm_easting"] is None:
        st.info("No coordinates - set a location in Scheme details to see the site evidence.")
        return
    flood = site.get("flood")
    if flood:
        if flood["flood_any"]:
            st.error(
                f"**Flood**: the site point is in a mapped flood zone (fluvial max depth {flood['fluvial_depth_max_m']} m, "
                f"coastal max depth {flood['coastal_depth_max_m']} m). Flooding and drainage are among the most common refusal grounds."
            )
        else:
            st.success(
                f"**Flood**: no mapped flood-zone hit at the site point. Nearest fluvial zone {flood['nearest_fluvial_m']:.0f} m, "
                f"nearest coastal zone {flood['nearest_coastal_m']:.0f} m."
            )
    small_area = site.get("small_area")
    if small_area:
        st.markdown(
            f"**Census small area**: {small_area.get('urban_area_name') or small_area.get('nuts3')} - "
            f"{small_area.get('pop_density_per_sqkm'):.0f} people/km2, owner-occupied {small_area.get('owner_share'):.0f}%, "
            f"private rent {small_area.get('private_rent_share'):.0f}%, septic {small_area.get('septic_share'):.0f}%, "
            f"{small_area.get('cars_per_hh'):.2f} cars/household."
        )
    rates = site.get("nearby_rates", {})
    if rates:
        km1 = rates.get("within_1km") or {}
        km3 = rates.get("within_3km") or {}
        st.markdown(
            f"**Local track record**: 1km - {km1.get('recent_24m_count', 0)} applications in the last 24 months, "
            f"{km1.get('recent_24m_refusal_rate', 0) * 100:.0f}% refused (all time: {km1.get('all_time_count', 0)}). "
            f"3km - {km3.get('recent_24m_count', 0)} applications, {km3.get('recent_24m_refusal_rate', 0) * 100:.0f}% refused."
        )
    zoning = site.get("zoning")
    if zoning:
        if zoning.get("status") == "ok":
            st.markdown(f"**Zoning**: {zoning.get('zone')} - {zoning.get('zone_description')} ({zoning.get('plan_period')}).")
        else:
            st.caption(f"Zoning: {zoning.get('note')}")

    constraints = site.get("constraints")
    if constraints:
        st.markdown("**National constraint layers**")
        if constraints.get("niah"):
            niah = constraints["niah"]
            st.markdown(f"- **Heritage (NIAH)**: nearest recorded structure is **{niah['name']}** "
                        f"({niah['reg_no']}, {niah.get('town') or niah.get('county')}) - {niah['distance_m']:.0f} m away. "
                        f"NIAH is advisory; confirm the council RPS separately.")
        if constraints.get("natura"):
            natura = constraints["natura"]
            marker = ":red[" if natura["distance_m"] < 1000 else ""
            st.markdown(f"- **Natura 2000**: nearest site is **{natura['sitename']}** ({natura['type']}, {natura['sitecode']}) - "
                        f"{marker}{natura['distance_m'] / 1000:.2f} km" + (" away]" if marker else " away") + ".")
        if constraints.get("traffic"):
            traffic = constraints["traffic"]
            st.markdown(f"- **Traffic**: {traffic['within_2km']} TII counters within 2 km; nearest **{traffic['nearest_name']}** "
                        f"at {traffic['nearest_distance_m']:.0f} m.")
        if constraints.get("wwtp"):
            wwtp = constraints["wwtp"]
            st.markdown(f"- **Wastewater (EPA)**: nearest recorded discharge point **{wwtp['name']}** "
                        f"({wwtp['distance_m'] / 1000:.1f} km) - capacity is not published; confirm with Irish Water.")

    nearby = site.get("nearby")
    if nearby and nearby["points"]:
        points = nearby["points"]
        refused = pd.DataFrame([p for p in points if p["outcome"] == "Refused"])
        granted = pd.DataFrame([p for p in points if p["outcome"] == "Granted"])
        refused["tooltip"] = refused.apply(lambda row: f"{row['case_key']} | Refused | {row['received']}", axis=1)
        granted["tooltip"] = granted.apply(lambda row: f"{row['case_key']} | Granted | {row['received']}", axis=1)
        site_row = pd.DataFrame([{"lat": site["map"]["lat"], "lon": site["map"]["lon"], "tooltip": "YOUR SITE"}])
        layers = []
        if not granted.empty:
            layers.append(pdk.Layer("ScatterplotLayer", data=granted, get_position="[lon, lat]", get_radius=70,
                                    get_fill_color=[30, 132, 73, 190], pickable=True))
        if not refused.empty:
            layers.append(pdk.Layer("ScatterplotLayer", data=refused, get_position="[lon, lat]", get_radius=70,
                                    get_fill_color=[192, 57, 43, 190], pickable=True))
        layers.append(pdk.Layer("ScatterplotLayer", data=site_row, get_position="[lon, lat]", get_radius=300,
                                get_fill_color=[0, 60, 140, 255], pickable=True))
        if site["map"].get("flood_any"):
            layers.append(pdk.Layer(
                "ScatterplotLayer",
                data=site_row,
                get_position="[lon, lat]",
                get_radius=700,
                get_fill_color=[255, 60, 40, 40],
                get_line_color=[255, 60, 40, 255],
                stroked=True,
                filled=False,
                line_width_min_pixels=2,
            ))
        view = pdk.ViewState(latitude=site["map"]["lat"], longitude=site["map"]["lon"], zoom=12.4, pitch=0)
        st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, tooltip={"text": "{tooltip}"}))
        st.caption("Blue = your site. Green = granted, red = refused decisions within 3km in the last 24 months. "
                   "Red ring = mapped flood-zone hit at the site point. " + nearby["cap_note"] + ".")

    st.divider()
    st.markdown("**Draw the site boundary** (optional)")
    st.caption("Draw a polygon over the site: the app computes the site area, density and the constraints inside the "
               "boundary (NIAH structures, Natura sites, wastewater points, traffic counters). Apply the area to rescore.")
    try:
        import folium  # noqa: F401
        from folium.plugins import Draw  # noqa: F401
        from streamlit_folium import st_folium  # noqa: F401

        centre = site.get("map") or {}
        boundary_map = folium.Map(location=[centre.get("lat", 53.35), centre.get("lon", -6.25)], zoom_start=15)
        Draw(
            export=True,
            draw_options={"polygon": True, "rectangle": True, "polyline": False,
                          "circle": False, "circlemarker": False, "marker": False},
        ).add_to(boundary_map)
        drawing_output = st_folium(boundary_map, width=700, height=420, key="boundary_draw")
        drawings = (drawing_output or {}).get("all_drawings") or []
        if drawings:
            last_drawing = drawings[-1]
            geometry = last_drawing.get("geometry") or {}
            if geometry.get("type") in ("Polygon", "Rectangle") and geometry.get("coordinates"):
                boundary = evidence.boundary_evidence(review["proposal"], geometry["coordinates"])
                if boundary:
                    st.success(
                        f"Boundary area: **{boundary['area_ha']:.2f} ha** ({boundary['area_sqm']:,.0f} m2) - "
                        f"density {boundary['density_units_per_ha']} units/ha at {boundary['units']} units."
                    )
                    inside = boundary["inside"]
                    lines = []
                    if "niah_count" in inside:
                        lines.append(f"{inside['niah_count']} NIAH-recorded structure(s) inside the boundary")
                    if "natura_count" in inside:
                        lines.append(f"{inside['natura_count']} Natura 2000 site(s) intersect the boundary")
                    if "wwtp_inside_count" in inside:
                        lines.append(f"{inside['wwtp_inside_count']} EPA wastewater point(s) inside")
                    if "traffic_inside_count" in inside:
                        lines.append(f"{inside['traffic_inside_count']} traffic counter(s) inside")
                    for line in lines:
                        st.markdown(f"- {line}")
                    st.caption("The drawn boundary feeds the site area and site-context counts only - the frozen scoring path is unchanged.")
                    if st.button("Use this area as the site area", key="apply_boundary"):
                        st.session_state["site_area_sqm"] = boundary["area_sqm"]
                        st.session_state["review"] = None
                        st.rerun()
    except Exception as exc:
        st.caption(f"Boundary drawing unavailable here: {type(exc).__name__}")


def render_wording_tab(review: dict, proposal: dict, artifact) -> None:
    st.markdown("**Rewrite in the style of granted schemes**")
    st.caption("Local, measured rewrites - no LLM. Each variant is rescored against your proposal; "
               "adopt one only if it still describes the scheme truthfully. Wording only ever moves the score "
               "in ways the historical record supports - it never overrides the site and scheme fundamentals.")
    if st.button("Generate rewritten descriptions", type="primary", key="rewrite"):
        with st.spinner("Testing variants against your scheme..."):
            result = wording.rewrite_variants(proposal)
        st.session_state["rewrites"] = result
        portfolio.record_event(review["score"]["model_version"], "wording_rewrite", proposal, result["baseline_refusal_probability"],
                               {"variants": [{"label": v["label"], "delta_pp": v["delta_pp"]} for v in result["variants"]]})
    rewrites = st.session_state.get("rewrites")
    if rewrites:
        st.caption(f"Baseline refusal: {rewrites['baseline_refusal_probability'] * 100:.0f}% (scheme kind: {rewrites['kind']})")
        for index, variant in enumerate(rewrites["variants"]):
            delta = variant["delta_pp"]
            if delta < 0:
                delta_text = f":green[{delta:+.1f} pp]"
            elif delta > 0:
                delta_text = f":red[{delta:+.1f} pp]"
            else:
                delta_text = f"{delta:+.1f} pp"
            with st.container(border=True):
                st.markdown(
                    f"**{variant['label']}** - refusal {variant['refusal_probability'] * 100:.0f}% "
                    f"({delta_text}) | text overlap with yours: {variant['similarity_to_yours']}"
                )
                st.code(variant["description"], language=None)
                st.caption(f"Source: {variant['source']}. {variant['rationale']}")
                col_use, col_save = st.columns(2)
                with col_use:
                    if st.button("Use this wording", key=f"use_{index}"):
                        st.session_state["description"] = variant["description"]
                        st.session_state["_tpl_description"] = variant["description"]
                        st.session_state["review"] = None
                        st.rerun()
                with col_save:
                    if st.button("Save as scenario", key=f"save_var_{index}"):
                        saved = st.session_state.get("saved_project_id")
                        if saved is None:
                            st.warning("Save the project to your portfolio first (button under the headline).")
                        else:
                            portfolio.save_scenario(saved, variant["label"], {"description": variant["description"]},
                                                    variant["refusal_probability"], variant["delta_pp"], "wording rewrite")
                            st.success("Scenario saved to the project.")
        if any(v["similarity_to_yours"] < 0.5 for v in rewrites["variants"]):
            st.warning("Variants with low text overlap change more than wording - check the numbers still describe your scheme before adopting.")


def render_scenario_tab(review: dict, base: dict, artifact) -> None:
    st.caption("Duplicate the proposal, change supported fields, rescore. Sensitivity analysis - not guarantees.")
    mode = st.radio("Scenario mode", ["Edit a scenario myself", "Run a lever sweep"], index=0, key="scenario_mode")
    saved = st.session_state.get("saved_project_id")
    if mode == "Edit a scenario myself":
        with st.form("scenario"):
            c1, c2, c3 = st.columns(3)
            with c1:
                s_units = st.number_input("Units", min_value=0, max_value=500, value=int(base["units"] or 0))
                s_floor = st.number_input("Floor area (m2)", min_value=0.0, max_value=1_000_000.0, value=float(base["floor_area_sqm"] or 0))
            with c2:
                s_site = st.number_input("Site area (m2)", min_value=0.0, max_value=1_000_000.0, value=float(base["site_area_sqm"] or 0))
            with c3:
                s_desc = st.text_area("Description (optional change)", value=base["description"])
            s_label = st.text_input("Scenario label", value="Edited scenario")
            submitted = st.form_submit_button("Score scenario")
        if submitted:
            scenario = {**base, "description": s_desc, "units": int(s_units),
                        "site_area_sqm": float(s_site), "floor_area_sqm": float(s_floor)}
            with st.spinner("Scoring scenario..."):
                result = plain_language(artifact, base, scenario)
            delta = result["delta_pp"]
            col1, col2 = st.columns(2)
            col1.metric("Baseline refusal", f"{result['baseline_refusal_probability'] * 100:.0f}%")
            col2.metric("Scenario refusal", f"{result['scenario_refusal_probability'] * 100:.0f}%", delta=f"{delta:+.1f}pp", delta_color="inverse")
            st.markdown(f"**{result['verdict']}**")
            for bullet in result["explanations"]:
                st.markdown(f"- {bullet['text']}")
            st.caption(result["note"])
            st.session_state["last_scenario"] = {"label": s_label, "changes": {"description": s_desc, "units": int(s_units),
                                                   "site_area_sqm": float(s_site), "floor_area_sqm": float(s_floor)},
                                                 "refusal_probability": result["scenario_refusal_probability"],
                                                 "delta_pp": delta, "verdict": result["verdict"]}
            portfolio.record_event(review["score"]["model_version"], "scenario", scenario,
                                   result["scenario_refusal_probability"], {"delta_pp": delta, "label": s_label})
        last = st.session_state.get("last_scenario")
        if last and saved is not None and st.button("Save this scenario to the project"):
            portfolio.save_scenario(saved, last["label"], last["changes"], last["refusal_probability"], last["delta_pp"], last["verdict"])
            st.success("Scenario saved.")
    else:
        if st.button("Run lever sweep", type="primary", key="lever_sweep"):
            base_units = int(base["units"] or 0)
            base_site = float(base["site_area_sqm"] or 0)
            base_floor = float(base["floor_area_sqm"] or 0)
            levers: list[tuple[str, dict]] = []
            if base_units >= 2:
                levers.append((f"Fewer units ({max(1, int(base_units * 0.75))})", {"units": max(1, int(base_units * 0.75))}))
                levers.append((f"Fewer units ({max(1, int(base_units * 0.5))})", {"units": max(1, int(base_units * 0.5))}))
                levers.append((f"More units ({int(base_units * 1.25)})", {"units": int(base_units * 1.25)}))
            if base_site > 0:
                levers.append((f"Larger site (+25%)", {"site_area_sqm": base_site * 1.25}))
                levers.append((f"Larger site (+50%)", {"site_area_sqm": base_site * 1.5}))
                levers.append((f"Smaller site (-25%)", {"site_area_sqm": base_site * 0.75}))
            if base_floor > 0:
                levers.append((f"Less floor area (-25%)", {"floor_area_sqm": base_floor * 0.75}))
                levers.append((f"Less floor area (-50%)", {"floor_area_sqm": base_floor * 0.5}))
            if base["description"] != DESCRIPTION_TEMPLATES["Detailed (mixed 47-unit)"]["description"] and base_units < 60:
                levers.append(("More detailed description", {"description": DESCRIPTION_TEMPLATES["Detailed (mixed 47-unit)"]["description"]}))
            levers.append(("Design-quality wording", {"description": base["description"] + " with high quality design and finishes, generous landscaped open space and adequate separation distances"}))
            if not levers:
                st.warning("Nothing to sweep - add units or site area first.")
            else:
                rows = []
                with st.spinner(f"Sweeping {len(levers)} scenarios..."):
                    for label, changes in levers:
                        scenario = {**base, **changes}
                        result = plain_language(artifact, base, scenario)
                        shown = {k: v for k, v in changes.items() if k in ("units", "site_area_sqm", "floor_area_sqm")}
                        shown_text = ", ".join(f"{k.split('_')[0]} {v:g}" for k, v in shown.items()) if shown else "description change"
                        rows.append({
                            "change": label,
                            "from": shown_text,
                            "refusal_%": round(result["scenario_refusal_probability"] * 100, 1),
                            "delta_pp": round(result["delta_pp"], 1),
                            "verdict": result["verdict"],
                        })
                        portfolio.record_event(review["score"]["model_version"], "lever", scenario,
                                               result["scenario_refusal_probability"], {"delta_pp": round(result["delta_pp"], 1), "label": label})
                table = pd.DataFrame(rows).sort_values("delta_pp").reset_index(drop=True)
                st.markdown("**Lever sweep results** (sorted by effect on refusal probability)")
                st.markdown("| Change | From | Refusal | Delta |\n|---|---|---|---|")
                for _, row in table.iterrows():
                    delta = row["delta_pp"]
                    colour = ":green[" if delta < 0 else (":red[" if delta > 0 else "")
                    delta_text = f"{colour}{delta:+.1f} pp]" if colour else f"{delta:+.1f} pp"
                    st.markdown(f"| {row['change']} | {row['from']} | {row['refusal_%']:.1f}% | {delta_text} |")
                negative = table[table["delta_pp"] < 0]
                if negative.empty:
                    st.warning(
                        "No tested change lowers the refusal probability - the model places this scheme near its "
                        "lowest-risk form for this site. The risk is mostly driven by factors outside the editable "
                        "fields (location, council track record, plan strictness, precedents). See the Verdict tab."
                    )
                else:
                    best = negative.iloc[0]
                    st.markdown(f"**Biggest drop: {best['change']}** - {best['verdict']}")


def render_review(review: dict, centres: dict[str, tuple[float, float]]) -> None:
    proposal = review["proposal"]
    artifact = load_artifact()

    st.divider()
    st.subheader("Pre-submission review")

    col_score, col_save, col_report = st.columns([1.4, 1, 1])
    with col_save:
        if st.button("Save to portfolio", type="secondary"):
            project_id = portfolio.save_project(proposal, review["score"], evidence.evidence_snapshot(proposal))
            st.session_state["saved_project_id"] = project_id
            st.success(f"Saved as project #{project_id}. Open Portfolio & monitoring to track it.")

    tabs = st.tabs(["Brief", "Verdict", "Precedents", "Policy", "Site & map", "Wording", "Scenarios", "PDF report"])
    with tabs[0]:
        render_brief_tab(review)
    with tabs[1]:
        render_verdict_tab(review)
    with tabs[2]:
        render_precedents_tab(review)
    with tabs[3]:
        render_policy_tab(review)
    with tabs[4]:
        render_site_tab(review)
    with tabs[5]:
        render_wording_tab(review, proposal, artifact)
    with tabs[6]:
        render_scenario_tab(review, proposal, artifact)
    with tabs[7]:
        render_report_tab(review)


def render_report_tab(review: dict) -> None:
    st.markdown("**Downloadable pre-submission review** - branded, dated, evidence-cited.")
    st.markdown(
        "The PDF carries the headline result with its calibration range, the drivers, the matched precedents by reference "
        "with inspector rationale, the development-plan crosswalk, the site evidence, the risk register and any recorded "
        "planner overrides."
    )
    proposal = review["proposal"]
    label = proposal.get("name") or f"{proposal['authority']} - {int(proposal['units'] or 0)} units"
    if st.button("Generate PDF report", type="primary"):
        with st.spinner("Building report..."):
            project_id = st.session_state.get("saved_project_id")
            overrides = portfolio.list_overrides(project_id) if project_id is not None else []
            pdf_bytes = build_report_pdf(
                scheme_label=label,
                proposal=proposal,
                score=review["score"],
                digest=review["digest"],
                confidence=review["confidence"],
                calibration=review["calibration"],
                precedents=review["precedents"],
                objectives=review["objectives"],
                site=review["site"],
                brief=review.get("brief"),
                override=overrides[0] if overrides else None,
            )
        slug = "".join(ch if ch.isalnum() else "_" for ch in label.lower())[:60]
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"pre_submission_review_{slug}.pdf",
            mime="application/pdf",
            key="download_report",
        )


def render_monitor(project_row: dict) -> None:
    project = portfolio.get_project(project_row["id"])
    latest = portfolio.latest_run(project_row["id"])
    snapshot_row = portfolio.latest_snapshot(project_row["id"])
    with st.spinner(f"Rescoring {project['name']} against the live register..."):
        current_score = score_proposal(project)
        current_snapshot = evidence.evidence_snapshot(project)
        portfolio.record_event(current_score["model_version"], "monitor_rescore", project, current_score["refusal_probability"],
                               {"project_id": project_row["id"]})
    alerts: list[str] = []
    if latest is None:
        alerts.append("No recorded run for this project - save it from the review page first.")
    else:
        delta_pp = (current_score["refusal_probability"] - latest["refusal_probability"]) * 100
        if abs(delta_pp) >= 1:
            alerts.append(
                f"Risk moved since the saved run: {latest['refusal_probability'] * 100:.0f}% -> "
                f"{current_score['refusal_probability'] * 100:.0f}% ({delta_pp:+.1f}pp). Same inputs, newer context."
            )
        else:
            alerts.append(f"Risk unchanged since the saved run ({current_score['refusal_probability'] * 100:.0f}%, {delta_pp:+.1f}pp).")
    if snapshot_row is None:
        alerts.append("No evidence snapshot on file for this project - save it from the review page to enable change alerts.")
    else:
        old = json.loads(snapshot_row["evidence_json"])
        for key in ("nearby_1km", "nearby_3km"):
            old_rate = (old.get(key) or {}).get("refusal_rate")
            new_rate = (current_snapshot.get(key) or {}).get("refusal_rate")
            old_count = (old.get(key) or {}).get("recent_24m_count")
            new_count = (current_snapshot.get(key) or {}).get("recent_24m_count")
            radius = "1km" if key == "nearby_1km" else "3km"
            if old_count is None or new_count is None:
                continue
            if new_count != old_count:
                alerts.append(
                    f"New nearby decisions since your snapshot: {radius} applications {old_count} -> {new_count}, "
                    f"refusal rate {old_rate * 100:.0f}% -> {new_rate * 100:.0f}%."
                )
            elif old_rate is not None and new_rate is not None and abs(new_rate - old_rate) >= 0.02:
                alerts.append(f"{radius} refusal rate changed {old_rate * 100:.0f}% -> {new_rate * 100:.0f}% (count unchanged).")
        old_comp = (old.get("comp_top20") or {}).get("refusal_rate")
        new_comp = current_snapshot["comp_top20"]["refusal_rate"]
        if old_comp is not None and new_comp is not None and abs(new_comp - old_comp) >= 0.05:
            alerts.append(f"The comparable-case refusal rate moved {old_comp * 100:.0f}% -> {new_comp * 100:.0f}%.")
    if not any("New nearby" in a for a in alerts) and snapshot_row is not None:
        alerts.append("No new decisions in the register since your snapshot (register covers decisions through 2025-12-23).")
    for alert in alerts:
        st.markdown(f"- {alert}")
    scenarios = portfolio.list_scenarios(project_row["id"])
    if scenarios:
        st.markdown(f"**Saved scenarios** ({len(scenarios)})")
        for scenario in scenarios[:8]:
            st.markdown(f"- {scenario['label']}: refusal {scenario['refusal_probability'] * 100:.0f}% "
                        f"({scenario['delta_pp']:+.1f}pp) - {scenario['created_at'][:16]}")


def render_portfolio_view() -> None:
    st.subheader("Portfolio & monitoring")
    projects = portfolio.list_projects()
    if not projects:
        st.info("No saved schemes yet. Score a scheme and press 'Save to portfolio' to start tracking it.")
        return
    frame = pd.DataFrame([
        {
            "ID": p["id"],
            "Name": p["name"],
            "Authority": p["authority"],
            "Units": p["units"] if p["units"] is not None else "-",
            "Latest risk": f"{p['latest_risk'] * 100:.0f}%" if p["latest_risk"] is not None else "-",
            "Band": (p["latest_band"] or "-").upper(),
            "Updated": p["updated_at"][:16],
        }
        for p in projects
    ])
    st.dataframe(frame, use_container_width=True, hide_index=True)

    st.markdown("**Compare schemes side by side**")
    choices = st.multiselect("Select up to 4 schemes", [p["name"] for p in projects], max_selections=4)
    if choices:
        rows = []
        for project in projects:
            if project["name"] in choices:
                rows.append({
                    "Scheme": project["name"],
                    "Authority": project["authority"],
                    "Units": project["units"],
                    "Site (m2)": project["site_area_sqm"],
                    "Floor (m2)": project["floor_area_sqm"],
                    "Year": project["submission_year"],
                    "Refusal risk": f"{project['latest_risk'] * 100:.0f}%" if project["latest_risk"] is not None else "-",
                    "Band": (project["latest_band"] or "-").upper(),
                })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("**Monitor - what changed since you saved**")
    st.caption("Rescores each scheme against the live context (nearby decisions, comparables, history) and diffs it against the saved snapshot.")
    if st.button("Rescore all & check for changes", type="primary"):
        for project in projects:
            with st.container(border=True):
                st.markdown(f"**{project['name']}** ({project['authority']})")
                render_monitor(project)

    st.markdown("**Load or delete**")
    col_load, col_delete = st.columns(2)
    with col_load:
        load_choice = st.selectbox("Scheme to load into the review form", [p["name"] for p in projects])
        if st.button("Load into review form"):
            selected = next(p for p in projects if p["name"] == load_choice)
            set_state_from_proposal(portfolio.get_project(selected["id"]))
            st.session_state["saved_project_id"] = selected["id"]
            st.session_state["nav"] = "Review a scheme"
            st.session_state["review"] = None
            st.rerun()
    with col_delete:
        delete_choice = st.selectbox("Scheme to delete", [p["name"] for p in projects], key="delete_choice")
        if st.button("Delete scheme", type="secondary"):
            selected = next(p for p in projects if p["name"] == delete_choice)
            portfolio.delete_project(selected["id"])
            st.rerun()


def main() -> None:
    init_state()
    st.set_page_config(page_title="Pre-Submission Review - Planning Intelligence", layout="wide")
    with st.sidebar:
        st.markdown("## Planning Intelligence")
        st.caption("Pre-Submission Review  |  model v4-full")
        nav_options = ["Review a scheme", "Portfolio & monitoring"]
        st.radio(
            "Navigate", nav_options,
            index=nav_options.index(st.session_state.get("nav", "Review a scheme")),
            key="nav",
        )
        st.divider()
        st.caption("Submission-time risk for Irish residential schemes. Scores, evidence, PDF reports, portfolio and alerts.")
        events = portfolio.count_runs()
        if events:
            st.caption(f"{events} scoring events logged locally.")

    centres = load_council_centres()
    artifact = load_artifact()

    if st.session_state["nav"] == "Portfolio & monitoring":
        render_portfolio_view()
        return

    st.title("Pre-Submission Review")
    st.caption(
        "Score a residential scheme before submission, see the evidence behind the number, download a defensible "
        "PDF report, and track your schemes in a portfolio. Scores are model-attributed sensitivity estimates - "
        "not guarantees and not planning advice."
    )
    proposal = render_scheme_form(centres)

    if st.button("Run pre-submission review", type="primary"):
        with st.spinner("Scoring and assembling evidence..."):
            review = run_review(proposal, centres)
        st.session_state["review"] = review
        st.session_state["saved_project_id"] = st.session_state.get("saved_project_id")

    review = st.session_state.get("review")
    if review is not None:
        render_review(review, centres)

    st.divider()
    st.caption("Explanations are model-attributed sensitivity statements built from historical rates - not guaranteed outcomes. Frozen v3 remains the untouched baseline artifact.")


if __name__ == "__main__":
    main()
