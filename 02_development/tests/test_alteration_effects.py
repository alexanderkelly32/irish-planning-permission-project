import unittest

import pandas as pd

import sys
sys.path.insert(0, r"02_development\scripts")

from build_alteration_effects import build_alteration_effects, granted_arm_counts, refused_arm_counts  # noqa: E402


class AlterationEffectsTests(unittest.TestCase):
    def build_canonical(self):
        return pd.DataFrame([
            {"feature_delta_json": '{"max_storeys_best": {"delta": -1.0, "from": 5.0, "to": 4.0}, "units_total_best": {"delta": -5.0, "from": 40.0, "to": 35.0}}'},
            {"feature_delta_json": '{"max_storeys_best": {"delta": -2.0, "from": 6.0, "to": 4.0}}'},
            {"feature_delta_json": '{"units_total_best": {"delta": -2.0, "from": 30.0, "to": 28.0}}'},
        ])

    def build_refused_fixed(self):
        return pd.DataFrame([
            {"manual_review_status": "accepted", "units_delta": -6.0},
            {"manual_review_status": "accepted", "units_delta": -9.0},
            {"manual_review_status": "rejected", "units_delta": -4.0},
            {"manual_review_status": "accepted", "units_delta": 5.0},
        ])

    def build_refused_reports(self):
        return pd.DataFrame([
            {"max_storeys_delta": -1.0, "parking_spaces_delta": None},
            {"max_storeys_delta": None, "parking_spaces_delta": -4.0},
        ])

    def test_granted_arm_counts_material_only(self):
        counts = granted_arm_counts(self.build_canonical())
        self.assertEqual(counts[("max_storeys_best", "down")], 2)
        self.assertEqual(counts[("units_total_best", "down")], 1)

    def _accepted(self, frame):
        return frame[frame["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")]

    def test_refused_arm_counts_units_and_reports(self):
        counts = refused_arm_counts(self._accepted(self.build_refused_fixed()), self.build_refused_reports())
        self.assertEqual(counts[("units_total_best", "down")], 2)
        self.assertEqual(counts[("units_total_best", "up")], 1)
        self.assertEqual(counts[("max_storeys_best", "down")], 1)
        self.assertEqual(counts[("parking_spaces_best", "down")], 1)

    def test_effects_table_ranks_and_computes_shares(self):
        effects = build_alteration_effects(self.build_canonical(), self._accepted(self.build_refused_fixed()), self.build_refused_reports())
        rows = {(row["column"], row["direction"]): row for row in effects["rows"]}
        units_down = rows[("units_total_best", "down")]
        self.assertEqual(units_down["audited_granted"], 1)
        self.assertEqual(units_down["audited_refused"], 2)
        self.assertEqual(units_down["grant_share"], round(1 / 3, 4))
        self.assertTrue(units_down["both_arms_measured"])
        self.assertIsNotNone(units_down["wilson_95_low"])
        self.assertEqual(effects["rows"][0]["column"], "max_storeys_best")


if __name__ == "__main__":
    unittest.main()
