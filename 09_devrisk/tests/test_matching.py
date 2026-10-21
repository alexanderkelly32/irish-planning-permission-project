import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.entity_resolution import scoring  # noqa: E402


def bcms_frame():
    return pd.DataFrame(
        {
            "source_row_id": ["1__aa", "2__bb", "3__cc"],
            "dwellings_total": [24, 60, 8],
            "planning_reference": ["CN123456", "CN654321", "CN999999"],
            "description_raw": ["construction of 24 dwellings and associated site works", "apartments in two blocks", "small extension"],
            "address_full": ["Main Street, Kilcock", "Newtown Road, Naas", "Other Lane, Trim"],
            "county": ["Meath", "Kildare", "Meath"],
            "itm_easting": [701100.0, 692050.0, 703500.0],
            "itm_northing": [745050.0, 738020.0, 744000.0],
        }
    )


class NormalizationTests(unittest.TestCase):
    def test_reference_normalization(self):
        self.assertEqual(scoring.normalize_reference(" AB/123-X "), "ab123x")
        self.assertEqual(scoring.normalize_reference("ab123x"), scoring.normalize_reference("AB123X"))

    def test_address_normalization_non_destructive(self):
        normalized = scoring.normalize_address("No. 12 Main Street, Kilcock")
        self.assertIn("main", normalized)
        self.assertIn("street", normalized)
        self.assertIn("kilcock", normalized)

    def test_token_similarity(self):
        self.assertAlmostEqual(
            scoring.token_similarity("Main Street Kilcock", "Main Street Kilcock"), 1.0
        )
        self.assertAlmostEqual(
            scoring.token_similarity("Main Street Kilcock", "Other Lane Trim"), 0.0
        )


class CandidateAndScoringTests(unittest.TestCase):
    def _scheme(self):
        return {
            "scheme_id": "S1",
            "units": 24,
            "address": "Main Street, Kilcock",
            "county": "meath",
            "itm_easting": 701000.0,
            "itm_northing": 745000.0,
            "application_reference": "AA1001",
        }

    def test_candidates_filter_by_distance_units_county(self):
        candidates = scoring.generate_bcms_candidates(self._scheme(), bcms_frame(), buffer_metres=500.0, max_unit_ratio_diff=0.5)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates.iloc[0]["source_row_id"], "1__aa")

    def test_match_features_exposed(self):
        candidates = scoring.generate_bcms_candidates(self._scheme(), bcms_frame(), buffer_metres=500.0)
        features = scoring.score_bcms_candidate(self._scheme(), candidates.iloc[0])
        self.assertIn("distance_metres", features)
        self.assertIn("address_token_similarity_full", features)
        self.assertIn("uncommon_place_agreement", features)
        self.assertEqual(features["uncommon_place_agreement"], 1)
        self.assertEqual(features["county_match"], 1)

    def test_confirmed_band_close_and_place_agree(self):
        features = {
            "distance_metres": 120.0,
            "unit_ratio_diff": 0.0,
            "uncommon_place_agreement": 1,
            "county_match": 1,
            "exact_reference_match": 0,
            "planning_reference_in_text": 0,
        }
        band, _ = scoring.confidence_band(features)
        self.assertEqual(band, "confirmed")

    def test_probable_band(self):
        features = {
            "distance_metres": 400.0,
            "unit_ratio_diff": None,
            "uncommon_place_agreement": 0,
            "address_token_similarity_full": 0.5,
            "county_match": 1,
            "exact_reference_match": 0,
            "planning_reference_in_text": 0,
        }
        band, _ = scoring.confidence_band(features)
        self.assertEqual(band, "probable")

    def test_rejected_on_county_conflict(self):
        features = {
            "distance_metres": 3000.0,
            "unit_ratio_diff": None,
            "uncommon_place_agreement": 0,
            "address_token_similarity_full": 0.0,
            "county_match": 0,
            "exact_reference_match": 0,
            "planning_reference_in_text": 0,
        }
        band, _ = scoring.confidence_band(features)
        self.assertEqual(band, "rejected")

    def test_exact_reference_match_confirms(self):
        scheme = self._scheme()
        candidates = scoring.generate_bcms_candidates(scheme, bcms_frame(), buffer_metres=10000.0)
        row = candidates[candidates["source_row_id"] == "1__aa"].iloc[0]
        features = scoring.score_bcms_candidate({**scheme, "application_reference": "CN123456"}, row)
        band, reasons = scoring.confidence_band(features)
        self.assertEqual(band, "confirmed")
        self.assertIn("exact reference match", reasons)


if __name__ == "__main__":
    unittest.main()
