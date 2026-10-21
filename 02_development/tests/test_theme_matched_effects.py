import json
import sys
import unittest

import pandas as pd

sys.path.insert(0, r"02_development\scripts")
from build_theme_matched_effects import build_theme_matched_effects  # noqa: E402


class ThemeMatchedEffectsTests(unittest.TestCase):
    def test_on_diagnosis_contrast_isolates_theme_matched_pairs(self):
        granted = pd.DataFrame([
            {"lever": "parking_spaces", "direction": "down", "themes": ["traffic_access"], "outcome": "granted"},
            {"lever": "parking_spaces", "direction": "down", "themes": ["traffic_access"], "outcome": "granted"},
            {"lever": "parking_spaces", "direction": "down", "themes": ["design_layout"], "outcome": "granted"},
            {"lever": "parking_spaces", "direction": "down", "themes": [], "outcome": "granted"},
        ])
        refused = pd.DataFrame([
            {"lever": "parking_spaces", "direction": "down", "themes": ["traffic_access"], "outcome": "refused"},
            {"lever": "parking_spaces", "direction": "down", "themes": ["design_layout"], "outcome": "refused"},
            {"lever": "parking_spaces", "direction": "down", "themes": [], "outcome": "refused"},
            {"lever": "parking_spaces", "direction": "down", "themes": ["design_layout"], "outcome": "refused"},
        ])
        effects = build_theme_matched_effects(granted, refused)
        rows = {(r["lever"], r["direction"], r["diagnosis"]): r for r in effects["rows"]}
        on_diag = rows[("parking_spaces", "down", "on_diagnosis")]
        self.assertEqual(on_diag["granted"], 2)
        self.assertEqual(on_diag["refused"], 1)
        self.assertEqual(on_diag["grant_share"], round(2 / 3, 4))
        off_diag = rows[("parking_spaces", "down", "off_diagnosis")]
        self.assertEqual(off_diag["granted"], 2)
        self.assertEqual(off_diag["refused"], 3)
        self.assertEqual(off_diag["grant_share"], round(2 / 5, 4))


if __name__ == "__main__":
    unittest.main()
