import json
import unittest

import pandas as pd

from build_lever_contrast import (
    build_lever_contrast,
    granted_arm_levers,
    refused_arm_levers,
    wilson,
)


class LeverContrastTests(unittest.TestCase):
    def _records(self):
        return pd.DataFrame([
            {
                "original_case_key": "g1",
                "feature_delta_json": json.dumps({
                    "units_total_best": {"delta": -5.0, "from": 40.0, "to": 35.0},
                    "max_storeys_best": {"delta": -1.0, "from": 5.0, "to": 4.0},
                }),
            },
            {
                "original_case_key": "g2",
                "feature_delta_json": json.dumps({
                    "units_total_best": {"delta": -8.0, "from": 50.0, "to": 42.0},
                }),
            },
            {
                "original_case_key": "g3",
                "feature_delta_json": json.dumps({
                    "units_total_best": {"delta": -2.0, "from": 30.0, "to": 28.0},
                }),
            },
        ])

    def _audit(self):
        return pd.DataFrame([
            {
                "original_case_key": "r1", "units_delta": -6.0,
                "manual_review_status": "accepted",
            },
            {
                "original_case_key": "r2", "units_delta": 5.0,
                "manual_review_status": "accepted",
            },
            {
                "original_case_key": "r3", "units_delta": -9.0,
                "manual_review_status": "rejected",
            },
        ])

    def test_wilson_bounds(self):
        low, high = wilson(10, 7)
        self.assertLess(low, 0.7)
        self.assertGreater(high, 0.7)
        self.assertEqual(wilson(0, 0), (None, None))

    def test_granted_arm_counts_material_deltas_only(self):
        counts = granted_arm_levers(self._records())
        self.assertEqual(counts[("units_total_best", "down")], 2)
        self.assertEqual(counts[("max_storeys_best", "down")], 1)
        self.assertNotIn(("units_total_best", "up"), counts)

    def test_refused_arm_counts_accepted_rows_only(self):
        counts = refused_arm_levers(self._audit())
        self.assertEqual(counts[("units_total_best", "down")], 1)
        self.assertEqual(counts[("units_total_best", "up")], 1)

    def test_contrast_with_audit(self):
        contrast = build_lever_contrast(self._records(), self._audit())
        self.assertEqual(contrast["status"], "complete")
        rows = {(row["structured_column"], row["direction"]): row for row in contrast["rows"]}
        units_down = rows[("units_total_best", "down")]
        self.assertEqual(units_down["audited_granted_pairs"], 2)
        self.assertEqual(units_down["audited_refused_pairs"], 1)
        self.assertEqual(units_down["audited_total"], 3)
        self.assertEqual(units_down["grant_share"], round(2 / 3, 4))
        self.assertIsNotNone(units_down["wilson_95_low"])

    def test_contrast_blocked_without_audit(self):
        contrast = build_lever_contrast(self._records(), None)
        self.assertEqual(contrast["status"], "blocked_on_audit")
        rows = contrast["rows"]
        self.assertTrue(all(row["audited_refused_pairs"] == 0 for row in rows))
        self.assertTrue(all(row["refused_arm_measured"] is False for row in rows))


if __name__ == "__main__":
    unittest.main()
