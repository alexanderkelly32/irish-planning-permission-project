import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.labels import activation  # noqa: E402


def schemes_frame():
    return pd.DataFrame(
        {
            "scheme_id": ["S1", "S2", "S3", "S4"],
            "final_grant_date": ["2019-06-14", "2025-01-15", "2019-06-14", None],
            "expected_units": [24, 12, 60, 10],
        }
    )


class ActivationLabelTests(unittest.TestCase):
    def test_event_observed_within_horizons(self):
        events = pd.DataFrame(
            {
                "scheme_id": ["S1"],
                "commencement_date_dt": [pd.Timestamp("2019-12-01", tz="UTC")],
                "corroboration_tier": ["B"],
                "competing_event": [None],
            }
        )
        labels = activation.build_activation_labels(schemes_frame(), events, censor_date="2026-09-27")
        row = labels[labels["scheme_id"] == "S1"].iloc[0]
        self.assertEqual(row["event_observed"], 1)
        self.assertFalse(row["censored"])
        self.assertEqual(row["commence_12m"], 1)
        self.assertEqual(row["commence_24m"], 1)
        self.assertEqual(row["corroboration_tier"], "B")
        self.assertAlmostEqual(row["duration_days"], 170, delta=1)

    def test_right_censoring_recent_grant(self):
        labels = activation.build_activation_labels(schemes_frame(), pd.DataFrame(), censor_date="2026-09-27")
        recent = labels[labels["scheme_id"] == "S2"].iloc[0]
        self.assertTrue(recent["censored"])
        self.assertEqual(recent["censor_reason"], "right_censored_no_event_by_censor_date")
        self.assertEqual(recent["event_observed"], 0)
        self.assertTrue(pd.isna(recent["commence_36m"]))  # 2025 grant never labelled "did not commence in 36m"
        self.assertFalse(pd.isna(recent["commence_12m"]))  # 12m window matured -> 0

    def test_mature_no_event_is_observed_zero(self):
        labels = activation.build_activation_labels(schemes_frame(), pd.DataFrame(), censor_date="2026-09-27")
        mature = labels[labels["scheme_id"] == "S3"].iloc[0]
        self.assertTrue(mature["censored"])
        self.assertEqual(mature["event_observed"], 0)
        self.assertEqual(mature["commence_36m"], 0)

    def test_missing_grant_not_eligible(self):
        labels = activation.build_activation_labels(schemes_frame(), pd.DataFrame(), censor_date="2026-09-27")
        row = labels[labels["scheme_id"] == "S4"].iloc[0]
        self.assertFalse(row["eligible"])
        self.assertEqual(row["censor_reason"], "missing_final_grant_date")

    def test_competing_event_reported(self):
        events = pd.DataFrame(
            {
                "scheme_id": ["S1"],
                "commencement_date_dt": [pd.Timestamp("2019-12-01", tz="UTC")],
                "corroboration_tier": ["A"],
                "competing_event": ["replacement_permission"],
            }
        )
        labels = activation.build_activation_labels(schemes_frame(), events, censor_date="2026-09-27")
        row = labels[labels["scheme_id"] == "S1"].iloc[0]
        self.assertEqual(row["competing_event"], "replacement_permission")

    def test_links_filter_unconfirmed(self):
        events = pd.DataFrame(
            {
                "scheme_id": ["S1"],
                "bcms_event_id": ["EVT1"],
                "commencement_date_dt": [pd.Timestamp("2019-12-01", tz="UTC")],
                "corroboration_tier": ["A"],
                "competing_event": [None],
            }
        )
        links = pd.DataFrame(
            {
                "scheme_id": ["S1"],
                "bcms_event_id": ["EVT1"],
                "confidence_band": ["ambiguous"],
            }
        )
        labels = activation.build_activation_labels(schemes_frame(), events, censor_date="2026-09-27", links=links)
        row = labels[labels["scheme_id"] == "S1"].iloc[0]
        self.assertEqual(row["event_observed"], 0)


if __name__ == "__main__":
    unittest.main()
