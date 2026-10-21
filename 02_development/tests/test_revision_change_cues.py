import unittest

from revision_change_cues import extract_review_cues


class RevisionChangeCueTests(unittest.TestCase):
    def test_returns_review_cues_only_when_refusal_theme_and_revised_text_are_relevant(self):
        cues = extract_review_cues(
            "40 apartments with limited open space and 10 parking spaces",
            "32 apartments, increased communal open space and 20 bicycle spaces",
            "Refusal due to excessive density and inadequate public open space.",
        )

        self.assertEqual(cues, ["density_scale", "open_space_amenity"])

    def test_does_not_state_that_a_change_caused_grant(self):
        cues = extract_review_cues("A house", "A house", "Refusal due to flooding.")

        self.assertEqual(cues, [])


if __name__ == "__main__":
    unittest.main()
