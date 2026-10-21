import unittest

import pandas as pd

from recommendation_grader import (
    band_for_value,
    build_recommendation,
    direction_label,
    field_delta_statistics,
    grade_evidence,
    grade_scenario,
    most_common_change_ranking,
    observed_rate_contrast,
    rerank_by_themes,
    suggested_levers,
    theme_conditioned_direction,
)


class RecommendationGraderTests(unittest.TestCase):
    def test_direction_labels(self):
        self.assertEqual(direction_label("max_storeys", 5, 4), "reduce")
        self.assertEqual(direction_label("units", 20, 30), "increase")
        self.assertEqual(direction_label("parking_spaces", None, 10), "changed")
        self.assertEqual(direction_label("units", 20, 20), "unchanged")

    def test_grade_requires_all_three_for_strong(self):
        self.assertEqual(grade_evidence(5.0, 3, 1, True, True), "strong")
        self.assertEqual(grade_evidence(5.0, 3, 1, True, False), "strong")
        self.assertEqual(grade_evidence(5.0, 1, 0, False, True), "moderate")
        self.assertEqual(grade_evidence(5.0, 0, 0, False, False), "weak")
        self.assertEqual(grade_evidence(1.0, 5, 5, True, True), "none")
        self.assertEqual(grade_evidence(None, 5, 5, True, True), "none")

    def test_strong_prefers_annotation_plus_precedent(self):
        self.assertEqual(grade_evidence(5.0, 0, 1, True, False), "strong")

    def test_build_recommendation_lines_up_reasons_and_wording(self):
        recommendation = build_recommendation(
            "max_storeys",
            {"from": 5, "to": 4},
            structured_delta_pp=-6.0,
            v3_delta_pp=None,
            revision_pairs=3,
            annotation_verified=1,
            precedent_support=True,
            policy_support=False,
        )
        self.assertEqual(recommendation["direction"], "reduce")
        self.assertEqual(recommendation["grade"], "strong")
        self.assertIn("Strong", recommendation["grade_label"])
        self.assertTrue(any("3 audited" in reason for reason in recommendation["reasons"]))
        self.assertTrue(any("modelled refusal risk changes by -6.0" in reason for reason in recommendation["reasons"]))

    def test_no_movement_yields_none_grade(self):
        recommendation = build_recommendation(
            "parking_spaces",
            {"from": 40, "to": 30},
            structured_delta_pp=-1.0,
            v3_delta_pp=-0.5,
            revision_pairs=2,
            annotation_verified=0,
            precedent_support=True,
            policy_support=True,
        )
        self.assertEqual(recommendation["grade"], "none")

    def test_grade_scenario_ranks_strong_first(self):
        recommendations = grade_scenario(
            ["max_storeys", "units", "parking_spaces"],
            {
                "max_storeys": {"from": 5, "to": 4},
                "units": {"from": 40, "to": 36},
                "parking_spaces": {"from": 40, "to": 30},
            },
            structured_scores={"before": 0.59, "after": 0.53},
            v3_scores=None,
            canonical_summary={
                "field_groups": [
                    {"field": "max_storeys", "matched_count": 21, "same_direction_count": 17},
                    {"field": "units", "matched_count": 50, "same_direction_count": 21},
                    {"field": "parking_spaces", "matched_count": 0, "same_direction_count": 0},
                ]
            },
            policy_comparison=True,
        )
        grades = [item["grade"] for item in recommendations]
        self.assertIn("strong", grades)
        self.assertEqual(grades, sorted(grades, key=lambda g: {"strong": 0, "moderate": 1, "weak": 2, "none": 3}[g]))

    def test_grade_scenario_handles_missing_scores(self):
        recommendations = grade_scenario(
            ["max_storeys"],
            {"max_storeys": {"from": 5, "to": 4}},
            structured_scores=None,
            v3_scores=None,
            canonical_summary=None,
        )
        self.assertEqual(recommendations[0]["grade"], "none")

    def test_band_lookup_and_observed_contrast(self):
        rates = {
            "max_storeys": [
                {"band": "4", "cases": 472, "observed_grant_rate": 0.7352},
                {"band": "5+", "cases": 729, "observed_grant_rate": 0.6914},
            ],
        }
        self.assertEqual(band_for_value(rates, "max_storeys", 4), "4")
        self.assertEqual(band_for_value(rates, "max_storeys", 7), "5+")
        self.assertIsNone(band_for_value(rates, "max_storeys", None))
        contrast = observed_rate_contrast(rates, "max_storeys", 5, 4)
        self.assertIn("73.5%", contrast)
        self.assertIn("69.1%", contrast)
        self.assertIn("not causal", contrast)
        self.assertIsNone(observed_rate_contrast(rates, "max_storeys", 4, 4))
        self.assertIsNone(observed_rate_contrast(rates, "max_height_m", 10, 8))

    def _records(self):
        return pd.DataFrame([
            {
                "original_case_key": "case_a",
                "feature_delta_json": '{"units_total_best": {"delta": -5.0, "from": 40.0, "to": 35.0}, "max_storeys_best": {"delta": -1.0, "from": 5.0, "to": 4.0}}',
            },
            {
                "original_case_key": "case_b",
                "feature_delta_json": '{"units_total_best": {"delta": -8.0, "from": 50.0, "to": 42.0}, "max_storeys_best": {"delta": 2.0, "from": 2.0, "to": 4.0}}',
            },
            {
                "original_case_key": "case_c",
                "feature_delta_json": '{"units_total_best": {"delta": -4.0, "from": 30.0, "to": 26.0}, "parking_spaces_best": {"delta": 3.0, "from": 10.0, "to": 13.0}}',
            },
            {
                "original_case_key": "case_d",
                "feature_delta_json": '{"parking_spaces_best": {"delta": 1.0, "from": 20.0, "to": 21.0}}',
            },
        ])

    def test_most_common_change_ranking_counts_material_deltas_only(self):
        ranking = most_common_change_ranking(self._records())
        self.assertEqual(ranking[0][0], "units")
        self.assertEqual(ranking[0][1], "down")
        self.assertEqual(ranking[0][3], 3)
        self.assertEqual(ranking[1][0], "max_storeys")
        self.assertEqual(ranking[1][3], 2)
        self.assertEqual(ranking[2][0], "parking_spaces")
        self.assertEqual(ranking[2][3], 1)

    def test_most_common_change_ranking_respects_leave_one_out(self):
        ranking = most_common_change_ranking(self._records(), exclude_case_keys={"case_a"})
        self.assertEqual(ranking[0][0], "units")
        self.assertEqual(ranking[0][3], 2)
        self.assertEqual(ranking[0][2], 2)
        fields = [entry[0] for entry in ranking]
        self.assertIn("max_storeys", fields)

    def test_rerank_by_themes_promotes_supported_fields_within_window(self):
        ranking = [
            ("units", "down", 3, 3),
            ("parking_spaces", "up", 2, 2),
            ("max_storeys", "down", 1, 1),
            ("total_gfa_sqm", "down", 1, 1),
        ]
        reranked = rerank_by_themes(
            ranking,
            ["traffic_access"],
            {"traffic_access": ["parking_spaces"]},
            limit=3,
            window=3,
        )
        self.assertEqual(reranked[0][0], "parking_spaces")
        self.assertIn("units", [entry[0] for entry in reranked])

    def test_rerank_by_themes_never_promotes_outside_window(self):
        ranking = [
            ("units", "down", 3, 3),
            ("parking_spaces", "up", 2, 2),
            ("max_storeys", "down", 1, 1),
            ("total_gfa_sqm", "down", 1, 1),
        ]
        reranked = rerank_by_themes(
            ranking,
            ["traffic_access"],
            {"traffic_access": ["total_gfa_sqm"]},
            limit=3,
            window=3,
        )
        self.assertEqual(len(reranked), 3)
        self.assertNotIn("total_gfa_sqm", [entry[0] for entry in reranked])

    def test_suggested_levers_excludes_changed_fields_and_reports_support(self):
        suggestions = suggested_levers(
            self._records(),
            ["traffic_access"],
            {"traffic_access": ["parking_spaces"]},
            changed_fields={"units"},
            limit=5,
        )
        self.assertTrue(suggestions)
        self.assertNotIn("units", [item["field"] for item in suggestions])
        parking = next(item for item in suggestions if item["field"] == "parking_spaces")
        self.assertEqual(parking["direction"], "increase")
        self.assertEqual(parking["total_count"], 1)
        self.assertEqual(parking["theme_support"], 1)
        self.assertEqual(parking["supported_by_themes"], ["traffic_access"])

    def test_suggested_levers_without_themes_returns_most_common(self):
        suggestions = suggested_levers(
            self._records(),
            [],
            {},
            changed_fields=set(),
            limit=5,
        )
        self.assertEqual(suggestions[0]["field"], "units")
        self.assertEqual(suggestions[0]["direction"], "reduce")

    def _themed_records(self):
        return pd.DataFrame([
            {
                "original_case_key": "case_a",
                "refusal_themes_original": "density_scale",
                "feature_delta_json": '{"units_total_best": {"delta": -5.0, "from": 40.0, "to": 35.0}}',
            },
            {
                "original_case_key": "case_b",
                "refusal_themes_original": "traffic_access",
                "feature_delta_json": '{"units_total_best": {"delta": -8.0, "from": 50.0, "to": 42.0}}',
            },
            {
                "original_case_key": "case_c",
                "refusal_themes_original": "traffic_access",
                "feature_delta_json": '{"units_total_best": {"delta": 4.0, "from": 30.0, "to": 34.0}}',
            },
            {
                "original_case_key": "case_d",
                "refusal_themes_original": "traffic_access",
                "feature_delta_json": '{"units_total_best": {"delta": 6.0, "from": 30.0, "to": 36.0}}',
            },
        ])

    def test_field_delta_statistics_reports_median_per_direction(self):
        stats = field_delta_statistics(self._themed_records())
        units = stats["units"]
        self.assertEqual(units["down"]["median"], -6.5)
        self.assertEqual(units["down"]["count"], 2)
        self.assertEqual(units["up"]["median"], 5.0)
        self.assertEqual(units["up"]["count"], 2)

    def test_theme_conditioned_direction_flips_on_theme_evidence(self):
        theme_map = {"density_scale": ["units"], "traffic_access": ["units"]}
        conditioned = theme_conditioned_direction(
            self._themed_records(), "units", ["traffic_access"], theme_map, min_theme_pairs=2,
        )
        self.assertEqual(conditioned, "up")
        weak = theme_conditioned_direction(
            self._themed_records(), "units", ["density_scale"], theme_map, min_theme_pairs=2,
        )
        self.assertIsNone(weak)
        unmapped = theme_conditioned_direction(
            self._themed_records(), "units", ["water_wastewater"], theme_map, min_theme_pairs=2,
        )
        self.assertIsNone(unmapped)

    def test_theme_conditioned_direction_respects_leave_one_out(self):
        theme_map = {"traffic_access": ["units"]}
        conditioned = theme_conditioned_direction(
            self._themed_records(), "units", ["traffic_access"], theme_map,
            min_theme_pairs=2, exclude_case_keys={"case_b", "case_c"},
        )
        self.assertIsNone(conditioned)
        conditioned = theme_conditioned_direction(
            self._themed_records(), "units", ["traffic_access"], theme_map,
            min_theme_pairs=2, exclude_case_keys={"case_d"},
        )
        self.assertEqual(conditioned, "up")

    def test_suggested_levers_uses_theme_conditioned_direction_and_median(self):
        suggestions = suggested_levers(
            self._themed_records(),
            ["traffic_access"],
            {"traffic_access": ["units"]},
            limit=5,
        )
        units = next(item for item in suggestions if item["field"] == "units")
        self.assertEqual(units["direction"], "increase")
        self.assertEqual(units["direction_source"], "theme_conditioned")
        self.assertEqual(units["median_observed_delta"], 5.0)
        self.assertEqual(units["median_delta_count"], 2)


if __name__ == "__main__":
    unittest.main()
