import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.reporting import analyst_review  # noqa: E402


class OverrideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_record_and_load_override(self):
        analyst_review.record_override(
            "S1", "refusal_probability", 0.18, 0.30,
            "planner judgment", "manual review", "analyst_a", overrides_dir=self.dir,
        )
        records = analyst_review.load_overrides("S1", overrides_dir=self.dir)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["original_value"], 0.18)
        self.assertEqual(records[0]["replacement_value"], 0.3)
        self.assertEqual(records[0]["reviewer"], "analyst_a")

    def test_override_never_mutates_model_value(self):
        analyst_review.record_override(
            "S1", "refusal_probability", 0.18, 0.30,
            "reason", "evidence", "a", overrides_dir=self.dir,
        )
        payload = {"planning_outcome": {"refusal_probability": 0.18, "grant_probability": 0.82}}
        applied = analyst_review.apply_overrides(payload, analyst_review.load_overrides("S1", overrides_dir=self.dir))
        self.assertEqual(applied["planning_outcome"]["refusal_probability"], 0.18)  # untouched
        self.assertEqual(applied["planning_outcome"]["refusal_probability_override"], 0.3)
        self.assertEqual(applied["overrides"][0]["target"], "refusal_probability")

    def test_append_only(self):
        analyst_review.record_override("S2", "fi_probability", 0.5, 0.6, "r1", "e1", "a", overrides_dir=self.dir)
        analyst_review.record_override("S2", "fi_probability", 0.6, 0.7, "r2", "e2", "b", overrides_dir=self.dir)
        records = analyst_review.load_overrides("S2", overrides_dir=self.dir)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["replacement_value"], 0.6)
        self.assertEqual(records[1]["replacement_value"], 0.7)


class PdfRenderTests(unittest.TestCase):
    def test_pdf_renders_markdown(self):
        with tempfile.TemporaryDirectory() as temp:
            out = analyst_review.render_pdf(
                "# Title\n\n## Section\n\n- bullet one with a very long unbroken token "
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n\n"
                "> banner text\n\nplain paragraph here",
                scheme_id="S9",
                out_path=Path(temp) / "out.pdf",
            )
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
