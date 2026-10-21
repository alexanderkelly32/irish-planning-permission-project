import unittest

import pandas as pd

from audit_structured_variables import (
    derive_density_plot_ratio,
    distribution_stats,
    field_coverage,
    grouped_coverage,
    recommend_ready_fields,
)


class StructuredVariableAuditTests(unittest.TestCase):
    def build_frame(self):
        return pd.DataFrame({
            "PlanningAuthority": ["A", "A", "B", "B", "B"],
            "ReceivedDate": ["2023-01-01"] * 5,
            "NumResidentialUnits": [40, 20, None, 10000, 5],
            "AreaofSite": [0.5, 0.2, 0.1, None, 0.05],
            "FloorArea": [4000, 1800, None, 90000, 500],
        })

    def test_field_coverage_counts_numeric_values(self):
        coverage = field_coverage(
            self.build_frame(),
            {"units": "NumResidentialUnits", "missing_column": "does_not_exist"},
        )
        self.assertEqual(coverage["units"]["non_null"], 4)
        self.assertAlmostEqual(coverage["units"]["fraction"], 0.8)
        self.assertTrue(coverage["missing_column"]["column_missing"])

    def test_grouped_coverage_breaks_down_by_group(self):
        frame = self.build_frame()
        table = grouped_coverage(frame, "NumResidentialUnits", "PlanningAuthority", minimum_rows=1)
        by_authority = dict(zip(table["PlanningAuthority"], table["fraction"]))
        self.assertAlmostEqual(by_authority["A"], 1.0)
        self.assertAlmostEqual(by_authority["B"], 2 / 3, places=4)

    def test_distribution_stats_flag_implausible_values(self):
        stats = distribution_stats(pd.Series([40, 20, 10000, 5, None]), bounds=(1.0, 2000.0))
        self.assertEqual(stats["non_null"], 4)
        self.assertEqual(stats["implausible_above_max"], 1)
        self.assertEqual(stats["implausible_below_min"], 0)
        self.assertEqual(stats["median"], 30.0)

    def test_distribution_stats_empty(self):
        self.assertEqual(distribution_stats(pd.Series([None, None])), {"non_null": 0})

    def test_derive_density_and_plot_ratio(self):
        frame = derive_density_plot_ratio(self.build_frame())
        self.assertAlmostEqual(frame.loc[0, "density_units_per_ha"], 80.0)
        self.assertAlmostEqual(frame.loc[0, "plot_ratio_proxy"], 0.8)

    def test_recommendation_gates_on_coverage_thresholds(self):
        register = {
            "units": {"rows": 200000, "non_null": 150000, "fraction": 0.75, "column_missing": False},
            "site_area_ha": {"rows": 200000, "non_null": 150000, "fraction": 0.75, "column_missing": False},
        }
        extracted = {
            "units": {"rows": 10000, "non_null": 9000, "fraction": 0.9, "column_missing": False},
            "max_storeys": {"rows": 10000, "non_null": 4000, "fraction": 0.4, "column_missing": False},
            "parking_spaces": {"rows": 10000, "non_null": 2000, "fraction": 0.2, "column_missing": False},
        }
        recommendation = recommend_ready_fields(register, extracted)
        ready = {item["variable"]: item["tier"] for item in recommendation["ready_to_model"]}
        self.assertIn("units", ready)
        self.assertIn("max_storeys", ready)
        self.assertNotIn("parking_spaces", ready)
        self.assertIn("max_height_m", recommendation["absent_entirely"])


if __name__ == "__main__":
    unittest.main()
