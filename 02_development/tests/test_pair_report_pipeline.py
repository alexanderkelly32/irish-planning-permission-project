import unittest

import pandas as pd

import sys
sys.path.insert(0, r"02_development\scripts")

from run_pair_report_pipeline import side_rows, already_extracted  # noqa: E402


class PairReportPipelineTests(unittest.TestCase):
    def build_pairs(self):
        return pd.DataFrame([
            {
                "planning_authority": "Meath County Council",
                "original_case_key": "meath_111",
                "revised_case_key": "meath_222",
                "original_source_url": "https://www.eplanning.ie/MeathCC/AppFileRefDetails/111/0",
                "revised_source_url": "https://www.eplanning.ie/MeathCC/AppFileRefDetails/222/0",
            },
            {
                "planning_authority": "Wexford County Council",
                "original_case_key": "wex_333",
                "revised_case_key": "wex_444",
                "original_source_url": "https://planning.agileapplications.ie/wexford/application-details/1",
                "revised_source_url": "https://planning.agileapplications.ie/wexford/application-details/2",
            },
        ])

    def test_side_rows_keeps_only_supported_eplan_sides(self):
        sides = side_rows(self.build_pairs())
        refs = set(sides["ref"])
        self.assertEqual(refs, {"111", "222"})
        self.assertEqual(sides.iloc[0]["council_path"], "MeathCC")
        self.assertEqual(sides.iloc[0]["side"], "original")

    def test_already_extracted_returns_false_without_csv(self):
        side = pd.Series({
            "council_path": "NonexistentCC", "ref": "999", "council": "X",
            "side": "original", "case_key": "x", "url": "x",
        })
        self.assertFalse(already_extracted(side))


if __name__ == "__main__":
    unittest.main()
