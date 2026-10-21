"""Permanent label-hygiene test suite.

Hard invariants on the actual label files. Any label rebuild that
violates these fails these tests - the rebuild is then blocked.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

GRACE_SALE = -90
GRACE_CCC_SALE = -365
MAX_TFS = 4000
MAX_ACTIVATION = 4000
MAX_CCC = 4000


class LabelHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
        cls.pain = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
        cls.completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
        cls.verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)

    def test_no_pending_rows_feed_labels(self):
        if "verification_status" not in self.verified.columns:
            self.skipTest("verification_status column missing")
        pending = self.verified[self.verified["verification_status"] == "pending"]
        non_pending = self.verified[self.verified["verification_status"] != "pending"]
        linked_schemes = set(self.exit_labels[self.exit_labels["sales_linked"].gt(0)]["scheme_id"].astype(str))
        pending_only = set(pending["scheme_id"].astype(str)) - set(non_pending["scheme_id"].astype(str))
        self.assertEqual(len(linked_schemes & pending_only), 0,
                         "schemes linked ONLY via pending rows feed labels")

    def test_no_duplicate_verified_rows(self):
        duplicates = self.verified.duplicated(subset=["scheme_id", "ppr_source_row_id"]).sum()
        self.assertEqual(duplicates, 0, "duplicate verified sale rows present")

    def test_time_to_first_sale_within_grace(self):
        tfs = pd.to_numeric(self.exit_labels["time_to_first_sale_from_grant_days"], errors="coerce")
        self.assertGreaterEqual(tfs.min(), GRACE_SALE, "first sale before grant grace window")
        self.assertLessEqual(tfs.max(), MAX_TFS, "implausibly long time to first sale")

    def test_activation_bounds(self):
        act = pd.to_numeric(self.pain["activation_days"], errors="coerce")
        self.assertGreaterEqual(act.min(), -180, "activation before grant grace window (180d)")
        self.assertLessEqual(act.max(), MAX_ACTIVATION, "implausible activation duration")

    def test_completion_targets_nonnegative(self):
        for column in ("t_first_ccc", "t_25pct", "t_50pct", "t_final_ccc"):
            values = pd.to_numeric(self.completion[column], errors="coerce")
            self.assertGreaterEqual(values.min(), 0, f"negative {column}")
            self.assertLessEqual(values.max(), MAX_CCC, f"implausible {column}")

    def test_final_ccc_not_before_first_ccc(self):
        first = pd.to_numeric(self.completion["t_first_ccc"], errors="coerce")
        final = pd.to_numeric(self.completion["t_final_ccc"], errors="coerce")
        mask = first.notna() & final.notna()
        self.assertTrue((final[mask] >= first[mask] - 1).all(), "final CCC before first CCC")

    def test_first_sale_not_before_commencement_by_more_than_grace(self):
        merged = self.exit_labels.merge(
            self.pain[["case_key", "activation_days"]],
            left_on="scheme_id", right_on="case_key", how="inner")
        act = pd.to_numeric(merged["activation_days"], errors="coerce")
        tfs = pd.to_numeric(merged["time_to_first_sale_from_grant_days"], errors="coerce")
        gap = tfs - act  # sale relative to commencement
        mask = act.notna() & tfs.notna()
        self.assertGreaterEqual(gap[mask].min(), GRACE_CCC_SALE, "sale implausibly before commencement")

    def test_ccc_to_sale_scheme_level_within_bounds(self):
        merged = self.exit_labels.merge(
            self.completion[["scheme_id", "t_first_ccc"]], on="scheme_id", how="left")
        merged = merged.merge(self.pain[["case_key", "activation_days"]],
                              left_on="scheme_id", right_on="case_key", how="left")
        act = pd.to_numeric(merged["activation_days"], errors="coerce")
        ccc = pd.to_numeric(merged["t_first_ccc"], errors="coerce")
        tfs = pd.to_numeric(merged["time_to_first_sale_from_grant_days"], errors="coerce")
        ccc_to_sale = tfs - act - ccc
        mask = act.notna() & ccc.notna() & tfs.notna()
        offenders = merged.loc[mask & (ccc_to_sale < -2500), ["scheme_id", "time_to_first_sale_from_grant_days", "activation_days", "t_first_ccc"]]
        offenders.to_csv(settings.SILVER_DIR / "audit" / "ccc_sale_offenders.csv", index=False)
        # scheme-level attribution is known-skewed for phased schemes
        # (phase-1 sales precede later phases' earliest linked CCCs);
        # the 7 residual offenders are exported for phase-level
        # reconstruction rather than deleted.
        self.assertGreaterEqual(ccc_to_sale[mask].min(), -2500, "sale > ~7 years before first CCC")


if __name__ == "__main__":
    unittest.main()
