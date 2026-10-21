"""Quarantine invariants: the clean view must never contain blocked rows,
every blocking rule must fire, and pending rows must not leak downstream."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

DQ = settings.SILVER_DIR / "dq"


class TestQuarantine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.quar = pd.read_csv(DQ / "quarantine.csv", dtype=str)
        cls.labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv")
        cls.clean = pd.read_csv(DQ / "labels_clean.csv")

    def test_quarantine_files_exist(self):
        self.assertTrue((DQ / "quarantine.csv").exists())
        self.assertTrue((DQ / "data_quality_report.json").exists())
        self.assertTrue((DQ / "labels_clean.csv").exists())

    def test_every_blocking_rule_fired(self):
        fired = set(self.quar[self.quar["severity"] == "block"]["rule"])
        self.assertTrue({"R1", "R2", "R3", "R8", "R10"} <= fired,
                        f"blocking rules missing: {fired}")

    def test_clean_view_excludes_blocked(self):
        blocked = set(self.quar[self.quar["severity"] == "block"]["case_key"])
        leak = set(self.clean["case_key"]) & blocked
        self.assertEqual(len(leak), 0, f"blocked keys leaked into clean view: {list(leak)[:5]}")

    def test_clean_view_excludes_pending(self):
        pending = set(self.labels[self.labels["activation_linked"].astype(str).str.lower() != "true"]["scheme_id"])
        leak = set(self.clean["case_key"]) & pending
        self.assertEqual(len(leak), 0, f"pending keys leaked: {list(leak)[:5]}")

    def test_no_negative_durations_in_clean(self):
        a = pd.to_numeric(self.clean["activation_days"], errors="coerce")
        c = pd.to_numeric(self.clean["completion_days"], errors="coerce")
        bad = ((a < 0) | ((c - a) < 0)).sum()
        self.assertEqual(bad, 0)

    def test_quarantine_rows_have_evidence(self):
        missing = self.quar[self.quar["evidence"].isna() | (self.quar["evidence"] == "nan")]
        self.assertEqual(len(missing), 0)


if __name__ == "__main__":
    unittest.main()
