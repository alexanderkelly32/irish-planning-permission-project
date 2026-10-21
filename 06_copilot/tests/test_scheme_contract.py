import unittest

from scheme_contract import FIELD_SUPPORT, validate_scheme, validate_site


class SchemeContractTests(unittest.TestCase):
    def test_valid_scheme_is_canonicalised(self):
        values, errors = validate_scheme(
            {
                "development_type": "residential",
                "proposal_type": "new build",
                "units": "42",
                "max_storeys": 5,
                "max_height_m": 16.2,
                "parking_spaces": 42,
                "project_description": " Apartments with communal open space ",
            }
        )
        self.assertEqual(errors, [])
        self.assertEqual(values["units"], 42)
        self.assertEqual(values["max_storeys"], 5.0)
        self.assertEqual(values["project_description"], "Apartments with communal open space")

    def test_negative_measurement_is_rejected(self):
        values, errors = validate_scheme({"units": 10, "max_height_m": -1})
        self.assertIsNone(values["max_height_m"])
        self.assertTrue(any("max_height_m" in error for error in errors))

    def test_invalid_numeric_value_is_rejected(self):
        values, errors = validate_scheme({"units": "many"})
        self.assertIsNone(values["units"])
        self.assertTrue(any("units" in error for error in errors))

    def test_support_registry_does_not_overclaim_v3(self):
        self.assertEqual(FIELD_SUPPORT["units"], "derived_model_active")
        self.assertEqual(FIELD_SUPPORT["max_height_m"], "captured_only")
        self.assertEqual(FIELD_SUPPORT["parking_spaces"], "retrieval_only")
        self.assertEqual(FIELD_SUPPORT["project_description"], "model_active")

    def test_site_requires_address_and_authority(self):
        values, errors = validate_site({"address": "12 Main Street"})
        self.assertEqual(values["address"], "12 Main Street")
        self.assertTrue(any("planning_authority" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
