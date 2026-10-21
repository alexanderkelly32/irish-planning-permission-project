import unittest

from similar_developments_app import pin_widget_key


class SimilarDevelopmentsAppTests(unittest.TestCase):
    def test_pin_keys_are_unique_when_a_case_appears_in_multiple_result_panels(self):
        overall = pin_widget_key("Closest Overall Precedents", "council__123")
        local = pin_widget_key("Closest Local Precedents", "council__123")

        self.assertNotEqual(overall, local)
        self.assertIn("council__123", overall)


if __name__ == "__main__":
    unittest.main()
