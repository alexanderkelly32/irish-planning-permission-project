import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "09_devrisk"))

import pandas as pd

from devrisk.models.ecad_pipeline import (
    consistency_score,
    created_after_grant,
    points_in_site,
    scheme_fingerprint,
)


class TestEcadPipeline(unittest.TestCase):
    def setUp(self):
        self.points = pd.DataFrame({
            "easting": [650000.0, 650010.0, 650020.0, 650800.0, 650015.0],
            "northing": [745000.0, 745005.0, 745010.0, 745500.0, 745020.0],
            "created_date": ["2019-01-01", "2019-03-01", "2020-06-01", "2019-02-01", "2015-01-01"],
            "address": ["1 Oakfield", "2 Oakfield", "3 Oakfield", "4 Elsewhere", "5 Oakfield old"],
            "eircode": ["D01AAAA", "D01AAAB", "D01AAAC", "D01AAAD", "D01AAAE"],
            "building_use": ["RES", "RES", "RES", "RES", "RES"],
        })
        self.scheme = {
            "scheme_id": "S1",
            "itm_easting": 650000.0,
            "itm_northing": 745000.0,
            "grant_date": "2018-12-01",
            "units": 4,
        }

    def test_points_in_site_radius(self):
        inside = points_in_site(self.scheme, self.points, radius_metres=250.0)
        self.assertEqual(len(inside), 4)  # 650800/745500 is ~500m away
        self.assertTrue((inside["distance_metres"] < 250).all())

    def test_created_after_grant_filters_old_points(self):
        inside = points_in_site(self.scheme, self.points, radius_metres=250.0)
        created = created_after_grant(inside, pd.Timestamp(self.scheme["grant_date"]))
        self.assertNotIn("D01AAAE", set(created["eircode"]))  # 2015 created, pre-grant
        self.assertEqual(len(created), 3)

    def test_consistency_ratios(self):
        inside = points_in_site(self.scheme, self.points, radius_metres=250.0)
        created = created_after_grant(inside, pd.Timestamp(self.scheme["grant_date"]))
        result = consistency_score(self.scheme, created)
        self.assertEqual(result["address_points_in_site"], 3)
        self.assertAlmostEqual(result["unit_ratio"], 0.75)

    def test_scheme_fingerprint_with_ppr(self):
        sales = pd.DataFrame({"eircode": ["D01AAAA", "D01ZZZZ"], "price": [300000, 400000]})
        result = scheme_fingerprint(self.scheme, self.points, ppr_sales=sales)
        self.assertEqual(result["ppr_matched_of_points"], 1)
        self.assertEqual(result["ppr_overlap_ratio"], round(1 / 3, 3))

    def test_fingerprint_no_ppr(self):
        result = scheme_fingerprint(self.scheme, self.points)
        self.assertNotIn("ppr_matched_of_points", result)


if __name__ == "__main__":
    unittest.main()
