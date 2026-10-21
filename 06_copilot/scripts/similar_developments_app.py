from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
import pydeck as pdk
import streamlit as st

from find_similar_developments import (
    DEFAULT_CSV,
    build_query_frame,
    find_similar,
    find_similar_to_query,
    fit_search_artifacts,
    transform_rows,
)
from precedent_copilot_logic import (
    CURRENT_DATE,
    THEME_LABELS,
    build_planning_risk_report,
    build_query_payload,
    citation_label,
    clean_text,
    compute_match_reasons,
    generate_strategy_pack,
    normalize_cases,
    normalize_decision,
    rerank_candidates,
    short_text,
)
from planning_repository import PlanningRepository
from prediction_service import predict_and_record
from refusal_theme_aggregation import REFUSAL_CASES_DEFAULT_PATH, build_refusal_theme_index
from scenario_view import render_scenario_testing
from site_evidence_service import (
    POLICY_CHUNKS_PATH,
    VERIFIED_RULES_PATH,
    load_current_zoning_layers,
    load_verified_rules,
)
from structured_score_service import CANDIDATE_PATH, load_structured_bundle

LEVER_RATES_PATH = (
    Path(__file__).resolve().parents[2]
    / "05_policy"
    / "current"
    / "lever_outcome_rates_2026-09-09.json"
)

LEVER_CONTRAST_PATH = (
    Path(__file__).resolve().parents[2]
    / "02_development"
    / "current"
    / "lever_contrast_2026-09-10.json"
)

RISK_MODEL_PATH = (
    Path(__file__).resolve().parents[2]
    / "05_policy"
    / "current"
    / "model_v3"
    / "national_residential_v3_comparables.joblib"
)
AUTHORITY_RELIABILITY_PATH = RISK_MODEL_PATH.parents[1] / "raw_planning_v3_reliability_by_authority.csv"
TYPE_RELIABILITY_PATH = RISK_MODEL_PATH.parents[1] / "raw_planning_v3_reliability_by_application_type.csv"
REVISION_EVIDENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "02_development"
    / "current"
    / "revision_intervention_evidence.csv"
)
CANONICAL_REVISION_RECORDS_PATH = (
    Path(__file__).resolve().parents[2]
    / "02_development"
    / "current"
    / "canonical_revision_scheme_records.csv"
)


