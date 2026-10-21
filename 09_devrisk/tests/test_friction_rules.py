import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.labels import friction  # noqa: E402


class FrictionRuleTests(unittest.TestCase):
    def test_rules_load_from_yaml(self):
        rules = friction.load_rules()
        self.assertIn("version", rules)
        self.assertIn("high_if_any", rules["rules"])

    def test_high_dominates(self):
        result = friction.apply_friction(
            {"judicial_review_observed": True, "fi_requested": True}
        )
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["high_hits"], ["judicial_review_observed"])

    def test_moderate(self):
        result = friction.apply_friction({"fi_requested": True})
        self.assertEqual(result["level"], "moderate")
        self.assertIn("fi_requested", result["moderate_hits"])

    def test_low_when_all_observed_absent(self):
        result = friction.apply_friction(
            {"fi_requested": False, "first_party_appeal": False, "third_party_appeal": False,
             "material_redesign": False, "judicial_review_observed": False,
             "unit_reduction_pct_gte_20": False, "high_impact_precommencement_condition": False}
        )
        self.assertEqual(result["level"], "low")

    def test_unknown_when_components_missing(self):
        result = friction.apply_friction({})
        self.assertEqual(result["level"], "unknown")

    def test_components_retained(self):
        components = {"fi_requested": True, "condition_count": 4}
        result = friction.apply_friction(components)
        self.assertEqual(result["components"], components)

    def test_truthy_variants(self):
        result = friction.apply_friction({"unit_reduction_pct_gte_20": "yes"})
        self.assertEqual(result["level"], "high")


if __name__ == "__main__":
    unittest.main()
