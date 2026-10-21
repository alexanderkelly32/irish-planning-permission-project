import unittest

from check_structured_readiness import TARGETS, build_readiness, count_extraction_values, COLUMN_KEYS


class StructuredReadinessTests(unittest.TestCase):
    def test_build_readiness_blocked_when_below_targets(self):
        counts = {"reports": 100}
        for field, target in TARGETS.items():
            counts[field] = 0
        readiness = build_readiness(counts)
        self.assertEqual(readiness["status"], "blocked_on_insufficiency")
        self.assertIn("BLOCKED", readiness["verdict"])
        self.assertEqual(readiness["fields"]["max_height_m"]["values"], 0)
        self.assertEqual(readiness["fields"]["max_height_m"]["target"], 300)

    def test_build_readiness_ready_when_all_targets_met(self):
        counts = {"reports": 1000}
        for field, target in TARGETS.items():
            counts[field] = target
        readiness = build_readiness(counts)
        self.assertEqual(readiness["status"], "ready")
        self.assertTrue(all(field["met"] for field in readiness["fields"].values()))

    def test_column_key_mapping_covers_all_fields(self):
        self.assertEqual(set(COLUMN_KEYS), set(TARGETS))


if __name__ == "__main__":
    unittest.main()
