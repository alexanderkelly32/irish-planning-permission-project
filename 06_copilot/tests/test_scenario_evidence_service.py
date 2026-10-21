import unittest

import pandas as pd

from find_similar_developments import fit_search_artifacts, transform_rows
from scenario_evidence_service import (
    build_scenario_evidence_query,
    summarize_revision_evidence_for_changes,
    select_revision_evidence_for_changes,
    summarize_scenario_evidence,
)
from scenario_evidence_service import retrieve_scenario_evidence


class ScenarioEvidenceServiceTests(unittest.TestCase):
    def test_builds_retrieval_query_from_submission_time_site_and_scheme_fields(self):
        query = build_scenario_evidence_query(
            {
                "planning_authority": "Example Council",
                "address": "1 Example Road",
                "itm_easting": 700000,
                "itm_northing": 730000,
            },
            {
                "application_type": "Permission",
                "project_description": "40 apartments",
                "units": 40,
                "max_storeys": 6,
                "site_area_sqm": 12500,
                "submission_year": 2026,
                "decision": "REFUSED",
            },
        )

        self.assertEqual(query["PlanningAuthority"], "Example Council")
        self.assertEqual(query["units_total_best"], 40)
        self.assertEqual(query["site_area_ha_best"], 1.25)
        self.assertNotIn("decision", query)

    def test_summarizes_outcomes_themes_and_case_citations_from_ranked_precedents(self):
        ranked = pd.DataFrame(
            [
                {
                    "hybrid_score": 0.91,
                    "case_key": "a__1",
                    "PlanningAuthority": "Example Council",
                    "ApplicationNumber": "A/1",
                    "Decision": "Conditional",
                    "decision_normalized": "GRANTED",
                    "case_top_primary_tag": "design_layout",
                    "case_primary_tags": "design_layout",
                    "match_reasons": "same authority",
                    "source_url": "https://example.test/a1",
                },
                {
                    "hybrid_score": 0.87,
                    "case_key": "a__2",
                    "PlanningAuthority": "Example Council",
                    "ApplicationNumber": "A/2",
                    "Decision": "Refused",
                    "decision_normalized": "REFUSED",
                    "case_top_primary_tag": "traffic_access",
                    "case_primary_tags": "traffic_access;design_layout",
                    "match_reasons": "same authority | similar scale",
                    "source_url": "https://example.test/a2",
                },
            ]
        )

        summary = summarize_scenario_evidence(ranked, top_k=2)

        self.assertEqual(summary["comparable_count"], 2)
        self.assertEqual(summary["outcome_mix"], {"granted": 1, "refused": 1, "other": 0})
        self.assertEqual(summary["top_comparables"][0]["case_key"], "a__1")
        self.assertEqual(summary["top_comparables"][1]["match_reasons"], "same authority | similar scale")
        self.assertIn("traffic_access", [theme["tag"] for theme in summary["refusal_themes"]])

    def test_summarizes_empty_result_set_without_inventing_evidence(self):
        summary = summarize_scenario_evidence(pd.DataFrame(), top_k=5)

        self.assertEqual(summary["comparable_count"], 0)
        self.assertEqual(summary["outcome_mix"], {"granted": 0, "refused": 0, "other": 0})
        self.assertEqual(summary["refusal_themes"], [])
        self.assertEqual(summary["top_comparables"], [])

    def test_retrieves_evidence_from_raw_cases_without_requiring_ui_normalization(self):
        cases = pd.DataFrame(
            [
                {"case_key": "a__1", "PlanningAuthority": "Council A", "ApplicationNumber": "A/1", "ApplicationType": "Permission", "Decision": "Conditional", "DevelopmentDescription": "40 apartment homes", "units_total_best": 40, "case_top_primary_tag": ""},
                {"case_key": "a__2", "PlanningAuthority": "Council A", "ApplicationNumber": "A/2", "ApplicationType": "Permission", "Decision": "Refused", "DevelopmentDescription": "42 apartment homes", "units_total_best": 42, "case_top_primary_tag": "traffic_access"},
                {"case_key": "b__1", "PlanningAuthority": "Council B", "ApplicationNumber": "B/1", "ApplicationType": "Permission", "Decision": "Refused", "DevelopmentDescription": "single rural dwelling", "units_total_best": 1, "case_top_primary_tag": ""},
            ]
        )
        artifacts = fit_search_artifacts(cases)
        result = retrieve_scenario_evidence(
            cases,
            artifacts,
            transform_rows(cases, artifacts),
            {"planning_authority": "Council A", "address": "Example Road"},
            {"project_description": "40 apartment homes", "units": 40},
            top_k=2,
        )

        self.assertEqual(result["summary"]["comparable_count"], 2)
        self.assertEqual(result["summary"]["top_comparables"][0]["case_key"], "a__1")

    def test_selects_only_revision_evidence_relevant_to_changed_fields(self):
        evidence = pd.DataFrame([
            {
                "original_case_key": "a__1", "revised_case_key": "a__2",
                "change_layout_design": True, "change_access_parking": False,
                "change_open_space_amenity": False, "change_drainage_environment": False,
                "change_policy_land_use": False, "annotation_confidence": "high",
                "source_backed_change_note": "Units reduced from 20 to 16.",
            },
            {
                "original_case_key": "b__1", "revised_case_key": "b__2",
                "change_layout_design": False, "change_access_parking": True,
                "change_open_space_amenity": False, "change_drainage_environment": False,
                "change_policy_land_use": False, "annotation_confidence": "medium",
                "source_backed_change_note": "Access relocated.",
            },
        ])

        selected = select_revision_evidence_for_changes(evidence, ["parking_spaces"])

        self.assertEqual(selected["revised_case_key"].tolist(), ["b__2"])
        self.assertEqual(selected.loc[0, "matched_change_categories"], "access_parking")

    def test_builds_source_linked_non_causal_revision_evidence_summary(self):
        evidence = pd.DataFrame([{
            "original_case_key": "a__1", "revised_case_key": "a__2",
            "original_source_url": "https://example.test/original",
            "revised_source_url": "https://example.test/revised",
            "change_layout_design": True, "change_access_parking": False,
            "change_open_space_amenity": False, "change_drainage_environment": False,
            "change_policy_land_use": False, "annotation_confidence": "high",
            "evidence_scope": "partial_support",
            "source_backed_change_note": "The revised scheme reduced the unit count.",
        }])

        summary = summarize_revision_evidence_for_changes(evidence, ["units"], limit=3)

        self.assertEqual(summary["matching_pair_count"], 1)
        self.assertEqual(summary["cases"][0]["original_source_url"], "https://example.test/original")
        self.assertEqual(summary["cases"][0]["matched_change_categories"], ["layout_design"])
        self.assertIn("does not prove", summary["disclaimer"])

    def test_revision_evidence_summary_is_empty_for_unsupported_changed_field(self):
        summary = summarize_revision_evidence_for_changes(pd.DataFrame(), ["max_height_m"])

        self.assertEqual(summary["matching_pair_count"], 0)
        self.assertEqual(summary["cases"], [])

    def test_revision_evidence_ranks_matching_numeric_change_direction_first(self):
        evidence = pd.DataFrame([
            {
                "original_case_key": "increase", "revised_case_key": "increase_r",
                "change_layout_design": True, "change_access_parking": False,
                "change_open_space_amenity": False, "change_drainage_environment": False,
                "change_policy_land_use": False, "annotation_confidence": "high",
                "source_backed_change_note": "Units increased.", "observed_units_delta": 5,
            },
            {
                "original_case_key": "decrease", "revised_case_key": "decrease_r",
                "change_layout_design": True, "change_access_parking": False,
                "change_open_space_amenity": False, "change_drainage_environment": False,
                "change_policy_land_use": False, "annotation_confidence": "medium",
                "source_backed_change_note": "Units reduced.", "observed_units_delta": -4,
            },
        ])

        summary = summarize_revision_evidence_for_changes(
            evidence,
            ["units"],
            scenario_delta={"units": {"from": 40, "to": 35}},
        )

        self.assertEqual(summary["cases"][0]["original_case_key"], "decrease")
        self.assertEqual(summary["cases"][0]["direction_match_fields"], ["units"])
        self.assertEqual(summary["cases"][1]["direction_mismatch_fields"], ["units"])


if __name__ == "__main__":
    unittest.main()
