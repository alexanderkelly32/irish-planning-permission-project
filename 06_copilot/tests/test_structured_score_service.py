import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from structured_score_service import build_structured_features, score_structured, sensitivity_sweeps


class FakePipeline:
    def __init__(self):
        self.columns = None

    def predict_proba(self, frame):
        storeys = frame["storeys"].to_numpy()
        refusal = 1.0 / (1.0 + np.exp(-(storeys - 5.0) / 2.0))
        return np.column_stack([1.0 - refusal, refusal])


class StructuredScoreServiceTests(unittest.TestCase):
    def build_bundle(self):
        return {
            "model_version": "structured_optimiser_candidate_2026-09-08",
            "pipeline": FakePipeline(),
            "feature_columns": ["log_units", "storeys", "log_site_area_sqm", "log_floor_area_sqm",
                                "density_units_per_ha", "plot_ratio_proxy", "log_parking_spaces",
                                "log_open_space_sqm", "units_missing", "site_area_missing",
                                "floor_area_missing", "parking_missing", "open_space_missing",
                                "received_year", "authority_ordinal"],
            "authority_map": {0: "Meath County Council"},
            "feature_medians": {"log_units": 3.0, "storeys": 2.0, "log_site_area_sqm": 8.0,
                                "log_floor_area_sqm": 8.0, "density_units_per_ha": 10.0,
                                "plot_ratio_proxy": 0.3, "log_parking_spaces": 3.0,
                                "log_open_space_sqm": 5.0, "authority_ordinal": 0.0},
        }

    def build_site_scheme(self):
        site = {"planning_authority": "Meath County Council"}
        scheme = {"units": 40, "max_storeys": 5, "site_area_sqm": 5000,
                  "total_gfa_sqm": 3500, "parking_spaces": 40,
                  "communal_open_space_sqm": 500, "submission_year": 2025}
        return site, scheme

    def test_features_map_scheme_fields(self):
        site, scheme = self.build_site_scheme()
        features = build_structured_features(site, scheme, self.build_bundle())
        self.assertAlmostEqual(features.loc[0, "storeys"], 5.0)
        self.assertAlmostEqual(features.loc[0, "log_units"], np.log1p(40))
        self.assertAlmostEqual(features.loc[0, "units_missing"], 0.0)
        self.assertAlmostEqual(features.loc[0, "authority_ordinal"], 0.0)
        self.assertAlmostEqual(features.loc[0, "received_year"], 2025.0)

    def test_unknown_authority_falls_back_to_median_ordinal(self):
        site, scheme = self.build_site_scheme()
        site["planning_authority"] = "Nowhere Council"
        features = build_structured_features(site, scheme, self.build_bundle())
        self.assertEqual(features.loc[0, "authority_ordinal"], 0.0)

    def test_score_and_sweep_are_deterministic_and_monotone_in_storeys(self):
        site, scheme = self.build_site_scheme()
        bundle = self.build_bundle()
        first = score_structured(site, scheme, bundle)
        second = score_structured(site, scheme, bundle)
        self.assertEqual(first["refusal_probability"], second["refusal_probability"])
        self.assertTrue(first["experimental"])
        sweeps = sensitivity_sweeps(site, scheme, bundle)
        storeys_sweep = [row["refusal_probability"] for row in sweeps["max_storeys"]]
        self.assertEqual(storeys_sweep, sorted(storeys_sweep), "storeys sweep should be monotone increasing")
        self.assertEqual(len(sweeps["units"]), 8)


if __name__ == "__main__":
    unittest.main()