@st.cache_data(show_spinner=False)
def load_data(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {path.resolve()}")
    df = pd.read_csv(path, low_memory=False)
    required = {"case_key", "PlanningAuthority", "ApplicationNumber", "DevelopmentDescription"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    return normalize_cases(df)


@st.cache_data(show_spinner=False)
def load_revision_evidence() -> pd.DataFrame:
    if not REVISION_EVIDENCE_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(REVISION_EVIDENCE_PATH, low_memory=False)


@st.cache_data(show_spinner=False)
def load_canonical_revision_records() -> pd.DataFrame:
    if not CANONICAL_REVISION_RECORDS_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(CANONICAL_REVISION_RECORDS_PATH, low_memory=False)


@st.cache_data(show_spinner=False)
def load_refusal_theme_index() -> pd.DataFrame:
    return build_refusal_theme_index(REFUSAL_CASES_DEFAULT_PATH)


@st.cache_resource(show_spinner=False)
def load_zoning_layers() -> dict:
    return load_current_zoning_layers()


@st.cache_data(show_spinner=False)
def load_verified_policy_rules() -> pd.DataFrame:
    if not VERIFIED_RULES_PATH.exists():
        return pd.DataFrame()
    return load_verified_rules(VERIFIED_RULES_PATH)


@st.cache_resource(show_spinner=False)
def load_structured_candidate() -> dict:
    if not CANDIDATE_PATH.exists():
        return {}
    return load_structured_bundle(CANDIDATE_PATH)


@st.cache_data(show_spinner=False)
def load_policy_chunks() -> pd.DataFrame:
    if not POLICY_CHUNKS_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(POLICY_CHUNKS_PATH, low_memory=False)


@st.cache_data(show_spinner=False)
def load_lever_rates() -> dict:
    if not LEVER_RATES_PATH.exists():
        return {}
    import json

    return json.loads(LEVER_RATES_PATH.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_lever_contrast() -> dict:
    if not LEVER_CONTRAST_PATH.exists():
        return {}
    import json

    return json.loads(LEVER_CONTRAST_PATH.read_text(encoding="utf-8"))


@st.cache_resource(show_spinner=True)
def build_index(df: pd.DataFrame):
    artifacts = fit_search_artifacts(df)
    x = transform_rows(df, artifacts)
    return artifacts, x


@st.cache_resource(show_spinner=False)
def load_risk_model():
    if not RISK_MODEL_PATH.exists():
        raise FileNotFoundError(f"Risk model not found: {RISK_MODEL_PATH}")
    bundle = joblib.load(RISK_MODEL_PATH)
    if isinstance(bundle, dict):
        bundle["authority_reliability"] = pd.read_csv(AUTHORITY_RELIABILITY_PATH) if AUTHORITY_RELIABILITY_PATH.exists() else pd.DataFrame()
        bundle["type_reliability"] = pd.read_csv(TYPE_RELIABILITY_PATH) if TYPE_RELIABILITY_PATH.exists() else pd.DataFrame()
    return bundle


def row_label(row: pd.Series) -> str:
    return (
        f"{row.get('case_key', '')} | "
        f"{row.get('PlanningAuthority', '')} | "
        f"{row.get('ApplicationNumber', '')} | "
        f"{short_text(row.get('DevelopmentDescription', ''), 70)}"
    )


def init_state() -> None:
    st.session_state.setdefault("copilot_results", {})
    st.session_state.setdefault("copilot_query", {})
    st.session_state.setdefault("pinned_case_keys", set())
    st.session_state.setdefault("strategy_pack_text", "")
    if "planning_repo" not in st.session_state:
        st.session_state["planning_repo"] = PlanningRepository()
    st.session_state.setdefault("baseline_scheme", {})
    st.session_state.setdefault("baseline_score", {})


def toggle_pin(case_key: str) -> None:
    current = set(st.session_state.get("pinned_case_keys", set()))
    if case_key in current:
        current.remove(case_key)
    else:
        current.add(case_key)
    st.session_state["pinned_case_keys"] = current


def build_intake_query(df: pd.DataFrame, search_mode: str) -> tuple[dict[str, object], int | None]:
    authorities = sorted(x for x in df["PlanningAuthority"].dropna().astype(str).unique() if x.strip())
    app_types = sorted(x for x in df["ApplicationType"].dropna().astype(str).unique() if x.strip())
    tags = sorted(x for x in df["case_top_primary_tag"].dropna().astype(str).unique() if x.strip())
    query_idx: int | None = None

    if search_mode == "Describe a new proposal":
        st.subheader("Project Intake")
        left, mid, right = st.columns([2, 1, 1])
        with left:
            description = st.text_area(
                "Proposed scheme",
                height=180,
                placeholder="Describe the scheme, access, drainage, mix, open space, landscaping, services, and any constraints.",
            )
            address = st.text_input("Site / location")
            uploaded_files = st.file_uploader(
                "Optional drawings / docs",
                accept_multiple_files=True,
                type=None,
                help="Files are referenced in the pack for v1. They are not parsed automatically yet.",
            )
        with mid:
            planning_authority = st.selectbox("Planning authority", options=[""] + authorities)
            application_type = st.selectbox("Application type", options=[""] + app_types)
            issue_tag = st.selectbox("Known issue / theme", options=[""] + tags)
            units_total = st.number_input("Units", min_value=0, value=25, step=1)
        with right:
            submission_year = st.number_input("Submission year", min_value=1990, max_value=2100, value=CURRENT_DATE.year, step=1)
            max_storeys = st.number_input("Max storeys", min_value=0.0, value=2.0, step=1.0)
            site_area_ha = st.number_input("Site area (ha)", min_value=0.0, value=0.0, step=0.1)
            itm_easting = st.number_input("ITM Easting", min_value=0.0, value=0.0, step=1.0)
            itm_northing = st.number_input("ITM Northing", min_value=0.0, value=0.0, step=1.0)

        with st.expander("Structured scheme fields", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                max_height_m = st.number_input("Max height (m)", min_value=0.0, value=0.0, step=0.1)
                upper_floor_setback_m = st.number_input("Upper-floor setback (m)", min_value=0.0, value=0.0, step=0.1)
            with c2:
                density_units_per_ha = st.number_input("Density (units/ha)", min_value=0.0, value=0.0, step=1.0)
                parking_spaces = st.number_input("Car spaces", min_value=0.0, value=0.0, step=1.0)
            with c3:
                bicycle_spaces = st.number_input("Bicycle spaces", min_value=0.0, value=0.0, step=1.0)
                private_open_space_sqm = st.number_input("Private open space (m²)", min_value=0.0, value=0.0, step=1.0)
            with c4:
                communal_open_space_sqm = st.number_input("Communal open space (m²)", min_value=0.0, value=0.0, step=1.0)

        query = build_query_payload(
            planning_authority=planning_authority,
            application_type=application_type,
            description=description,
            address=address,
            units_total=float(units_total) if units_total else None,
            storeys=float(max_storeys) if max_storeys else None,
            site_area_ha=float(site_area_ha) if site_area_ha else None,
            itm_easting=float(itm_easting) if itm_easting else None,
            itm_northing=float(itm_northing) if itm_northing else None,
            issue_tag=issue_tag,
            uploaded_documents=[f.name for f in uploaded_files] if uploaded_files else [],
        )
        query["received_year"] = float(submission_year)
        query.update({
            "max_height_m": max_height_m or None,
            "upper_floor_setback_m": upper_floor_setback_m or None,
            "density_units_per_ha": density_units_per_ha or None,
            "parking_spaces": parking_spaces or None,
            "bicycle_spaces": bicycle_spaces or None,
            "private_open_space_sqm": private_open_space_sqm or None,
            "communal_open_space_sqm": communal_open_space_sqm or None,
        })
        st.caption("The query is ranked against Irish GE10 housing precedents already extracted in the canonical dataset.")
        return query, None

    st.subheader("Existing Case Intake")
    labels = [row_label(df.iloc[i]) for i in range(len(df))]
    selected_label = st.selectbox("Choose development", options=labels, index=0)
    query_idx = labels.index(selected_label)
    query_row = df.iloc[query_idx]
    st.write(
        {
            "case_key": query_row.get("case_key", ""),
            "PlanningAuthority": query_row.get("PlanningAuthority", ""),
            "ApplicationNumber": query_row.get("ApplicationNumber", ""),
            "Decision": query_row.get("Decision", ""),
            "Units": query_row.get("units_total_num", ""),
            "DevelopmentDescription": short_text(query_row.get("DevelopmentDescription"), 400),
        }
    )
    return query_row.to_dict(), query_idx


def run_search(
    df: pd.DataFrame,
    artifacts,
    x,
    query_payload: dict[str, object],
    query_idx: int | None,
    top_k: int,
) -> dict[str, pd.DataFrame]:
    if query_idx is None:
        query_df = build_query_frame(
            df,
            PlanningAuthority=query_payload.get("PlanningAuthority"),
            ApplicationType=query_payload.get("ApplicationType"),
            DevelopmentDescription=query_payload.get("DevelopmentDescription"),
            DevelopmentAddress=query_payload.get("DevelopmentAddress"),
            units_total_best=query_payload.get("units_total_best"),
            NumResidentialUnits=query_payload.get("units_total_best"),
            max_storeys_best=query_payload.get("max_storeys_best"),
            site_area_ha_best=query_payload.get("site_area_ha_best"),
            ITMEasting=query_payload.get("ITMEasting"),
            ITMNorthing=query_payload.get("ITMNorthing"),
            case_top_primary_tag=query_payload.get("case_top_primary_tag"),
        )
        base = find_similar_to_query(df, x, transform_rows(query_df, artifacts), top_k=max(top_k * 6, 120))
    else:
        base = find_similar(df, x, query_idx=query_idx, top_k=max(top_k * 6, 120))

    ranked = rerank_candidates(base, query_payload)
    ranked["match_reasons"] = ranked.apply(lambda row: " | ".join(compute_match_reasons(query_payload, row)), axis=1)
    overall = ranked.head(top_k)
    grants = ranked[ranked["decision_normalized"] == "GRANTED"].head(top_k)
    refusals = ranked[ranked["decision_normalized"] == "REFUSED"].head(top_k)
    fi_cases = ranked[ranked["fi_count_num"] > 0].head(top_k)
    if clean_text(query_payload.get("PlanningAuthority")):
        local = ranked[
            ranked["PlanningAuthority"].fillna("").astype(str).str.lower()
            == clean_text(query_payload.get("PlanningAuthority")).lower()
        ].head(top_k)
    else:
        local = ranked.dropna(subset=["distance_km"]).sort_values(["distance_km", "hybrid_score"], ascending=[True, False]).head(top_k)

    return {
        "ranked": ranked,
        "overall": overall,
        "grants": grants,
        "refusals": refusals,
        "fi": fi_cases,
        "local": local,
    }


def selected_cases_from_state(ranked: pd.DataFrame) -> pd.DataFrame:
    pinned_keys = set(st.session_state.get("pinned_case_keys", set()))
    if pinned_keys:
        selected = ranked[ranked["case_key"].isin(pinned_keys)]
        if not selected.empty:
            return selected
    fallback_keys = []
    for group in [
        st.session_state["copilot_results"].get("grants", pd.DataFrame()).head(3),
        st.session_state["copilot_results"].get("refusals", pd.DataFrame()).head(3),
        st.session_state["copilot_results"].get("fi", pd.DataFrame()).head(2),
    ]:
        if not group.empty:
            fallback_keys.extend(group["case_key"].tolist())
    if fallback_keys:
        return ranked[ranked["case_key"].isin(fallback_keys)].drop_duplicates("case_key")
    return ranked.head(8)


def pin_widget_key(scope: str, case_key: str) -> str:
    return f"pin_{scope}_{case_key}"


def render_case_card(row: pd.Series, widget_scope: str) -> None:
    case_key = clean_text(row.get("case_key"))
    title = (
        f"{citation_label(row)} | hybrid {float(row.get('hybrid_score', 0.0)):.3f}"
    )
    with st.expander(title):
        left, right = st.columns([3, 1])
        with left:
            st.write(
                {
                    "case_key": row.get("case_key", ""),
                    "decision": row.get("Decision", ""),
                    "decision_normalized": row.get("decision_normalized", ""),
                    "units": row.get("units_total_num", ""),
                    "max_storeys": row.get("max_storeys_num", ""),
                    "site_area_ha": row.get("site_area_ha_num", ""),
                    "reason_count": row.get("reason_count_num", 0),
                    "fi_item_count": row.get("fi_count_num", 0),
                }
            )
            st.caption("Why this matched: " + (clean_text(row.get("match_reasons")) or "text similarity"))
        with right:
            pin_label = "Unpin case" if case_key in st.session_state.get("pinned_case_keys", set()) else "Pin case"
            st.button(pin_label, key=pin_widget_key(widget_scope, case_key), on_click=toggle_pin, args=(case_key,))
            source_url = clean_text(row.get("source_url"))
            if source_url:
                st.markdown(f"[Open source]({source_url})")
        st.markdown("**Case summary**")
        st.write(clean_text(row.get("case_summary")) or clean_text(row.get("DevelopmentDescription")))
        st.markdown("**Coverage / confidence**")
        st.write(clean_text(row.get("coverage_note")))
        if clean_text(row.get("refusal_excerpt")):
            st.markdown("**Refusal evidence**")
            st.write(clean_text(row.get("refusal_excerpt")))
        if clean_text(row.get("fi_excerpt")):
            st.markdown("**Further information evidence**")
            st.write(clean_text(row.get("fi_excerpt")))


def render_results_table(title: str, df: pd.DataFrame, limit: int) -> None:
    st.subheader(title)
    if df.empty:
        st.info("No cases in this view.")
        return
    preview_cols = [
        c
        for c in [
            "hybrid_score",
            "text_score",
            "PlanningAuthority",
            "ApplicationNumber",
            "Decision",
            "units_total_num",
            "case_top_primary_tag",
            "reason_count_num",
            "fi_count_num",
            "distance_km",
            "match_reasons",
            "coverage_note",
        ]
        if c in df.columns
    ]
    preview = df.head(limit)[preview_cols].copy()
    for col in ["hybrid_score", "text_score", "distance_km"]:
        if col in preview.columns:
            preview[col] = preview[col].map(lambda v: None if pd.isna(v) else round(float(v), 3))
    st.dataframe(preview, use_container_width=True, hide_index=True)
    for _, row in df.head(limit).iterrows():
        render_case_card(row, title)


def render_metrics(results: dict[str, pd.DataFrame]) -> None:
    overall = results["overall"]
    refusals = results["refusals"]
    grants = results["grants"]
    fi_cases = results["fi"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Top matches", f"{len(overall):,}")
    col2.metric("Granted precedents", f"{len(grants):,}")
    col3.metric("Refusal precedents", f"{len(refusals):,}")
    col4.metric("FI precedents", f"{len(fi_cases):,}")


def render_summary(results: dict[str, pd.DataFrame]) -> None:
    ranked = results["ranked"]
    selected = selected_cases_from_state(ranked)
    st.subheader("Scheme Risk Summary")
    if selected.empty:
        st.info("Run a search to generate a risk summary.")
        return
    grants = selected[selected["decision_normalized"] == "GRANTED"]
    refusals = selected[selected["decision_normalized"] == "REFUSED"]
    fi_cases = selected[selected["fi_count_num"] > 0]
    risk_lines = []
    for frame, label in [(refusals, "refusal"), (fi_cases, "FI")]:
        if not frame.empty:
            tags = (
                frame["case_top_primary_tag"]
                .fillna("untagged")
                .astype(str)
                .value_counts()
                .head(3)
            )
            for tag, count in tags.items():
                risk_lines.append(f"{label}: {tag} ({int(count)} cases)")
    st.write(
        {
            "selected_precedents": int(len(selected)),
            "supporting_grants": int(len(grants)),
            "refusal_risks": int(len(refusals)),
            "fi_heavy_cases": int(len(fi_cases)),
            "leading_risk_themes": ", ".join(risk_lines) if risk_lines else "No dominant risk theme found.",
        }
    )
    st.caption("Pins drive the strategy pack. If nothing is pinned, the app falls back to the strongest mix of grants, refusals, and FI precedents.")


def render_planning_risk_report(report: dict[str, object]) -> None:
    st.subheader("Planning Risk Report")
    score = report.get("score", {})
    precedent_mix = report.get("precedent_mix", {})
    top_themes = report.get("top_themes", [])
    pressure_signals = report.get("pressure_signals", [])
    closest_precedents = report.get("closest_precedents", pd.DataFrame()).copy()

    col1, col2, col3, col4 = st.columns(4)
    if score.get("status") == "scored":
        col1.metric("Refusal risk", str(score.get("risk_band", "Not scored")))
        col2.metric("Calibrated estimate", f"{score.get('risk_score_0_100', 0):.1f}%")
    else:
        col1.metric("Refusal risk", "Not scored")
        col2.metric("Risk score", "n/a")
    col3.metric("Closest grants", f"{precedent_mix.get('grants', 0):,}")
    col4.metric("Closest refusals", f"{precedent_mix.get('refusals', 0):,}")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Main factors from comparable cases**")
        if top_themes:
            for item in top_themes:
                st.write(
                    f"- {item['label']}: {item['case_count']} comparable cases"
                )
        else:
            st.write("- No dominant refusal/FI theme found in the nearest comparables.")

        st.markdown("**Pressure signals from the current scheme**")
        if pressure_signals:
            for signal in pressure_signals:
                st.write(f"- {signal}")
        else:
            st.write("- No obvious structural pressure signal detected from the intake fields.")
    with right:
        st.markdown("**Comparable-case mix**")
        st.write(
            {
                "closest_precedents": int(precedent_mix.get("closest_cases", 0)),
                "granted": int(precedent_mix.get("grants", 0)),
                "refused": int(precedent_mix.get("refusals", 0)),
                "fi_cases": int(precedent_mix.get("fi_cases", 0)),
            }
        )
        if score.get("status") != "scored":
            st.caption("Add a planning authority to score the submission-time refusal model.")
        elif score.get("model_version") in {"national_residential_v1", "national_residential_v2_history", "national_residential_v3_comparables"}:
            authority_reliability = score.get("authority_reliability", {})
            type_reliability = score.get("application_type_reliability", {})
            st.markdown("**Model confidence**")
            if authority_reliability:
                observed = authority_reliability.get("actual_refusal_rate")
                st.write(
                    {
                        "council_confidence": authority_reliability.get("confidence", "limited"),
                        "council_auc": authority_reliability.get("evaluation_auc"),
                        "observed_refusal_rate_in_band": None if observed is None else round(float(observed) * 100, 1),
                        "band_cases": authority_reliability.get("cases", 0),
                    }
                )
            if type_reliability:
                st.caption(
                    f"Application type: {score.get('application_bucket')} | "
                    f"confidence: {type_reliability.get('confidence', 'limited')}"
                )
            history_diagnostics = score.get("history_diagnostics", {})
            if history_diagnostics and not history_diagnostics.get("nearby_history_available"):
                st.caption("Nearby-history features were not used because ITM coordinates were not supplied.")
            if history_diagnostics and history_diagnostics.get("history_was_capped_to_reference"):
                st.caption(f"History features use the frozen reference snapshot as of {history_diagnostics.get('effective_history_date')}.")
            if history_diagnostics and history_diagnostics.get("comparable_raw_values"):
                comp = history_diagnostics.get("comparable_raw_values", {})
                st.caption(
                    f"Comparable-feature reference count: {int(comp.get('comp_top20_count', 0) or 0)} prior text-similar cases."
                )

    if not closest_precedents.empty:
        preview = closest_precedents.copy()
        if "hybrid_score" in preview.columns:
            preview["hybrid_score"] = preview["hybrid_score"].map(lambda v: None if pd.isna(v) else round(float(v), 3))
        if "distance_km" in preview.columns:
            preview["distance_km"] = preview["distance_km"].map(lambda v: None if pd.isna(v) else round(float(v), 2))
        if "case_top_primary_tag" in preview.columns:
            preview["case_top_primary_tag"] = preview["case_top_primary_tag"].map(
                lambda v: THEME_LABELS.get(clean_text(v), clean_text(v).replace("_", " ")) if clean_text(v) else ""
            )
        st.markdown("**Closest precedents**")
        st.dataframe(preview, use_container_width=True, hide_index=True)


def render_map_tab(results: dict[str, pd.DataFrame], query_payload: dict[str, object]) -> None:
    st.subheader("Map")
    df = results["local"].dropna(subset=["latitude", "longitude"]).copy()
    if df.empty:
        st.info("No mappable local precedents. Add ITM coordinates in the intake or use a case with coordinates.")
        return
    plot_df = df.head(40).copy()
    plot_df["tooltip_label"] = plot_df.apply(
        lambda row: f"{citation_label(row)} | {short_text(row.get('DevelopmentDescription'), 90)}",
        axis=1,
    )
    view_state = pdk.ViewState(
        latitude=float(plot_df["latitude"].mean()),
        longitude=float(plot_df["longitude"].mean()),
        zoom=9,
        pitch=0,
    )
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=plot_df,
        get_position="[longitude, latitude]",
        get_radius=800,
        get_fill_color=[180, 60, 40, 160],
        pickable=True,
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip={"text": "{tooltip_label}"},
        )
    )
    if clean_text(query_payload.get("DevelopmentAddress")):
        st.caption(f"Query site context: {clean_text(query_payload.get('DevelopmentAddress'))}")


def render_strategy_tab(df: pd.DataFrame) -> None:
    results = st.session_state.get("copilot_results", {})
    if not results:
        st.info("Run a search first.")
        return
    ranked = results["ranked"]
    selected = selected_cases_from_state(ranked)
    query_payload = st.session_state.get("copilot_query", {})

    st.subheader("Pinned / Selected Precedents")
    if selected.empty:
        st.info("No cases selected.")
        return
    selected_preview = selected[
        [
            c
            for c in [
                "case_key",
                "PlanningAuthority",
                "ApplicationNumber",
                "Decision",
                "hybrid_score",
                "match_reasons",
            ]
            if c in selected.columns
        ]
    ].copy()
    if "hybrid_score" in selected_preview.columns:
        selected_preview["hybrid_score"] = selected_preview["hybrid_score"].map(lambda v: round(float(v), 3))
    st.dataframe(selected_preview, use_container_width=True, hide_index=True)

    generated_pack = generate_strategy_pack(query_payload, selected, ranked)
    if not st.session_state.get("strategy_pack_text"):
        st.session_state["strategy_pack_text"] = generated_pack

    st.subheader("Editable Strategy Pack")
    st.session_state["strategy_pack_text"] = st.text_area(
        "Strategy pack draft",
        value=st.session_state["strategy_pack_text"],
        height=520,
    )
    st.download_button(
        "Download strategy pack",
        data=st.session_state["strategy_pack_text"],
        file_name="planning_precedent_strategy_pack.md",
        mime="text/markdown",
    )
    st.caption("This draft is evidence-backed but still requires consultant review before client issue or application submission.")


def main() -> None:
    init_state()
    st.set_page_config(page_title="Planning Precedent Copilot", layout="wide")
    st.title("Planning Precedent Copilot")
    st.caption("Consultant-facing precedent search for Irish GE10 housing cases with cited refusals, FI issues, local comparables, and an editable strategy pack.")

    with st.sidebar:
        st.header("Settings")
        csv_path = st.text_input("CSV path", value=DEFAULT_CSV)
        top_k = st.slider("Results per tab", min_value=5, max_value=25, value=10, step=1)

    try:
        df = load_data(csv_path)
    except Exception as exc:
        st.error(str(exc))
        return
    try:
        risk_model = load_risk_model()
    except Exception as exc:
        risk_model = None
        st.warning(f"Risk model unavailable: {exc}")
    revision_evidence = load_revision_evidence()
    canonical_revision_records = load_canonical_revision_records()
    refusal_index = load_refusal_theme_index()
    zoning_layers = load_zoning_layers()
    verified_rules = load_verified_policy_rules()
    policy_chunks = load_policy_chunks()
    structured_bundle = load_structured_candidate() or None
    lever_rates = load_lever_rates()
    lever_contrast = load_lever_contrast()

    artifacts, x = build_index(df)
    st.write(f"Loaded `{len(df):,}` cases from `{csv_path}`.")

    search_mode = st.radio(
        "Query mode",
        options=["Describe a new proposal", "Use an existing case"],
        horizontal=True,
    )
    query_payload, query_idx = build_intake_query(df, search_mode)

    if st.button("Run precedent search", type="primary"):
        if query_idx is None and not clean_text(query_payload.get("DevelopmentDescription")):
            st.warning("Enter a proposal description before searching.")
            return
        results = run_search(df, artifacts, x, query_payload, query_idx, top_k)
        st.session_state["copilot_results"] = results
        st.session_state["copilot_query"] = query_payload
        st.session_state["strategy_pack_text"] = ""
        if risk_model is not None and query_idx is None:
            repo = st.session_state["planning_repo"]
            site = {
                "address": query_payload.get("DevelopmentAddress"),
                "planning_authority": query_payload.get("PlanningAuthority"),
                "latitude": query_payload.get("latitude"),
                "longitude": query_payload.get("longitude"),
            }
            scheme = {
                "proposal_type": query_payload.get("ApplicationType"),
                "project_description": query_payload.get("DevelopmentDescription"),
                "units": query_payload.get("units_total_best"),
                "max_storeys": query_payload.get("max_storeys_best"),
                "site_area_sqm": None if not query_payload.get("site_area_ha_best") else float(query_payload["site_area_ha_best"]) * 10000,
                "submission_year": query_payload.get("received_year"),
                **{key: query_payload.get(key) for key in ["max_height_m", "upper_floor_setback_m", "density_units_per_ha", "parking_spaces", "bicycle_spaces", "private_open_space_sqm", "communal_open_space_sqm"]},
            }
            site_id = repo.create_site(site)
            scheme_id = repo.create_scheme(site_id, scheme)
            score = predict_and_record(repo, scheme_id, site, scheme, risk_model)
            st.session_state["baseline_scheme"] = {"site_id": site_id, "scheme_id": scheme_id, "site": site, "snapshot": scheme}
            st.session_state["baseline_score"] = score

    results = st.session_state.get("copilot_results", {})
    if not results:
        st.info("Complete the intake and run the precedent search.")
        return

    render_metrics(results)
    if risk_model is not None:
        render_planning_risk_report(build_planning_risk_report(st.session_state.get("copilot_query", {}), results, risk_model))
    render_summary(results)

    tab_best, tab_refused, tab_grants, tab_fi, tab_map, tab_pack, tab_scenarios = st.tabs(
        ["Best Matches", "Refusals", "Grants", "FI Requests", "Map", "Strategy Pack", "Scenario Testing"]
    )
    with tab_best:
        render_results_table("Closest Overall Precedents", results["overall"], top_k)
        render_results_table("Closest Local Precedents", results["local"], min(top_k, 8))
    with tab_refused:
        render_results_table("Closest Refusal Precedents", results["refusals"], top_k)
    with tab_grants:
        render_results_table("Closest Granted Precedents", results["grants"], top_k)
    with tab_fi:
        render_results_table("Closest FI Precedents", results["fi"], top_k)
    with tab_map:
        render_map_tab(results, st.session_state.get("copilot_query", {}))
    with tab_pack:
        render_strategy_tab(df)
    with tab_scenarios:
        render_scenario_testing(
            st.session_state.get("baseline_scheme", {}),
            st.session_state.get("baseline_score", {}),
            risk_model,
            st.session_state.get("planning_repo"),
            revision_evidence,
            df,
            artifacts,
            x,
            refusal_index,
            zoning_layers,
            verified_rules,
            policy_chunks,
            canonical_revision_records,
            structured_bundle,
            lever_rates,
            lever_contrast,
        )


if __name__ == "__main__":
    main()
