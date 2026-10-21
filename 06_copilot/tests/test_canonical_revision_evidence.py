import json
import unittest

import pandas as pd

from scenario_evidence_service import summarize_canonical_revision_evidence


def record_row(original, revised, tier="high", deltas=None, annotation_deltas=None, themes="", confidence=""):
    return {
        "original_case_key": original,
        "revised_case_key": revised,
        "planning_authority": "Example Council",
        "linkage_tier": tier,
        "feature_delta_json": json.dumps(deltas or {}),
        "annotation_observed_delta_json": json.dumps(annotation_deltas or {}),
        "refusal_themes_original": themes,
        "annotation_confidence": confidence,
        "source_backed_change_note": "",
        "original_source_url": "https://example.test/o",
        "revised_source_url": "https://example.test/r",
    }


class CanonicalRevisionEvidenceTests(unittest.TestCase):
    def build_records(self):
        return pd.DataFrame([
            record_row("a", "ar", deltas={"units_total_best": {"from": 40, "to": 36, "delta": -4}}),
            record_row("b", "br", deltas={"units_total_best": {"from": 20, "to": 26, "delta": 6}}),
            record_row("c", "cr", tier="medium", deltas={"max_storeys_best": {"from": 6, "to": 5, "delta": -1}}),
            record_row("d", "dr", themes="design_layout"),
        ])

    def test_counts_and_ranks_same_direction_pairs_first(self):
        records = self.build_records()
        summary = summarize_canonical_revision_evidence(
            records,
            ["units"],
            scenario_delta={"units": {"from": 40, "to": 34}},
            limit=3,
        )
        self.assertEqual(summary["pair_count"], 4)
        group = summary["field_groups"][0]
        self.assertEqual(group["matched_count"], 2)
        self.assertEqual(group["same_direction_count"], 1)
        self.assertEqual(group["median_delta"], 1.0)
        self.assertEqual(group["examples"][0]["original_case_key"], "a")

    def test_field_without_observations_is_honest(self):
        summary = summarize_canonical_revision_evidence(
            self.build_records(),
            ["max_height_m"],
            scenario_delta={"max_height_m": {"from": 16, "to": 14}},
        )
        group = summary["field_groups"][0]
        self.assertEqual(group["matched_count"], 0)
        self.assertIn("No audited revision pair", group["note"])

    def test_annotation_deltas_fall_back_for_matching(self):
        records = pd.DataFrame([
            record_row("a", "ar", annotation_deltas={"observed_units_delta": -4}),
        ])
        summary = summarize_canonical_revision_evidence(
            records,
            ["units"],
            scenario_delta={"units": {"from": 40, "to": 36}},
        )
        group = summary["field_groups"][0]
        self.assertEqual(group["matched_count"], 1)
        self.assertEqual(group["same_direction_count"], 1)

    def test_empty_records_and_disclaimer(self):
        summary = summarize_canonical_revision_evidence(pd.DataFrame(), ["units"], {"units": {"from": 1, "to": 2}})
        self.assertEqual(summary["pair_count"], 0)
        self.assertEqual(summary["field_groups"], [])
        full = summarize_canonical_revision_evidence(self.build_records(), ["units"], {"units": {"from": 1, "to": 2}})
        self.assertIn("does not prove", full["disclaimer"])

    def test_no_scenario_delta_ranks_largest_observed_change_first(self):
        summary = summarize_canonical_revision_evidence(self.build_records(), ["units"], None, limit=3)
        group = summary["field_groups"][0]
        self.assertEqual(group["examples"][0]["original_case_key"], "b")


if __name__ == "__main__":
    unittest.main()
