import unittest

import numpy as np
import pandas as pd

from council_calibration import (
    evaluate_council_calibration,
    fit_council_calibrators,
)


def frame_with(rows):
    return pd.DataFrame(rows)


class CouncilCalibrationTests(unittest.TestCase):
    def build_fit_frame(self):
        rows = []
        for council, base_risk in [("Big Council", 0.2), ("Big Council", 0.2), ("Small Council", 0.3)]:
            pass
        rows = []
        for index in range(120):
            risk = 0.2 if index % 2 else 0.4
            rows.append({
                "PlanningAuthority": "Big Council", "v3_ranking_score": risk,
                "target_refused": 1 if risk > 0.3 else 0, "v3_platt_risk": risk * 0.5,
            })
        for index in range(30):
            rows.append({
                "PlanningAuthority": "Small Council", "v3_ranking_score": 0.35,
                "target_refused": 0, "v3_platt_risk": 0.2,
            })
        return pd.DataFrame(rows)

    def test_fit_applies_minimum_sample_fallback(self):
        council_calibrators, national, diagnostics = fit_council_calibrators(
            self.build_fit_frame(), minimum_samples=50
        )
        self.assertIn("Big Council", council_calibrators)
        self.assertNotIn("Small Council", council_calibrators)
        self.assertIn("Small Council", diagnostics["councils_fallback"])
        self.assertIsNotNone(national)

    def test_single_class_council_fits_none_and_skips(self):
        frame = pd.DataFrame([
            {"PlanningAuthority": "OneClass", "v3_ranking_score": 0.2, "target_refused": 0},
            {"PlanningAuthority": "OneClass", "v3_ranking_score": 0.25, "target_refused": 0},
            {"PlanningAuthority": "TwoClass", "v3_ranking_score": 0.2, "target_refused": 0},
            {"PlanningAuthority": "TwoClass", "v3_ranking_score": 0.8, "target_refused": 1},
        ])
        calibrators, _, diagnostics = fit_council_calibrators(frame, minimum_samples=1)
        self.assertTrue(diagnostics["councils_fitted"]["OneClass"]["single_class_skipped"])
        self.assertIsNotNone(calibrators["TwoClass"])

    def test_evaluation_reports_all_three_tracks(self):
        calibrators, national, _ = fit_council_calibrators(self.build_fit_frame(), minimum_samples=50)
        eval_frame = self.build_fit_frame()
        evaluation = evaluate_council_calibration(eval_frame, calibrators, national)
        self.assertIn("council_aware_brier", evaluation["summary"])
        self.assertIn("national_fit_brier", evaluation["summary"])
        self.assertIn("frozen_national_brier", evaluation["summary"])
        self.assertIn("Big Council", evaluation["by_council"])
        self.assertFalse(evaluation["by_council"]["Small Council"]["used_council_calibrator"])

    def test_evaluation_handles_empty_frame(self):
        evaluation = evaluate_council_calibration(pd.DataFrame(), {}, None)
        self.assertEqual(evaluation["summary"]["eval_rows"], 0)

    def test_calibration_is_finite_and_within_unit_interval(self):
        calibrators, national, _ = fit_council_calibrators(self.build_fit_frame(), minimum_samples=50)
        evaluation = evaluate_council_calibration(self.build_fit_frame(), calibrators, national)
        for value in evaluation["by_council"].values():
            for key in ("council_brier", "national_brier", "frozen_brier"):
                if value[key] is not None:
                    self.assertTrue(np.isfinite(value[key]))


if __name__ == "__main__":
    unittest.main()
