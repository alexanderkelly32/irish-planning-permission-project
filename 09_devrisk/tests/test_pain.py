import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.labels import pain  # noqa: E402


def register_frame():
    return pd.DataFrame(
        {
            "case_key": ["S1", "S2", "S3", "S4"],
            "PlanningAuthority": ["Meath County Council"] * 4,
            "ApplicationNumber": ["AA1", "AA2", "AA3", "AA4"],
            "ReceivedDate": ["2019-01-10", "2019-01-10", "2019-01-10", "2019-01-10"],
            "DecisionDate": ["2019-06-10", "2019-06-10", "2021-03-10", "2019-06-10"],
            "GrantDate": ["2019-06-14", "2019-06-14", "2021-03-14", "2019-06-14"],
            "FIRequestDate": [None, "2019-02-01", None, None],
            "FIRecDate": [None, None, None, None],
            "AppealSubmittedDate": [None, None, None, "2019-08-01"],
            "AppealRefNumber": [None, None, None, "ABP-123"],
            "ITMEasting": [701000.0] * 4,
            "ITMNorthing": [745000.0] * 4,
        }
    )


def bcms_frame():
    return pd.DataFrame(
        {
            "bcms_event_id": ["E1", "E2", "E3", "E4"],
            "commencement_date_dt": pd.to_datetime(
                ["2020-06-01", "2019-08-01", "2023-06-01", "2019-12-01"], utc=True
            ),
            "completion_certificate_date_dt": pd.to_datetime(
                [None, "2021-08-01", None, "2022-01-01"], utc=True
            ),
        }
    )


def links_frame():
    return pd.DataFrame(
        {
            "scheme_id": ["S1", "S2", "S3", "S4"],
            "bcms_event_id": ["E1", "E2", "E3", "E4"],
            "confidence_band": ["confirmed", "confirmed", "ambiguous", "confirmed"],
        }
    )


class PainLabelTests(unittest.TestCase):
    def test_components_from_structured_data(self):
        labels = pain.build_components(register_frame(), bcms_frame(), links_frame(), censor_date="2026-09-27")
        s1 = labels[labels["scheme_id"] == "S1"].iloc[0]
        self.assertFalse(s1["fi_requested"])
        self.assertFalse(s1["appeal_submitted"])
        self.assertEqual(s1["planning_duration_days"], 151)
        self.assertAlmostEqual(s1["activation_days"], 352, delta=1)

    def test_fi_and_slow_planning(self):
        labels = pain.build_components(register_frame(), bcms_frame(), links_frame(), censor_date="2026-09-27")
        s2 = labels[labels["scheme_id"] == "S2"].iloc[0]
        self.assertTrue(s2["fi_requested"])
        s3 = labels[labels["scheme_id"] == "S3"].iloc[0]
        self.assertTrue(s3["slow_planning_12m"])
        self.assertTrue(s3["slow_planning_24m"])

    def test_appeal_is_high(self):
        labels = pain.build_components(register_frame(), bcms_frame(), links_frame(), censor_date="2026-09-27")
        s4 = labels[labels["scheme_id"] == "S4"].iloc[0]
        self.assertTrue(s4["appeal_submitted"])
        self.assertEqual(s4["level"], "high")
        self.assertEqual(s4["pain_high_binary"], 1)

    def test_ambiguous_link_does_not_create_activation(self):
        labels = pain.build_components(register_frame(), bcms_frame(), links_frame(), censor_date="2026-09-27")
        s3 = labels[labels["scheme_id"] == "S3"].iloc[0]
        self.assertFalse(s3["activation_linked"])

    def test_level_assign_priority(self):
        self.assertEqual(pain.assign_level({"appeal_submitted": True, "fi_requested": True}), "high")
        self.assertEqual(pain.assign_level({"fi_requested": True}), "moderate")
        self.assertEqual(
            pain.assign_level({"appeal_submitted": False, "slow_planning_24m": False,
                               "slow_activation_24m": False, "slow_completion_36m": False,
                               "fi_requested": False, "slow_planning_12m": False,
                               "no_completion_matured": False}),
            "low",
        )

    def test_prevalence_summary(self):
        labels = pain.build_components(register_frame(), bcms_frame(), links_frame(), censor_date="2026-09-27")
        summary = pain.component_prevalence(labels)
        self.assertEqual(summary["rows"], 4)
        self.assertIn("pain_high_prevalence", summary)


if __name__ == "__main__":
    unittest.main()
