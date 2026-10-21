import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.models import survival  # noqa: E402


class SurvivalBaselineTests(unittest.TestCase):
    def test_kaplan_meier_no_censoring(self):
        durations = np.array([10.0, 20.0, 30.0, 40.0])
        events = np.array([1, 1, 1, 1])
        table = survival.kaplan_meier(durations, events)
        self.assertEqual(len(table), 4)
        self.assertAlmostEqual(table["survival"].iloc[-1], 0.0)
        self.assertAlmostEqual(table["survival"].iloc[0], 0.75)

    def test_kaplan_meier_with_censoring(self):
        durations = np.array([5.0, 10.0, 15.0, 20.0])
        events = np.array([1, 0, 1, 1])
        table = survival.kaplan_meier(durations, events)
        self.assertAlmostEqual(table["survival"].iloc[0], 0.75)  # 1 event / 4 at risk
        self.assertAlmostEqual(table["survival"].iloc[2], 0.375)  # S = 0.75 * 1/2
        self.assertAlmostEqual(table["survival"].iloc[-1], 0.0)

    def test_horizon_probabilities(self):
        durations = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        events = np.ones(5)
        table = survival.kaplan_meier(durations, events)
        self.assertEqual(survival.km_probability_by(table, 50.0), 0.0)
        self.assertEqual(survival.km_probability_by(table, 600.0), 1.0)
        self.assertAlmostEqual(survival.km_probability_by(table, 250.0), 0.4)

    def test_empty_input(self):
        table = survival.kaplan_meier(np.array([]), np.array([]))
        self.assertTrue(table.empty)

    def test_negative_duration_raises(self):
        with self.assertRaises(ValueError):
            survival.kaplan_meier(np.array([-1.0]), np.array([1]))

    def test_median_survival_time(self):
        table = survival.kaplan_meier(np.array([10.0, 20.0, 30.0, 40.0]), np.ones(4))
        self.assertEqual(survival.median_survival_time(table), 20.0)

    def test_discrete_time_hazard_matrix(self):
        durations = np.array([45.0, 75.0])
        events = np.array([1, 0])
        person_periods = survival.discrete_time_hazard_matrix(durations, events, max_time=90.0, interval_days=30.0)
        self.assertTrue({"unit", "t_start", "t_end", "y"}.issubset(person_periods.columns))
        self.assertEqual(person_periods.loc[person_periods["unit"] == 0, "y"].sum(), 1)
        self.assertEqual(person_periods.loc[person_periods["unit"] == 1, "y"].sum(), 0)

    def test_discrete_time_hazard_fit_predict(self):
        rng = np.random.default_rng(3)
        n = 200
        feature = rng.uniform(0, 1, n)
        durations = 100 + 300 * (1 - feature) + rng.uniform(0, 50, n)
        durations = np.clip(durations, 10, 400)
        events = rng.uniform(0, 1, n) < 0.8
        person_periods = survival.discrete_time_hazard_matrix(durations, events, max_time=400.0, interval_days=30.0)
        person_periods["x"] = feature[person_periods["unit"]]
        model = survival.fit_discrete_time_hazard(person_periods, ["x"])
        probs_high = survival.predict_horizon_probabilities(model, {"x": 0.95}, [365], interval_days=30.0)
        probs_low = survival.predict_horizon_probabilities(model, {"x": 0.05}, [365], interval_days=30.0)
        self.assertGreater(probs_high[365], probs_low[365])
        for horizon, prob in probs_high.items():
            self.assertTrue(0.0 <= prob <= 1.0)


if __name__ == "__main__":
    unittest.main()
