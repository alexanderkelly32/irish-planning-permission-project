"""Frozen-model adapter tests: non-invasive integration only.

The frozen artifact itself is never modified; these tests verify the wrapper
reads the manifest and builds submission-time proposals correctly, and (if the
artifact is present) that scoring still runs through the public interface.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk import settings  # noqa: E402
from devrisk.models import planning_adapter  # noqa: E402


class PlanningAdapterTests(unittest.TestCase):
    def test_frozen_manifest_reads(self):
        self.assertTrue(settings.FROZEN_MANIFEST_JSON.exists())
        version = planning_adapter.frozen_model_version()
        self.assertEqual(version, "national_residential_v4_full")

    def test_proposal_from_application_submission_time_only(self):
        proposal = planning_adapter.proposal_from_application(
            authority="Meath County Council",
            description="construction of 20 houses",
            units=20,
            site_area_sqm=8000,
            floor_area_sqm=4000,
            itm_easting=701000,
            itm_northing=745000,
            submission_year=2021,
        )
        self.assertEqual(proposal["authority"], "Meath County Council")
        self.assertEqual(proposal["units"], 20)
        self.assertEqual(proposal["submission_year"], 2021)
        self.assertNotIn("decision", proposal)

    def test_score_planning_returns_versioned_result(self):
        if not settings.FROZEN_MODEL_JOBLIB.exists():
            self.skipTest("frozen artifact absent")
        score = planning_adapter.score_planning(
            {
                "authority": "Dun Laoghaire Rathdown County Council",
                "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
                "units": 12,
                "site_area_sqm": 4000,
                "floor_area_sqm": 2400,
                "itm_easting": 722000,
                "itm_northing": 726500,
                "submission_year": 2026,
            }
        )
        self.assertEqual(score["model_version"], "national_residential_v4_full")
        self.assertTrue(0.0 <= score["refusal_probability"] <= 1.0)
        self.assertIn("risk_band", score)


if __name__ == "__main__":
    unittest.main()
