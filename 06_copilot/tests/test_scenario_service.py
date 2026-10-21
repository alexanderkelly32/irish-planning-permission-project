import unittest

from scenario_service import ScenarioValidationError, mutate_scheme


class ScenarioServiceTests(unittest.TestCase):
    def test_mutation_returns_delta_and_support(self):
        baseline = {"units": 42, "max_height_m": 16.2, "project_description": "Apartments"}
        result = mutate_scheme(baseline, {"units": 40, "max_height_m": 14.0})
        self.assertEqual(result["snapshot"]["units"], 40.0)
        self.assertEqual(result["changed_fields"], ["max_height_m", "units"])
        self.assertEqual(result["support"]["max_height_m"], "captured_only")
        self.assertEqual(result["delta"]["units"], {"from": 42, "to": 40.0})

    def test_unrelated_fields_are_unchanged(self):
        baseline = {"units": 42, "max_height_m": 16.2, "project_description": "Apartments"}
        result = mutate_scheme(baseline, {"units": 40})
        self.assertEqual(result["snapshot"]["max_height_m"], 16.2)
        self.assertEqual(result["snapshot"]["project_description"], "Apartments")

    def test_invalid_or_noop_mutation_is_rejected(self):
        with self.assertRaises(ScenarioValidationError):
            mutate_scheme({"units": 42}, {"units": -1})
        with self.assertRaises(ScenarioValidationError):
            mutate_scheme({"units": 42}, {"units": 42})

    def test_description_mutation_is_language_sensitivity(self):
        result = mutate_scheme({"project_description": "Apartments"}, {"project_description": "Apartments with setback"})
        self.assertEqual(result["support"]["project_description"], "language_sensitivity")


if __name__ == "__main__":
    unittest.main()
