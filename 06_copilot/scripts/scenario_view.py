"""Streamlit presentation for bounded scenario sensitivity testing."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from precedent_copilot_logic import token_set
from scenario_service import ScenarioValidationError, create_scored_scenario
from scenario_evidence_service import (
    retrieve_scenario_evidence,
    summarize_canonical_revision_evidence,
    summarize_revision_evidence_for_changes,
)
from site_evidence_service import summarize_site_evidence
from structured_score_service import score_structured, sensitivity_sweeps
from recommendation_grader import (
    STRUCTURED_TO_SCHEME_FIELD,
    grade_scenario,
    observed_rate_contrast,
    suggested_levers,
)
from theme_lever_bridge import THEME_TO_FIELD

SCHEME_TO_STRUCTURED_FIELD = {field: column for column, field in STRUCTURED_TO_SCHEME_FIELD.items()}

SUGGESTION_UNITS = {
    "units": "units",
    "max_storeys": "storeys",
    "parking_spaces": "spaces",
    "bicycle_spaces": "spaces",
    "site_area_sqm": "sqm",
    "total_gfa_sqm": "sqm",
    "private_open_space_sqm": "sqm",
}


CHANGE_CATEGORY_LABELS = {
    "layout_design": "layout and design",
    "access_parking": "access and parking",
    "open_space_amenity": "open space and amenity",
    "drainage_environment": "drainage and environment",
    "policy_land_use": "policy and land use",
}


def _lever_contrast_line(lever_contrast: dict | None, suggestion: dict) -> str | None:
    """Observational contrast line for a suggested lever, only when the refused arm
    is measured (both audited arms present)."""
    if not lever_contrast or lever_contrast.get("status") != "complete":
        return None
    column = SCHEME_TO_STRUCTURED_FIELD.get(suggestion["field"])
    direction = "up" if suggestion["direction"] == "increase" else "down"
    if column is None:
        return None
    row = next(
        (item for item in lever_contrast.get("rows", [])
         if item["structured_column"] == column and item["direction"] == direction),
        None,
    )
    if row is None or not row.get("refused_arm_measured"):
        return None
    granted = row["audited_granted_pairs"]
    refused = row["audited_refused_pairs"]
    share = row["grant_share"]
    low = row["wilson_95_low"]
    high = row["wilson_95_high"]
    return (
        f"- Audited resubmissions changing {suggestion['field']} in this direction: "
        f"{granted} preceded grants vs {refused} preceded refusals "
        f"(grant share {share * 100:.1f}%, Wilson 95% CI {low * 100:.1f}-{high * 100:.1f}%). "
        "Observational, not causal."
    )


def render_scenario_testing(
    baseline: dict,
    baseline_score: dict,
    model,
    repo,
    revision_evidence: pd.DataFrame | None = None,
    cases_df: pd.DataFrame | None = None,
    artifacts=None,
    case_matrix=None,
    refusal_index: pd.DataFrame | None = None,
    zoning_layers: dict | None = None,
    rules_df: pd.DataFrame | None = None,
    policy_chunks: pd.DataFrame | None = None,
    canonical_records: pd.DataFrame | None = None,
    structured_bundle: dict | None = None,
    lever_rates: dict | None = None,
    lever_contrast: dict | None = None,
) -> None:
    st.subheader("Scenario Testing")
    if not baseline or not baseline_score or model is None or repo is None:
        st.info("Run a new proposal search first to create a persisted baseline scheme.")
        return
    snapshot = baseline["snapshot"]
    st.caption("Scenario changes are modelled sensitivity analysis, holding other model inputs constant; they are not causal guarantees.")

    def default_number(field: str, step: float = 1.0):
        return st.number_input(
            field.replace("_", " ").capitalize(), min_value=0.0,
            value=float(snapshot.get(field) or 0), step=step, key=f"scenario_{field}",
        )

    with st.form("scenario_form"):
        name = st.text_input("Scenario name", value=f"Scenario {len(st.session_state.get('scenario_results', [])) + 1}")
        with st.expander("Scale", expanded=True):
            scale_left, scale_mid, scale_right = st.columns(3)
            with scale_left:
                units = default_number("units")
                max_storeys = default_number("max_storeys")
                site_area = default_number("site_area_sqm")
            with scale_mid:
                height = default_number("max_height_m", step=0.1)
                gfa = default_number("total_gfa_sqm")
                density = default_number("density_units_per_ha")
            with scale_right:
                plot_ratio = default_number("plot_ratio", step=0.1)
                coverage = default_number("site_coverage_pct")
                parking = default_number("parking_spaces")
        with st.expander("Setbacks and context"):
            context_left, context_mid, context_right = st.columns(3)
            with context_left:
                front_setback = default_number("front_setback_m", step=0.1)
                rear_setback = default_number("rear_setback_m", step=0.1)
                side_setback = default_number("side_setback_m", step=0.1)
            with context_mid:
                upper_setback = default_number("upper_floor_setback_m", step=0.1)
                nearest_separation = default_number("nearest_dwelling_separation_m", step=0.1)
            with context_right:
                opposing_separation = default_number("opposing_window_separation_m", step=0.1)
        with st.expander("Amenity and transport"):
            amenity_left, amenity_mid = st.columns(2)
            with amenity_left:
                private_open = default_number("private_open_space_sqm")
                communal_open = default_number("communal_open_space_sqm")
            with amenity_mid:
                bicycles = default_number("bicycle_spaces")
                access_points = default_number("vehicular_access_points")
        with st.expander("Other"):
            demolition = st.checkbox(
                "Demolition proposed",
                value=bool(snapshot.get("demolition_proposed")),
                key="scenario_demolition_proposed",
            )
            housing_type = st.text_input(
                "Housing type", value=str(snapshot.get("housing_type") or ""),
                key="scenario_housing_type",
            )
            unit_mix = st.text_input(
                "Unit mix", value=str(snapshot.get("unit_mix") or ""),
                key="scenario_unit_mix",
            )
            description = st.text_area(
                "Project description", value=str(snapshot.get("project_description") or ""),
                key="scenario_project_description",
            )
        submitted = st.form_submit_button("Run scenario", type="primary")
    if submitted:
        def optional(value):
            return value if value > 0 else None
        numeric_fields = {
            "units": units, "max_storeys": max_storeys, "max_height_m": optional(height),
            "site_area_sqm": optional(site_area), "total_gfa_sqm": optional(gfa),
            "density_units_per_ha": optional(density), "plot_ratio": optional(plot_ratio),
            "site_coverage_pct": optional(coverage), "parking_spaces": optional(parking),
            "front_setback_m": optional(front_setback), "rear_setback_m": optional(rear_setback),
            "side_setback_m": optional(side_setback), "upper_floor_setback_m": optional(upper_setback),
            "nearest_dwelling_separation_m": optional(nearest_separation),
            "opposing_window_separation_m": optional(opposing_separation),
            "private_open_space_sqm": optional(private_open),
            "communal_open_space_sqm": optional(communal_open),
            "bicycle_spaces": optional(bicycles), "vehicular_access_points": optional(access_points),
        }
        changes = {key: value for key, value in numeric_fields.items() if value != snapshot.get(key)}
        if bool(demolition) != bool(snapshot.get("demolition_proposed")):
            changes["demolition_proposed"] = demolition
        for field, value in {
            "housing_type": housing_type, "unit_mix": unit_mix,
            "project_description": description,
        }.items():
            stripped = value.strip()
            if stripped and stripped != (snapshot.get(field) or ""):
                changes[field] = stripped
        try:
            result = create_scored_scenario(
                repo, baseline["scheme_id"], name, snapshot, changes, baseline["site"], model
            )
            st.session_state.setdefault("scenario_results", []).append(result)
        except ScenarioValidationError as exc:
            st.error(str(exc))
    baseline_grant = float(baseline_score.get("grant_probability", 0.0))
    rows = [{"name": "Baseline", "grant_probability": baseline_grant, "delta_pp": 0.0, "changed_fields": "—", "support": "baseline"}]
    for result in st.session_state.get("scenario_results", []):
        grant = float(result["score"].get("grant_probability", 0.0))
        rows.append({
            "name": result["scenario_id"],
            "grant_probability": grant,
            "delta_pp": (grant - baseline_grant) * 100,
            "changed_fields": ", ".join(result["changed_fields"]),
            "support": ", ".join(f"{k}: {v}" for k, v in result["support"].items()),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if not st.session_state.get("scenario_results"):
        return
    st.markdown("#### Audited revision evidence")
    st.caption("Evidence is selected by the categories changed in each scenario. It supports sensitivity analysis, not a causal promise of permission.")
    evidence = revision_evidence if revision_evidence is not None else pd.DataFrame()
    for result in st.session_state.get("scenario_results", []):
        summary = summarize_revision_evidence_for_changes(
            evidence,
            result["changed_fields"],
            limit=3,
            scenario_delta=result.get("delta", {}),
        )
        with st.expander(
            f"{result['scenario_id']}: {summary['matching_pair_count']} relevant audited revision pairs",
            expanded=False,
        ):
            if not summary["cases"]:
                st.info("No audited revision pair currently matches this scenario's changed fields.")
                continue
            st.caption(summary["disclaimer"])
            for index, case in enumerate(summary["cases"]):
                categories = ", ".join(
                    CHANGE_CATEGORY_LABELS.get(category, category.replace("_", " "))
                    for category in case["matched_change_categories"]
                )
                st.write(case["source_backed_change_note"])
                st.caption(
                    f"{categories} · {case['annotation_confidence']} confidence · "
                    f"{case['evidence_scope'].replace('_', ' ')}"
                )
                if case["direction_match_fields"]:
                    st.caption("Same observed change direction: " + ", ".join(case["direction_match_fields"]))
                elif case["direction_mismatch_fields"]:
                    st.caption("Opposite observed change direction: " + ", ".join(case["direction_mismatch_fields"]))
                else:
                    st.caption("Category match only; no comparable numeric direction was available.")
                links = st.columns(2)
                if case["original_source_url"]:
                    links[0].markdown(f"[Original refused application]({case['original_source_url']})")
                if case["revised_source_url"]:
                    links[1].markdown(f"[Revised granted application]({case['revised_source_url']})")

    if canonical_records is not None and not canonical_records.empty:
        st.markdown("#### Audited resubmission statistics")
        st.caption(
            "Observed changes aggregated over manually audited refused-to-revised-to-granted pairs. "
            "An observed change is associated with a later grant; it does not prove causation."
        )
        for result in st.session_state.get("scenario_results", []):
            summary = summarize_canonical_revision_evidence(
                canonical_records,
                result["changed_fields"],
                scenario_delta=result.get("delta", {}),
                limit=3,
            )
            with st.expander(
                f"{result['scenario_id']}: observed changes among {summary['pair_count']} audited resubmissions",
                expanded=False,
            ):
                st.caption(summary["disclaimer"])
                for group in summary["field_groups"]:
                    if group["matched_count"] == 0:
                        st.caption(f"{group['field']}: {group['note']}")
                        continue
                    st.write(
                        f"**{group['field']}**: {group['matched_count']} audited pairs with an observed change "
                        f"(same direction: {group['same_direction_count']}, median delta {group['median_delta']})"
                    )
                    for example in group["examples"]:
                        st.write(f"- {example['citation']} (observed delta {example['observed_delta']})")
                        if example["source_backed_change_note"]:
                            st.caption(example["source_backed_change_note"])
                        links = st.columns(2)
                        if example["original_source_url"]:
                            links[0].markdown(f"[Original refused application]({example['original_source_url']})")
                        if example["revised_source_url"]:
                            links[1].markdown(f"[Revised granted application]({example['revised_source_url']})")

    if canonical_records is not None and not canonical_records.empty:
        st.markdown("#### Suggested next changes")
        st.caption(
            "Suggestions lead with the empirically most common changes observed in audited "
            "refused-to-revised-to-granted resubmissions, re-ranked using the scenario's diagnosed "
            "refusal themes. They are historical observations, not causal advice."
        )
        for result in st.session_state.get("scenario_results", []):
            scenario_themes = themes_by_scenario.get(result["scenario_id"], [])
            suggestions = suggested_levers(
                canonical_records,
                scenario_themes,
                THEME_TO_FIELD,
                changed_fields=set(result["changed_fields"]),
                limit=5,
            )
            with st.expander(
                f"{result['scenario_id']}: empirically most common next changes",
                expanded=False,
            ):
                if not suggestions:
                    st.info("No additional material changes observed among audited resubmissions.")
                    continue
                for suggestion in suggestions:
                    theme_note = ""
                    if suggestion["supported_by_themes"]:
                        theme_note = (
                            " · supported by diagnosed theme(s): "
                            + ", ".join(suggestion["supported_by_themes"])
                        )
                    st.write(
                        f"**{suggestion['direction']} {suggestion['field']}** — observed in "
                        f"{suggestion['total_count']} audited resubmission(s) "
                        f"({suggestion['majority_count']} in this direction)"
                    )
                    lines = [f"- Historical observation{theme_note}; does not prove causation."]
                    median = suggestion.get("median_observed_delta")
                    if median is not None and suggestion.get("median_delta_count"):
                        unit = SUGGESTION_UNITS.get(suggestion["field"], "")
                        median_text = (
                            f"median observed {suggestion['direction']}: {abs(median):g}"
                            + (f" {unit}" if unit else "")
                        )
                        lines.append(
                            f"- {median_text} (n={suggestion['median_delta_count']} audited pairs); "
                            "use only as a starting magnitude."
                        )
                    if suggestion.get("direction_source") == "theme_conditioned":
                        lines.append(
                            "- Direction from audited pairs sharing the same refusal themes; "
                            "otherwise the global majority direction."
                        )
                    contrast = _lever_contrast_line(lever_contrast, suggestion)
                    if contrast:
                        lines.append(contrast)
                    for line in lines:
                        st.caption(line)

    if cases_df is None or artifacts is None or case_matrix is None:
        st.caption("Comparable refused-case themes require the national case index; it is unavailable in this session.")
        return
    st.markdown("#### Comparable refused cases: recurring themes")
    st.caption(
        "Themes are aggregated from extraction-tagged decision documents of comparable "
        "refused cases retrieved for each scenario. They support sensitivity analysis; "
        "they do not predict this scenario's outcome."
    )
    themes_by_scenario: dict[str, list[str]] = {}
    for result in st.session_state.get("scenario_results", []):
        evidence = retrieve_scenario_evidence(
            cases_df,
            artifacts,
            case_matrix,
            baseline["site"],
            result["snapshot"],
            top_k=8,
            refusal_index=refusal_index,
        )
        summary = evidence["summary"]
        themes_by_scenario[result["scenario_id"]] = [
            theme["tag"] for theme in summary.get("refusal_themes", [])
        ]
        with st.expander(
            f"{result['scenario_id']}: refusal themes among top {summary['comparable_count']} comparables",
            expanded=False,
        ):
            st.caption(summary["refusal_theme_coverage_note"])
            themes = summary.get("refusal_themes", [])
            if not themes:
                st.info("No extraction-tagged refusal themes were available among the top comparable refused cases.")
                continue
            for theme in themes:
                st.markdown(
                    f"**{theme['label']}** — {theme['case_count']} refused comparable(s), "
                    f"weighted score {theme['weighted_score']}"
                )
                for source_case in theme.get("cases", []):
                    st.write(f"- {source_case['citation']}")
                    st.caption(
                        f"Source: {source_case['source_file'] or 'not recorded'} · "
                        f"{source_case['extraction_provenance']}"
                    )
                    if source_case["excerpt"]:
                        st.caption(source_case["excerpt"])
                    if source_case["source_url"]:
                        st.markdown(f"[View application details]({source_case['source_url']})")

    if not baseline:
        return
    if structured_bundle:
        st.markdown("#### Experimental structured scheme risk")
        site = baseline.get("site", {})
        baseline_snapshot = baseline.get("snapshot", {})
        try:
            baseline_structured = score_structured(site, baseline_snapshot, structured_bundle)
            rows = [{
                "name": "Baseline",
                "structured_refusal": baseline_structured["refusal_probability"],
                "structured_grant": baseline_structured["grant_probability"],
            }]
            for result in st.session_state.get("scenario_results", []):
                score = score_structured(site, result["snapshot"], structured_bundle)
                rows.append({
                    "name": result["scenario_id"],
                    "structured_refusal": score["refusal_probability"],
                    "structured_grant": score["grant_probability"],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            sweeps = sensitivity_sweeps(site, baseline_snapshot, structured_bundle)
            with st.expander("Sensitivity sweeps (baseline, other inputs constant)", expanded=False):
                for field, sweep in sweeps.items():
                    st.caption(f"{field}: " + " | ".join(
                        f"{row['value']} -> {row['refusal_probability']}" for row in sweep
                    ))
        except Exception as exc:
            st.warning(f"Structured candidate unavailable: {exc}")

        st.markdown("#### Graded recommendations")
        st.caption(
            "Grades combine modelled movement (sensitivity, holding other inputs constant), matched "
            "audited resubmissions and precedent/policy support. They are evidence summaries, not "
            "guarantees or causal claims."
        )
        baseline_grant = float(baseline_score.get("grant_probability", 0.0))
        for result in st.session_state.get("scenario_results", []):
            canonical_summary = summarize_canonical_revision_evidence(
                canonical_records if canonical_records is not None else pd.DataFrame(),
                result["changed_fields"],
                scenario_delta=result.get("delta", {}),
                limit=3,
            )
            v3_scores = {
                "before": 1.0 - baseline_grant,
                "after": 1.0 - float(result["score"].get("grant_probability", baseline_grant)),
            }
            structured_scores = None
            if structured_bundle:
                before = score_structured(site, baseline_snapshot, structured_bundle)
                after = score_structured(site, result["snapshot"], structured_bundle)
                structured_scores = {
                    "before": before["refusal_probability"],
                    "after": after["refusal_probability"],
                }
            recommendations = grade_scenario(
                result["changed_fields"],
                result.get("delta", {}),
                structured_scores,
                v3_scores,
                canonical_summary,
                policy_comparison=bool(rules_df is not None and not rules_df.empty),
            )
            with st.expander(f"{result['scenario_id']}: recommendations", expanded=False):
                for recommendation in recommendations:
                    st.write(
                        f"**{recommendation['direction']} {recommendation['field']}** — "
                        f"{recommendation['grade_label']}"
                    )
                    for reason in recommendation["reasons"]:
                        st.caption(f"- {reason}")
                    field_delta = result.get("delta", {}).get(recommendation["field"], {})
                    contrast = observed_rate_contrast(
                        lever_rates or {}, recommendation["field"],
                        field_delta.get("from"), field_delta.get("to"),
                    )
                    if contrast:
                        st.caption(contrast)

    st.markdown("#### Verified site evidence")
    description_terms = sorted(token_set(baseline.get("snapshot", {}).get("project_description")))
    evidence = summarize_site_evidence(
        baseline.get("site", {}),
        baseline.get("snapshot", {}),
        zoning_layers,
        rules_df,
        policy_chunks,
        passage_terms=description_terms[:8],
    )
    with st.expander("Site evidence", expanded=True):
        zoning = evidence["zoning"]
        if zoning["status"] == "matched":
            st.write(
                f"**Zoning:** {zoning['zone_description'] or zoning['zone_code']} "
                f"({zoning['authority']} {zoning['plan_period']} plan zoning layer)"
            )
        else:
            st.caption(zoning.get("note", ""))
        policy = evidence["policy_standards"]
        if policy["status"] == "available":
            st.caption(f"Verified standards: {policy.get('source_document_label')} ({policy.get('plan_period')})")
            for family in ("apartment_min_floor_area", "communal_amenity_min_per_unit"):
                block = policy.get(family)
                if block:
                    standards = "; ".join(
                        f"{row['subject_type']}: {row['threshold_kind']} {row['threshold_value']} {row['threshold_unit']}"
                        for row in block["standards"]
                    )
                    st.caption(f"{family}: {standards}")
                    st.caption(block["comparison_note"])
            ratio = policy.get("open_space_min_site_ratio", {})
            if ratio.get("status") == "compared":
                verdict = "meets" if ratio["meets_threshold"] else "is below"
                st.write(
                    f"**Open-space ratio:** observed {ratio['observed_ratio']} "
                    f"(site area {ratio['site_area_sqm']} sqm, open space {ratio['open_space_sqm']} sqm) "
                    f"{verdict} the verified minimum {ratio['threshold']} "
                    f"{ratio['threshold_unit']} for {ratio['zone_code']} "
                    f"({ratio['source_document_label']}, p. {ratio['source_page_range']})"
                )
                st.caption(ratio["note"])
            elif ratio.get("status") in {"not_comparable_missing_fields", "zone_not_covered", "not_applicable_authority"}:
                st.caption(ratio.get("note", "No verified open-space standard applies here."))
        elif policy["status"] == "no_verified_rules":
            st.caption(policy["note"])
        st.caption(evidence["flood"]["note"])
        for passage in evidence.get("policy_passages", []):
            st.caption(
                f"Plan passage — {passage['document_label']}, {passage['section_title']} "
                f"(p. {passage['page_range']}): {passage['excerpt']}"
            )
