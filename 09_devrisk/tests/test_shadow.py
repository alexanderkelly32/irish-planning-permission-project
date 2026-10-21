"""Shadow deployment invariants: append-only, write-once, no retro-regeneration."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.shadow import log_prediction  # noqa: E402


class TestShadow(unittest.TestCase):

    def test_seed_written(self):
        path = settings.SILVER_DIR / "shadow" / "shadow_predictions.csv"
        self.assertTrue(path.exists())
        frame = pd.read_csv(path, dtype=str)
        self.assertGreater(len(frame), 0)

    def test_prediction_ids_unique(self):
        frame = pd.read_csv(settings.SILVER_DIR / "shadow" / "shadow_predictions.csv", dtype=str)
        self.assertEqual(len(frame["prediction_id"]), frame["prediction_id"].nunique())

    def test_write_once(self):
        import devrisk.shadow as shadow_mod
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            shadow_mod.TABLE_PATH = Path(tmp) / "shadow_test.csv"
            shadow_mod.log_prediction(case_key="__test_key__", model_version="test_v0",
                                      state_at_prediction="final_grant",
                                      target_transition="final_grant->commenced",
                                      prediction={"median_days": 1.0},
                                      timestamp="2026-01-01T00:00:00+00:00")
            with self.assertRaises(ValueError):
                shadow_mod.log_prediction(case_key="__test_key__", model_version="test_v0",
                                          state_at_prediction="final_grant",
                                          target_transition="final_grant->commenced",
                                          prediction={"median_days": 999.0},
                                          timestamp="2026-01-01T00:00:00+00:00")

    def test_seed_timestamp_frozen(self):
        frame = pd.read_csv(settings.SILVER_DIR / "shadow" / "shadow_predictions.csv", dtype=str)
        self.assertTrue((frame["prediction_timestamp"] == "2026-10-01T00:00:00+00:00").all())


if __name__ == "__main__":
    unittest.main()
