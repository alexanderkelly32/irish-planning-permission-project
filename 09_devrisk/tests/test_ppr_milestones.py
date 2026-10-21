import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.labels import ppr_milestones  # noqa: E402


class PprMilestoneTests(unittest.TestCase):
    def _transactions(self, n=20):
        return pd.DataFrame(
            {
                "sale_date": pd.date_range("2021-03-01", periods=n, freq="14D", tz="UTC"),
                "price": [300000 + i * 1000 for i in range(n)],
                "eligible": [True] * n,
            }
        )

    def test_build_to_rent_ineligible(self):
        result = ppr_milestones.build_sales_milestones("S1", self._transactions(), expected_sellable_units=20, tenure_or_exit_type="build_to_rent")
        self.assertFalse(result["eligible"])
        self.assertIn("build_to_rent", result["reason"])

    def test_milestones_reached(self):
        result = ppr_milestones.build_sales_milestones("S1", self._transactions(20), expected_sellable_units=20)
        self.assertTrue(result["eligible"])
        self.assertIsNotNone(result["milestones"]["first_sale_date"])
        self.assertIsNotNone(result["milestones"]["pct25_date"])
        self.assertIsNotNone(result["milestones"]["pct50_date"])
        self.assertIsNotNone(result["milestones"]["pct90_date"])

    def test_coverage_warning_when_undersold(self):
        result = ppr_milestones.build_sales_milestones("S1", self._transactions(5), expected_sellable_units=20)
        self.assertTrue(result["coverage_warning"])
        self.assertEqual(result["coverage_ratio"], 0.25)

    def test_no_denominator_ineligible(self):
        result = ppr_milestones.build_sales_milestones("S1", self._transactions(), expected_sellable_units=None)
        self.assertFalse(result["eligible"])

    def test_ineligible_transactions_excluded(self):
        transactions = self._transactions(10)
        transactions.loc[0, "eligible"] = False
        result = ppr_milestones.build_sales_milestones("S1", transactions, expected_sellable_units=10)
        self.assertEqual(result["linked_transactions"], 9)


if __name__ == "__main__":
    unittest.main()
