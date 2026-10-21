import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.reporting import refusal_reason_engine, timing_engine  # noqa: E402


class TimingEngineTests(unittest.TestCase):
    def test_score_timing_quantiles_ordered(self):
        artifact = timing_engine.load_artifact()
        register = timing_engine._register_durations()
        result = timing_engine.score_timing(
            authority="Meath County Council",
            units=40,
            description="construction of 40 no. houses with a new access road",
            received_date=pd.Timestamp("2025-03-01", tz="UTC"),
            register=register,
            artifact=artifact,
        )
        self.assertLessEqual(result["P20_days"], result["P50_days"])
        self.assertLessEqual(result["P50_days"], result["P80_days"])
        self.assertIn("183", result["horizon_probabilities"])
        for prob in result["horizon_probabilities"].values():
            self.assertTrue(0.0 <= prob <= 1.0)

    def test_explain_timing_returns_drivers(self):
        artifact = timing_engine.load_artifact()
        drivers = timing_engine.explain_timing(
            authority="Meath County Council",
            units=40,
            description="construction of 40 no. houses with a new access road",
            received_date=pd.Timestamp("2025-03-01", tz="UTC"),
            artifact=artifact,
        )
        self.assertTrue(drivers)
        self.assertTrue(all(0.0 <= d["importance"] <= 1.0 for d in drivers))
        self.assertEqual(drivers[0]["feature"], "auth_prior_180d_median_duration")

    def test_congestion_time_safety(self):
        register = pd.DataFrame({
            "PlanningAuthority": ["Meath County Council"] * 3,
            "received_date_dt": pd.to_datetime(["2025-01-01", "2025-03-01", "2025-04-01"], utc=True),
            "duration_days": [100.0, 200.0, 300.0],
        })
        features = timing_engine._congestion_features(register, "Meath County Council", pd.Timestamp("2025-05-01", tz="UTC"))
        self.assertEqual(features["auth_prior_90d_count"], 2)  # Mar + Apr, excludes Jan
        self.assertEqual(features["auth_prior_180d_median_duration"], 200.0)  # median(100, 200, 300)


class RefusalReasonEngineTests(unittest.TestCase):
    def test_family_priors(self):
        priors = refusal_reason_engine.family_priors()
        self.assertGreater(priors["n_refused"], 1000)
        self.assertGreater(priors["tag_coverage"], 0.5)
        self.assertIn("design_visual_impact", priors["frequencies"])
        self.assertTrue(all(0.0 <= f <= 1.0 for f in priors["frequencies"].values()))

    def test_transfer_themes(self):
        transfer = refusal_reason_engine.transfer_themes(
            description="construction of 24 houses with access road and wastewater treatment",
            authority="Meath County Council",
            units=24,
        )
        self.assertIn("matched_n", transfer)
        self.assertIn("transfer_accuracy_note", transfer)

    def test_payload(self):
        payload = refusal_reason_engine.refusal_reason_payload(
            description="construction of 24 houses with access road",
            authority="Meath County Council",
            units=24,
        )
        self.assertIn("family_priors", payload)
        self.assertIn("scheme_transfer", payload)


if __name__ == "__main__":
    unittest.main()
