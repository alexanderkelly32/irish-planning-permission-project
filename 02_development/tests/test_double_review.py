import unittest

import pandas as pd

from double_review import (
    build_double_review_slice,
    merge_double_review,
    summarize_double_review,
)


def pilot_row(original, revised, tier, status):
    return {
        "original_case_key": original,
        "revised_case_key": revised,
        "planning_authority": "Example Council",
        "original_application_number": original,
        "revised_application_number": revised,
        "linkage_tier": tier,
        "linkage_score": 0.9,
        "manual_review_status": status,
        "manual_review_notes": "reviewer A note",
        "reviewer": "ReviewerA",
        "reviewed_at": "2026-09-02",
    }


class DoubleReviewSliceTests(unittest.TestCase):
    def build_pilot(self):
        rows = []
        for index in range(12):
            rows.append(pilot_row(f"h{index}", f"h{index}r", "high", "accepted" if index % 3 else "rejected"))
        for index in range(9):
            rows.append(pilot_row(f"m{index}", f"m{index}r", "medium", "accepted"))
        for index in range(6):
            rows.append(pilot_row(f"l{index}", f"l{index}r", "low", "rejected"))
        for index in range(3):
            rows.append(pilot_row(f"p{index}", f"p{index}r", "high", "pending"))
        return pd.DataFrame(rows)

    def test_slice_is_deterministic_and_stratified(self):
        pilot = self.build_pilot()
        first = build_double_review_slice(pilot, per_tier=5, seed=42)
        second = build_double_review_slice(pilot, per_tier=5, seed=42)

        self.assertEqual(first["original_case_key"].tolist(), second["original_case_key"].tolist())
        counts = first["linkage_tier"].value_counts().to_dict()
        self.assertEqual(counts, {"high": 5, "medium": 5, "low": 5})
        self.assertFalse(
            set(first["original_case_key"]).intersection({"p0", "p1", "p2"}),
            "pending rows must not enter the double-review slice",
        )

    def test_slice_masks_reviewer_a_labels(self):
        pilot = self.build_pilot()
        slice_df = build_double_review_slice(pilot, per_tier=3, seed=42)

        for column in ("manual_review_status", "manual_review_notes", "reviewer", "reviewed_at"):
            self.assertNotIn(column, slice_df.columns)
        for column in ("double_review_status", "double_review_notes", "reviewer_b", "reviewed_at_b"):
            self.assertIn(column, slice_df.columns)
            self.assertTrue(slice_df[column].isna().all() or (slice_df[column] == "").all())

    def test_slice_caps_at_available_resolved_rows(self):
        pilot = self.build_pilot()
        slice_df = build_double_review_slice(pilot, per_tier=100, seed=7)
        counts = slice_df["linkage_tier"].value_counts().to_dict()
        self.assertEqual(counts, {"high": 12, "medium": 9, "low": 6})

    def test_missing_required_columns_raise(self):
        with self.assertRaises(ValueError):
            build_double_review_slice(pd.DataFrame([{"case_key": "x"}]))
        with self.assertRaises(ValueError):
            merge_double_review(pd.DataFrame([{"case_key": "x"}]), pd.DataFrame())

    def test_agreement_and_disagreement_are_flag_never_auto_resolved(self):
        pilot = pd.DataFrame([
            pilot_row("a", "ar", "high", "accepted"),
            pilot_row("b", "br", "medium", "rejected"),
            pilot_row("c", "cr", "low", "accepted"),
        ])
        reviewer_b = pd.DataFrame([
            {"original_case_key": "a", "revised_case_key": "ar", "double_review_status": "accepted", "double_review_notes": "agrees"},
            {"original_case_key": "b", "revised_case_key": "br", "double_review_status": "accepted", "double_review_notes": "disagrees"},
            {"original_case_key": "c", "revised_case_key": "cr", "double_review_status": "pending", "double_review_notes": ""},
        ])

        adjudication = merge_double_review(pilot, reviewer_b)
        summary = summarize_double_review(adjudication)

        self.assertTrue(adjudication.loc[0, "agreement"])
        self.assertFalse(adjudication.loc[1, "agreement"])
        self.assertTrue(adjudication.loc[1, "adjudication_required"])
        self.assertEqual(adjudication.loc[1, "adjudicated_status"], "")
        self.assertTrue(adjudication.loc[2, "adjudication_required"], "unresolved reviewer B rows need adjudication")
        self.assertEqual(summary["reviewer_b_resolved_count"], 2)
        self.assertEqual(summary["agreement_count"], 1)
        self.assertEqual(summary["disagreement_count"], 1)
        self.assertEqual(summary["pending_by_b_count"], 1)
        self.assertEqual(summary["adjudication_required_count"], 2)
        self.assertIn("never used to auto-accept", summary["note"])

    def test_rows_outside_the_slice_are_not_adjudication_required(self):
        pilot = pd.DataFrame([pilot_row("a", "ar", "high", "accepted")])
        reviewer_b = pd.DataFrame(columns=["original_case_key", "revised_case_key", "double_review_status", "double_review_notes"])

        adjudication = merge_double_review(pilot, reviewer_b)
        summary = summarize_double_review(adjudication)

        self.assertFalse(adjudication.loc[0, "in_slice"])
        self.assertFalse(adjudication.loc[0, "adjudication_required"])
        self.assertEqual(summary["double_reviewed_count"], 0)
        self.assertEqual(summary["adjudication_required_count"], 0)

    def test_summary_handles_empty_frame(self):
        summary = summarize_double_review(pd.DataFrame())
        self.assertEqual(summary["row_count"], 0)
        self.assertIsNone(summary["agreement_rate"])

    def test_merge_requires_reviewer_b_status_column(self):
        pilot = pd.DataFrame([pilot_row("a", "ar", "high", "accepted")])
        with self.assertRaises(ValueError):
            merge_double_review(pilot, pd.DataFrame([{"original_case_key": "a"}]))


if __name__ == "__main__":
    unittest.main()
