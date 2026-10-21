import unittest

import numpy as np
import pandas as pd

from evaluate_linkage_ranking import (
    build_labelled_frame,
    evaluate_labelled_ranking,
    review_order_analysis,
)


def queue_row(original, revised, tier, status, score, distance=5.0, desc_sim=0.9, applicant=False, postcode=True, gap=200, units_delta=None, blocking="exact_address"):
    return {
        "original_case_key": original,
        "revised_case_key": revised,
        "planning_authority": "Example Council",
        "original_application_number": original,
        "revised_application_number": revised,
        "original_received_date": "2020-01-01",
        "revised_received_date": "2021-01-01",
        "gap_days": gap,
        "blocking_methods": blocking,
        "coordinate_distance_m": distance,
        "description_similarity": desc_sim,
        "applicant_match": applicant,
        "postcode_match": postcode,
        "original_units": 40,
        "revised_units": 38,
        "units_delta": units_delta,
        "linkage_score": score,
        "linkage_tier": tier,
        "manual_review_status": status,
        "manual_review_notes": "",
    }


class LinkageRankingEvaluationTests(unittest.TestCase):
    def build_queue(self):
        rows = []
        for index in range(30):
            rows.append(queue_row(f"h{index}a", f"h{index}b", "high", "accepted" if index < 21 else "rejected", 0.9 - index * 0.01))
        for index in range(30):
            rows.append(queue_row(f"m{index}a", f"m{index}b", "medium", "accepted" if index < 15 else "rejected", 0.6 - index * 0.01, distance=40.0))
        for index in range(30):
            rows.append(queue_row(f"l{index}a", f"l{index}b", "low", "accepted" if index < 5 else "rejected", 0.35 - index * 0.005, distance=400.0, blocking="spatial_50m", desc_sim=0.4))
        for index in range(10):
            rows.append(queue_row(f"p{index}a", f"p{index}b", "high", "pending", 0.8))
        return pd.DataFrame(rows)

    def test_builds_labelled_frame_with_features_and_excludes_pending(self):
        frame = build_labelled_frame(self.build_queue())

        self.assertEqual(len(frame), 90)
        self.assertTrue(set(frame["target"].unique()).issubset({0, 1}))
        self.assertEqual(int(frame["target"].sum()), 41)
        self.assertIn("has_units_delta", frame.columns)
        self.assertIn("tier_ordinal", frame.columns)
        self.assertEqual(frame.loc[0, "tier_ordinal"], 3)

    def test_evaluation_reports_folds_and_tier_metrics(self):
        frame = build_labelled_frame(self.build_queue())
        results = evaluate_labelled_ranking(frame, n_splits=3, seed=42)

        self.assertEqual(results["status"], "evaluated")
        self.assertEqual(results["labelled_row_count"], 90)
        self.assertEqual(len(results["fold_results"]), 3)
        fold = results["fold_results"][0]
        self.assertIn("roc_auc", fold)
        self.assertIn("precision", fold)
        self.assertIn("recall", fold)
        self.assertIn("high", fold["tier_metrics"])
        self.assertIn("medium", fold["tier_metrics"])
        self.assertIn("low", fold["tier_metrics"])
        self.assertGreater(fold["roc_auc"], 0.5)
        self.assertIn("roc_auc", results["fold_aggregates"])
        self.assertIsNotNone(results["fold_aggregates"]["roc_auc"]["mean"])
        self.assertIn("mean_precision", results["tier_aggregates"]["high"])

    def test_evaluation_degrades_to_insufficient_with_single_class(self):
        rows = [queue_row("a", "ar", "high", "accepted", 0.9) for _ in range(5)]
        results = evaluate_labelled_ranking(build_labelled_frame(pd.DataFrame(rows)))
        self.assertEqual(results["status"], "insufficient_labels")

    def test_review_order_finds_accepted_labels_early(self):
        queue = self.build_queue()
        analysis = review_order_analysis(queue)

        self.assertEqual(analysis["labelled_row_count"], 90)
        self.assertEqual(analysis["accepted_label_count"], 41)
        for key in ("accepted_labels_found_in_top_1pct", "accepted_labels_found_in_top_5pct", "accepted_labels_found_in_top_10pct"):
            self.assertGreaterEqual(analysis[key], 0.0)
        self.assertGreaterEqual(
            analysis["accepted_labels_found_in_top_20pct"],
            analysis["accepted_labels_found_in_top_10pct"],
        )
        self.assertEqual(analysis["by_tier"]["high"]["accepted_rows"], 21)

    def test_queue_missing_columns_raise(self):
        with self.assertRaises(ValueError):
            build_labelled_frame(pd.DataFrame([{"case_key": "x"}]))

    def test_review_order_median_rank_is_monotonic_with_construction(self):
        queue = self.build_queue()
        analysis = review_order_analysis(queue)
        positions = [np.median(np.arange(10)), np.median(np.arange(30) + 40), np.median(np.arange(30) + 70)]
        self.assertIsNotNone(analysis["rejected_labels_median_rank"])
        self.assertGreater(analysis["rejected_labels_median_rank"], analysis["by_tier"]["high"]["median_rank_in_queue"])


if __name__ == "__main__":
    unittest.main()
