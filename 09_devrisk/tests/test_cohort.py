import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk import cohort  # noqa: E402


def register_frame():
    return pd.DataFrame(
        {
            "PlanningAuthority": ["Meath County Council"] * 5 + ["Kildare County Council"] * 5,
            "ApplicationNumber": [f"AA{i}" for i in range(10)],
            "NumResidentialUnits": [12, 40, 120, 300, 24, 14, 60, 150, 320, 28],
            "Decision": ["GRANTED"] * 10,
            "GrantDate": pd.to_datetime(
                ["2019-06-01"] * 5 + ["2021-07-01"] * 5, utc=True
            ),
            "ReceivedDate": pd.to_datetime(["2018-01-01"] * 10, utc=True),
            "DevelopmentAddress": [f"Road {i}, Town" for i in range(10)],
            "SiteId": [f"S{i}" for i in range(10)],
            "ITMEasting": [701000.0 + i for i in range(10)],
            "ITMNorthing": [745000.0 + i for i in range(10)],
        }
    )


class CohortTests(unittest.TestCase):
    def test_candidate_pool_filters(self):
        pool = cohort.build_candidate_pool(register_frame(), grant_start="2016-01-01", grant_end="2022-12-31", censor_date="2026-09-27")
        self.assertEqual(len(pool), 10)
        self.assertTrue((pool["followup_months"] >= 36).all())

    def test_candidate_pool_rejects_under_10_units_and_refusals(self):
        frame = register_frame()
        frame.loc[0, "NumResidentialUnits"] = 5
        frame.loc[1, "Decision"] = "REFUSED"
        pool = cohort.build_candidate_pool(frame, grant_start="2016-01-01", grant_end="2022-12-31", censor_date="2026-09-27")
        self.assertEqual(len(pool), 8)

    def test_is_granted(self):
        self.assertTrue(cohort.is_granted("GRANTED"))
        self.assertTrue(cohort.is_granted("Grant permission"))
        self.assertTrue(cohort.is_granted("CONDITIONAL"))
        self.assertFalse(cohort.is_granted("REFUSED"))
        self.assertFalse(cohort.is_granted("grant permission refused"))

    def test_covid_exposure(self):
        exposure = cohort.covid_exposure(pd.Timestamp("2019-06-01", tz="UTC"))
        self.assertTrue(exposure["covid_materially_exposed"])
        self.assertGreater(exposure["covid_exposure_days"]["broad_closure"], 0)

    def test_annotate_pool_strata(self):
        annotated = cohort.annotate_pool(register_frame())
        self.assertEqual(set(annotated["size_band"]), {"10-29", "30-99", "100-249", "250+"})
        self.assertIn("covid_materially_exposed", annotated.columns)

    def test_stratify_pilot_size_and_bands(self):
        annotated = cohort.annotate_pool(register_frame())
        pilot = cohort.stratify_pilot(annotated, target=8, seed=7)
        self.assertEqual(len(pilot), 8)
        self.assertEqual(set(pilot["size_band"]), {"10-29", "30-99", "100-249", "250+"})
        self.assertTrue((pilot["pilot_rank"] >= 1).all())


if __name__ == "__main__":
    unittest.main()
