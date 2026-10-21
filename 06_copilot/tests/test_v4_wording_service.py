import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "06_copilot" / "scripts"))
import v4_wording_service as wording  # noqa: E402
from v4_wording_service import _fix_articles, _splice_numbers, _similarity_ratio  # noqa: E402


class WordingServiceTests(unittest.TestCase):
    def test_detect_scheme_kind(self):
        self.assertEqual(wording.detect_scheme_kind("single storey extension to the rear", 1), "extension")
        self.assertEqual(wording.detect_scheme_kind("construction of a single dwelling", 1), "one-off house")
        self.assertEqual(wording.detect_scheme_kind("construction of 47 apartments", 47), "new build")

    def test_fix_articles(self):
        self.assertEqual(_fix_articles("an duplex apartment block"), "a duplex apartment block")
        self.assertEqual(_fix_articles("an residential development"), "a residential development")
        self.assertEqual(_fix_articles("a apartment block"), "an apartment block")

    def test_splice_numbers(self):
        template = "construction of 47 no. apartments and 21 no. houses"
        spliced = _splice_numbers(template, 12, None)
        self.assertIn("12 no. apartments", spliced)
        self.assertIn("21 no. houses", spliced)

    def test_similarity_ratio(self):
        self.assertEqual(_similarity_ratio("construction of twelve houses", "construction of twelve houses"), 1.0)
        self.assertEqual(_similarity_ratio("", "construction"), 0.0)
        ratio = _similarity_ratio("construction of a housing development", "construction of a residential development")
        self.assertGreater(ratio, 0.5)
        self.assertLess(ratio, 1.0)

    def test_swap_variant_grammar_and_case(self):
        from v4_wording_service import SWAPS

        risky = sorted({pair[0] for pair in SWAPS})
        self.assertIn("housing development", risky)
        self.assertIn("apartment block", risky)


if __name__ == "__main__":
    unittest.main()
