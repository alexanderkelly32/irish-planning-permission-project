import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.models import hazard  # noqa: E402
from devrisk.models.survival import kaplan_meier  # noqa: E402


class HazardTests(unittest.TestCase):
    def test_regime_exposure(self):
        import datetime as dt

        exposure = hazard.regime_exposure(dt.date(2021, 2, 1), dt.date(2021, 2, 28))
        self.assertEqual(exposure["broad_closure"], 1)
        self.assertEqual(exposure["phased_reopening"], 0)
        outside = hazard.regime_exposure(dt.date(2022, 1, 1), dt.date(2022, 1, 28))
        self.assertEqual(outside["broad_closure"], 0)

    def test_person_periods_expansion(self):
        durations = np.array([45.0, 75.0])
        events = np.array([1, 0])
        starts = np.array([pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")])
        features = pd.DataFrame({"x": [0.1, 0.2]})
        periods = hazard.build_person_periods(durations, events, start_dates=starts, features=features)
        self.assertEqual(periods.loc[periods["unit"] == 0, "y"].sum(), 1)
        self.assertEqual(periods.loc[periods["unit"] == 1, "y"].sum(), 0)
        self.assertIn("broad_closure", periods.columns)

    def test_concordance_perfect_and_inverse(self):
        times = np.array([10.0, 20.0, 30.0])
        events = np.array([1, 1, 1])
        perfect = hazard.concordance_index(times, events, np.array([3.0, 2.0, 1.0]))
        inverse = hazard.concordance_index(times, events, np.array([1.0, 2.0, 3.0]))
        self.assertAlmostEqual(perfect, 1.0)
        self.assertAlmostEqual(inverse, 0.0)

    def test_brier_ipcw_bounds(self):
        times = np.array([100.0, 400.0, 800.0, 1200.0])
        events = np.array([1, 0, 1, 1])
        surv = np.array([0.8, 0.5, 0.3, 0.1])
        score = hazard.brier_ipcw(times, events, surv, horizon=730.0)
        self.assertGreaterEqual(score, 0.0)

    def test_horizon_prediction_monotonic(self):
        features = pd.DataFrame({"x": [0.0, 1.0]})
        durations = np.array([100.0, 300.0, 500.0, 700.0, 900.0])
        events = np.ones(5)
        starts = np.array([pd.Timestamp("2020-01-01", tz="UTC")] * 5)
        base = pd.DataFrame({"x": [0.0, 0.5, 1.0, 1.5, 2.0]})
        periods = hazard.build_person_periods(durations, events, start_dates=starts, features=base)
        model = hazard.fit_hazard(periods, ["interval_index", "t_start", "broad_closure", "phased_reopening", "x"])
        probs = hazard.predict_horizon_probabilities(
            model, base.head(2), feature_columns=["interval_index", "t_start", "broad_closure", "phased_reopening", "x"],
            origins=starts[:2], horizons=(365, 730, 1096),
        )
        for row in probs:
            self.assertTrue(np.all(np.diff(row) >= -1e-9))


if __name__ == "__main__":
    unittest.main()
