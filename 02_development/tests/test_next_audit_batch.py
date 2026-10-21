import unittest

import pandas as pd

from build_next_linkage_audit_batch import build_audit_batch


def sample_row(tier, index):
    return {
        "original_case_key": f"{tier}_{index}_a",
        "revised_case_key": f"{tier}_{index}_b",
        "linkage_tier": tier,
        "manual_review_status": "pending",
        "linkage_score": 0.9 - index * 0.001,
        "original_source_url": "https://example.test/o",
        "revised_source_url": "https://example.test/r",
    }


class NextAuditBatchTests(unittest.TestCase):
    def build_sample(self):
        rows = [sample_row("high", i) for i in range(80)]
        rows += [sample_row("medium", i) for i in range(80)]
        rows += [sample_row("low", i) for i in range(80)]
        return pd.DataFrame(rows)

    def test_batch_is_deterministic_and_per_tier(self):
        sample = self.build_sample()
        first = build_audit_batch(sample, per_tier=40)
        second = build_audit_batch(sample, per_tier=40)

        self.assertEqual(first["original_case_key"].tolist(), second["original_case_key"].tolist())
        self.assertEqual(first["linkage_tier"].value_counts().to_dict(), {"high": 40, "medium": 40, "low": 40})

    def test_batch_blanks_review_columns(self):
        batch = build_audit_batch(self.build_sample(), per_tier=10)
        for column in ("manual_review_status", "manual_review_notes", "reviewer", "reviewed_at"):
            self.assertTrue(batch[column].isna().all() or (batch[column] == "").all())

    def test_batch_excludes_resolved_rows_and_respects_tier_selection(self):
        sample = self.build_sample()
        sample.loc[0, "manual_review_status"] = "accepted"
        batch = build_audit_batch(sample, per_tier=10, tiers=("high", "medium"))
        self.assertNotIn("low", set(batch["linkage_tier"]))
        self.assertNotIn("high_0_a", batch["original_case_key"].tolist())

    def test_batch_includes_low_tier_by_default(self):
        batch = build_audit_batch(self.build_sample(), per_tier=5)
        self.assertEqual(batch["linkage_tier"].value_counts().to_dict(), {"high": 5, "medium": 5, "low": 5})

    def test_missing_columns_raise(self):
        with self.assertRaises(ValueError):
            build_audit_batch(pd.DataFrame([{"case_key": "x"}]))


if __name__ == "__main__":
    unittest.main()
