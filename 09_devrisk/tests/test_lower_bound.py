import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np
import pandas as pd

from run_lower_bound_benchmark import strata_quantiles  # noqa: E402


class StrataQuantileTests(unittest.TestCase):
    def _frames(self):
        rng = np.random.default_rng(0)
        authorities = ["Meath County Council", "Cork County Council"]
        rows = []
        for authority in authorities:
            for year in (2018, 2019, 2020):
                for _ in range(20):
                    rows.append({
                        "PlanningAuthority": authority,
                        "anchor_year": year,
                        "size_band": "10-29",
                        "duration": float(rng.integers(50, 400)),
                    })
        frame = pd.DataFrame(rows)
        train = frame[frame["anchor_year"] < 2020].copy()
        test = frame[frame["anchor_year"] >= 2020].copy()
        return train, test

    def test_fallback_fills_unseen_years_positionally(self):
        train, test = self._frames()
        result = strata_quantiles(train, test, ["PlanningAuthority", "anchor_year", "size_band"], "duration")
        self.assertEqual(len(result), len(test))
        self.assertTrue(result["pred_q50"].notna().all())
        # 2020 years are unseen in train: authority-level values apply, so the
        # two authorities must produce different predictions.
        meath = result[result["PlanningAuthority"] == "Meath County Council"]["pred_q50"]
        cork = result[result["PlanningAuthority"] == "Cork County Council"]["pred_q50"]
        self.assertFalse(np.allclose(meath.to_numpy(), cork.to_numpy()))

    def test_overall_fallback_when_authority_unseen(self):
        train, test = self._frames()
        extra = pd.DataFrame([{"PlanningAuthority": "Kerry County Council", "anchor_year": 2020, "size_band": "10-29", "duration": 100.0}])
        result = strata_quantiles(train, pd.concat([test, extra], ignore_index=True), ["PlanningAuthority", "anchor_year", "size_band"], "duration")
        kerry = result[result["PlanningAuthority"] == "Kerry County Council"]["pred_q50"]
        self.assertTrue(kerry.notna().all())
        self.assertEqual(kerry.iloc[0], float(train["duration"].quantile(0.5)))

    def test_quantiles_monotonic(self):
        train, test = self._frames()
        result = strata_quantiles(train, test, ["PlanningAuthority", "anchor_year", "size_band"], "duration")
        self.assertTrue((result["pred_q20"] <= result["pred_q50"]).all())
        self.assertTrue((result["pred_q50"] <= result["pred_q80"]).all())


if __name__ == "__main__":
    unittest.main()
