import math
import unittest

import pandas as pd

from structured_feature_utils import add_structured_scheme_features


class StructuredFeatureUtilsTests(unittest.TestCase):
    def test_derives_logs_density_and_missingness(self):
        data = pd.DataFrame({"NumResidentialUnits": [10], "AreaofSite": [0.5], "FloorArea": [250]})
        out = add_structured_scheme_features(data)
        self.assertAlmostEqual(out.loc[0, "log_submitted_units"], math.log1p(10))
        self.assertAlmostEqual(out.loc[0, "density_units_per_ha"], 20.0)
        self.assertEqual(out.loc[0, "area_missing"], 0.0)

    def test_missing_values_are_flagged_without_fabricating_density(self):
        data = pd.DataFrame({"NumResidentialUnits": [None], "AreaofSite": [None], "FloorArea": [None]})
        out = add_structured_scheme_features(data)
        self.assertTrue(pd.isna(out.loc[0, "density_units_per_ha"]))
        self.assertEqual(out.loc[0, "units_missing"], 1.0)
        self.assertEqual(out.loc[0, "floor_area_missing"], 1.0)


if __name__ == "__main__":
    unittest.main()
