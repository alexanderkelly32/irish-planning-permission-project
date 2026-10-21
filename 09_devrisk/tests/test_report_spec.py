import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.reporting import report_spec  # noqa: E402


class ReportSpecTests(unittest.TestCase):
    def test_statement_classification(self):
        statement = report_spec.Statement("The proposal comprises 184 units.", "observed_fact", evidence="register row 1")
        self.assertEqual(statement.classification, "observed_fact")
        with self.assertRaises(ValueError):
            report_spec.Statement("x", "opinion")

    def test_probability_statement_has_eight_fields(self):
        prob = report_spec.probability_statement(
            "ultimate refusal", "not applicable", "submission", 0.18,
            snapshot="2026-09-27", uncertainty="band CI 0.15-0.21",
            model_version="national_residential_v4_full", coverage="all residential",
        )
        required = {"event", "horizon", "clock_origin", "information_snapshot", "estimate",
                    "uncertainty", "model_version", "coverage_limitation"}
        self.assertEqual(required, set(prob.keys()))

    def test_module_availability_abstains(self):
        availability = report_spec.module_availability({}, {"identity_confirmed": True})
        self.assertEqual(availability["identity_snapshot"], "available")
        self.assertEqual(availability["grant_conditions"], "unavailable")

    def test_validate_report_structure(self):
        report = {
            "as_of": "2026-09-27",
            "scheme_id": "S1",
            "modules": {},
            "statements": [{"text": "x", "classification": "unknown"}],
            "probabilities": [
                report_spec.probability_statement("e", "24m", "grant", 0.5, snapshot="s",
                                                 uncertainty="u", model_version="v", coverage="c")
            ],
        }
        self.assertEqual(report_spec.validate_report_structure(report), [])

    def test_validate_catches_unclassified(self):
        report = {"as_of": "2026-09-27", "scheme_id": "S1", "modules": {},
                  "statements": [{"text": "x", "classification": "vibes"}], "probabilities": []}
        errors = report_spec.validate_report_structure(report)
        self.assertTrue(any("classification" in error for error in errors))


class DriverExplanationTests(unittest.TestCase):
    def test_feature_groups_exist(self):
        from devrisk.reporting.driver_explanation import FEATURE_GROUPS, _group_of

        self.assertEqual(_group_of("txt__access"), "description_text")
        self.assertEqual(_group_of("comp_top5_refusal_rate"), "comparables")
        self.assertEqual(_group_of("authority_prior_12m_refusal_rate"), "history_context")
        self.assertEqual(_group_of("flood_any"), "flood")

    def test_explain_returns_structured_payload(self):
        from devrisk.reporting.driver_explanation import explain

        proposal = {
            "authority": "Dun Laoghaire Rathdown County Council",
            "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
            "units": 12,
            "site_area_sqm": 4000,
            "floor_area_sqm": 2400,
            "itm_easting": 722000,
            "itm_northing": 726500,
            "submission_year": 2026,
        }
        payload = explain(proposal)
        self.assertIn("top_raising", payload)
        self.assertIn("top_lowering", payload)
        self.assertIn("group_contributions", payload)
        self.assertIn("counterfactuals", payload)
        self.assertTrue(0.0 <= payload["calibrated_probability"] <= 1.0)
        self.assertAlmostEqual(payload["raw_ranking_score"],
                               1.0 / (1.0 + __import__("math").exp(-payload["native_logit"])), places=4)

    def test_narrative_facts_reproducible(self):
        from devrisk.reporting.driver_explanation import explain, narrative_facts

        proposal = {
            "authority": "Meath County Council",
            "description": "construction of 40 no. houses with a new access road",
            "units": 40,
            "site_area_sqm": 20000,
            "floor_area_sqm": 9000,
            "itm_easting": 701000,
            "itm_northing": 745000,
            "submission_year": 2026,
        }
        payload = explain(proposal)
        facts_a = narrative_facts(payload)
        facts_b = narrative_facts(payload)
        self.assertEqual(facts_a, facts_b)


if __name__ == "__main__":
    unittest.main()
