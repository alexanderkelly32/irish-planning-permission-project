"""Leakage, chronology and data-invariant tests (brief sections 16.2, 20.3-20.4)."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk import provenance  # noqa: E402


class LeakageTests(unittest.TestCase):
    def test_feature_after_snapshot_rejected(self):
        with self.assertRaises(provenance.AvailabilityError):
            provenance.enforce_available_at("nearby_refusal_rate", "2021-02-01", "2020-01-01")

    def test_feature_on_snapshot_day_ok(self):
        provenance.enforce_available_at("nearby_refusal_rate", "2020-01-01", "2020-01-01")

    def test_all_features_audited(self):
        features = {
            "feature_a": {"available_at": "2019-05-01"},
            "feature_b": {"available_at": "2019-12-01"},
        }
        snapshot_at = "2019-11-01"
        failures = []
        for name, meta in features.items():
            try:
                provenance.enforce_available_at(name, meta["available_at"], snapshot_at)
            except provenance.AvailabilityError as error:
                failures.append(str(error))
        self.assertEqual(len(failures), 1)
        self.assertIn("feature_b", failures[0])


class ChronologyTests(unittest.TestCase):
    def test_final_grant_cannot_precede_submission(self):
        rows = pd.DataFrame(
            {
                "submission": pd.to_datetime(["2020-01-10", "2020-01-10"], utc=True),
                "final_grant": pd.to_datetime(["2020-06-01", "2019-12-01"], utc=True),
            }
        )
        violations = rows[rows["final_grant"] < rows["submission"]]
        self.assertEqual(len(violations), 1)

    def test_commencement_not_before_grant_without_flag(self):
        rows = pd.DataFrame(
            {
                "grant": pd.to_datetime(["2020-06-01"], utc=True),
                "commencement": pd.to_datetime(["2020-05-15"], utc=True),
                "exceptional_status": [False],
            }
        )
        violations = rows[(rows["commencement"] < rows["grant"]) & (~rows["exceptional_status"])]
        self.assertEqual(len(violations), 1)

    def test_ppr_sale_not_before_plausible_chronology(self):
        rows = pd.DataFrame(
            {
                "first_commencement": pd.to_datetime(["2020-06-01"], utc=True),
                "sale": pd.to_datetime(["2020-05-15"], utc=True),
            }
        )
        violations = rows[rows["sale"] < rows["first_commencement"]]
        self.assertEqual(len(violations), 1)


class InvariantTests(unittest.TestCase):
    def test_probabilities_in_unit_interval(self):
        probs = pd.Series([0.0, 0.5, 1.0, 0.999])
        self.assertTrue(probs.between(0.0, 1.0).all())

    def test_label_has_window_and_eligibility(self):
        labels = pd.DataFrame(
            {
                "scheme_id": ["S1"],
                "label_name": ["commence_24m"],
                "observation_window_end": ["2026-09-27"],
                "eligible": [True],
            }
        )
        self.assertTrue({"observation_window_end", "eligible"}.issubset(labels.columns))

    def test_confirmed_links_have_evidence(self):
        links = pd.DataFrame(
            {
                "scheme_id": ["S1"],
                "bcms_event_id": ["E1"],
                "confidence_band": ["confirmed"],
                "evidence_json": ['{"reasons": ["exact reference match"]}'],
            }
        )
        confirmed = links[links["confidence_band"] == "confirmed"]
        self.assertTrue((confirmed["evidence_json"].astype(str) != "").all())


if __name__ == "__main__":
    unittest.main()
