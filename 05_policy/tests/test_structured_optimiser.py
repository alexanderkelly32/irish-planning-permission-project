import unittest

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from structured_optimiser import (
    apply_calibration,
    bootstrap_ci,
    build_cohort,
    calibrate_with_cv,
    evaluate_probas,
    make_logistic,
    resolve_outcome,
    sensitivity_sweep,
    split_temporal,
)


class StructuredOptimiserTests(unittest.TestCase):
    def build_source(self):
        rows = []
        for index in range(120):
            year = 2023 if index < 90 else 2025
            rows.append({
                "case_key": f"k{index}",
                "PlanningAuthority": "Dublin City Council" if index % 2 == 0 else "Meath County Council",
                "Decision": "REFUSED" if index % 6 == 0 else "CONDITIONAL",
                "ReceivedDate": f"{year}-01-15",
                "units_total_best": 20 + index,
                "llm_max_storeys": 2 + index % 5,
                "max_storeys_best": 2 + index % 5,
                "NumResidentialUnits": 20 + index,
                "AreaofSite": 0.5 + index * 0.01,
                "FloorArea": 2000 + index * 40,
                "parking_spaces_best": 10 + index,
                "open_space_sqm_best": 100 + index,
            })
        return pd.DataFrame(rows)

    def test_resolve_outcome(self):
        self.assertEqual(resolve_outcome("Conditional Permission"), "GRANTED")
        self.assertEqual(resolve_outcome("REFUSE PERMISSION"), "REFUSED")
        self.assertEqual(resolve_outcome(""), "UNKNOWN")

    def test_cohort_derives_features_and_targets(self):
        cohort = build_cohort(self.build_source())
        self.assertIn("storeys", cohort.columns)
        self.assertIn("density_units_per_ha", cohort.columns)
        self.assertIn("units_missing", cohort.columns)
        self.assertTrue(set(cohort["target_refused"]).issubset({0, 1}))
        self.assertEqual(len(cohort), 120)

    def test_temporal_split_keeps_holdout_untouched(self):
        cohort = build_cohort(self.build_source())
        train, test = split_temporal(cohort, cutoff_year=2025)
        self.assertTrue((train["received_year"] < 2025).all())
        self.assertTrue((test["received_year"] >= 2025).all())
        self.assertEqual(len(train), 90)
        self.assertEqual(len(test), 30)

    def test_evaluation_metrics(self):
        metrics = evaluate_probas(pd.Series([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]))
        self.assertEqual(metrics["roc_auc"], 1.0)
        self.assertGreater(metrics["log_loss"], 0)

    def test_sensitivity_sweep_holds_other_inputs_constant(self):
        model: Pipeline = make_logistic(["a", "b"])
        frame = pd.DataFrame({"a": [1, 1, 2, 2, 0, 0], "b": [0, 0, 1, 1, 2, 2]})
        model.fit(frame, pd.Series([0, 0, 0, 1, 1, 1]))
        sweep = sensitivity_sweep(model, {"a": 1.0, "b": 1.0}, ["a", "b"], "a", [0.0, 1.0, 2.0])
        self.assertEqual(len(sweep), 3)
        self.assertAlmostEqual(
            sweep[1]["refusal_probability"],
            round(model.predict_proba([[1.0, 1.0]])[:, 1][0], 4),
            places=4,
        )
        self.assertTrue(all(np.isfinite(row["refusal_probability"]) for row in sweep))

    def test_calibration_with_cv_improves_brier_on_synthetic_data(self):
        rng = np.random.default_rng(3)
        frame = pd.DataFrame({
            "a": rng.normal(0, 1, 400),
            "b": rng.normal(0, 1, 400),
        })
        logit = frame["a"] * 2 + frame["b"] * 1.5
        y = pd.Series((rng.random(400) < 1 / (1 + np.exp(-logit))).astype(int))
        model = make_logistic(["a", "b"])
        model.fit(frame, y)
        raw = model.predict_proba(frame)[:, 1]
        calibrator = calibrate_with_cv(model, frame, y, n_splits=3, seed=1)
        calibrated = apply_calibration(calibrator, raw)
        raw_brier = evaluate_probas(y, raw)["brier"]
        calibrated_brier = evaluate_probas(y, calibrated)["brier"]
        self.assertLessEqual(calibrated_brier, raw_brier + 0.02)

    def test_bootstrap_ci_reports_intervals(self):
        rng = np.random.default_rng(1)
        y = pd.Series((rng.random(200) < 0.2).astype(int))
        p = y * 0.6 + (1 - y) * 0.3 + rng.normal(0, 0.05, 200)
        ci = bootstrap_ci(y, p, n_boot=100, seed=5)
        self.assertEqual(ci["bootstrap_samples"], 100)
        self.assertGreater(ci["roc_auc"]["median"], 0.5)
        self.assertLessEqual(ci["roc_auc"]["p05"], ci["roc_auc"]["p95"])


if __name__ == "__main__":
    unittest.main()
