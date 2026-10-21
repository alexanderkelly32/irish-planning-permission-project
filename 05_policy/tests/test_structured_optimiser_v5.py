import unittest

import numpy as np
import pandas as pd

from structured_optimiser_v5 import (
    AUTHORITY_CODE_MAP,
    V5_FEATURES,
    build_v5_cohort,
    dedupe_reports,
    join_planner_features,
    load_planner_reports,
    map_report_columns,
)
from structured_optimiser import build_cohort


class StructuredOptimiserV5Tests(unittest.TestCase):
    def build_source(self):
        rows = []
        for index in range(120):
            year = 2023 if index < 90 else 2025
            rows.append({
                "case_key": f"k{index}",
                "PlanningAuthority": "Meath County Council",
                "ApplicationNumber": str(1000 + index),
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

    def build_reports(self):
        rows = []
        for index in range(0, 60, 2):
            rows.append({
                "case_key": str(1000 + index),
                "authority": "MeathCC",
                "doc_max_storeys": 2 + index % 4,
                "doc_max_height_m": 7.0 + index,
                "doc_nearest_dwelling_separation_m": 18.0,
                "doc_vehicular_access_points": 1,
            })
            rows.append({
                "case_key": str(1000 + index),
                "authority": "MeathCC",
                "doc_max_storeys": None,
                "doc_max_height_m": 7.5 + index,
                "doc_cycle_parking_spaces": 20,
            })
        frame = pd.DataFrame(rows)
        frame["app_number"] = frame["case_key"].astype(str).str.strip()
        frame["_authority"] = AUTHORITY_CODE_MAP["MeathCC"]
        return map_report_columns(frame)

    def test_authority_map_covers_councils(self):
        self.assertEqual(AUTHORITY_CODE_MAP["KildareCC"], "Kildare County Council")
        self.assertEqual(AUTHORITY_CODE_MAP["LimerickCC"], "Limerick County Council")

    def test_dedupe_reports_combines_columns_across_rows(self):
        reports = self.build_reports()
        deduped = dedupe_reports(reports)
        self.assertEqual(len(deduped), 30)
        row = deduped[deduped["app_number"] == "1000"].iloc[0]
        self.assertEqual(row["report_storeys"], 2)
        self.assertIsNotNone(row["report_cycle_parking_spaces"])
        self.assertEqual(row["report_max_height_m"], 7.0)

    def test_join_adds_report_features_and_flags(self):
        cohort = build_cohort(self.build_source())
        joined = join_planner_features(cohort, self.build_reports())
        self.assertIn("log_max_height_m", joined.columns)
        self.assertIn("height_missing", joined.columns)
        self.assertIn("report_joined", joined.columns)
        self.assertEqual(int(joined["report_joined"].sum()), 30)
        self.assertGreater(joined["height_missing"].eq(0).sum(), 0)

    def test_v5_cohort_has_all_features(self):
        cohort = build_v5_cohort(self.build_source(), self.build_reports())
        for feature in V5_FEATURES:
            self.assertIn(feature, cohort.columns)
        self.assertEqual(len(cohort), 120)
        self.assertIn("storeys", cohort.columns)
        self.assertTrue(cohort["storeys"].notna().all())

    def test_storeys_prefer_report_values(self):
        source = self.build_source()
        cohort = build_cohort(source)
        report = pd.DataFrame([{
            "case_key": "1001",
            "authority": "MeathCC",
            "doc_max_storeys": 9,
            "doc_max_height_m": 11.0,
        }])
        report["app_number"] = report["case_key"].astype(str).str.strip()
        report["_authority"] = AUTHORITY_CODE_MAP["MeathCC"]
        joined = join_planner_features(cohort, map_report_columns(report))
        row = joined[joined["ApplicationNumber"] == "1001"].iloc[0]
        self.assertEqual(row["storeys"], 9)


if __name__ == "__main__":
    unittest.main()
