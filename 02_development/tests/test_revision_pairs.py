import unittest

import pandas as pd

from revision_pairs import build_revision_pairs, normalize_address


class RevisionPairTests(unittest.TestCase):
    def test_normalize_address_removes_format_noise(self):
        self.assertEqual(normalize_address(" 1, Main-Road, Dublin  "), "1 main road dublin")

    def test_same_site_refusal_to_later_grant_is_high_confidence(self):
        data = pd.DataFrame([
            {"case_key": "a", "SiteId": "site-1", "PlanningAuthority": "Council", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "REFUSED", "ReceivedDate": "2024-01-01", "units_total_best": 40},
            {"case_key": "b", "SiteId": "site-1", "PlanningAuthority": "Council", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "36 apartments revised", "Decision": "CONDITIONAL", "ReceivedDate": "2024-04-01", "units_total_best": 36},
        ])
        pairs = build_revision_pairs(data)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs.iloc[0]["match_method"], "site_id")
        self.assertGreaterEqual(pairs.iloc[0]["confidence_same_project"], 0.95)
        self.assertEqual(pairs.iloc[0]["units_delta"], -4.0)
        self.assertEqual(pairs.iloc[0]["original_description"], "40 apartments")
        self.assertEqual(pairs.iloc[0]["revised_description"], "36 apartments revised")

    def test_address_fallback_requires_description_similarity(self):
        data = pd.DataFrame([
            {"case_key": "a", "PlanningAuthority": "Council", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments with access", "Decision": "REFUSED", "ReceivedDate": "2024-01-01", "units_total_best": 40},
            {"case_key": "b", "PlanningAuthority": "Council", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "38 apartments with access", "Decision": "GRANTED", "ReceivedDate": "2024-03-01", "units_total_best": 38},
            {"case_key": "c", "PlanningAuthority": "Council", "DevelopmentAddress": "2 Other Road", "DevelopmentDescription": "retention of a shed", "Decision": "GRANTED", "ReceivedDate": "2024-04-01", "units_total_best": 1},
        ])
        pairs = build_revision_pairs(data)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs.iloc[0]["revised_case_key"], "b")
        self.assertEqual(pairs.iloc[0]["match_method"], "address_description")

    def test_address_fallback_rejects_dissimilar_pair(self):
        data = pd.DataFrame([
            {"case_key": "a", "PlanningAuthority": "Council", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments with access", "Decision": "REFUSED", "ReceivedDate": "2024-01-01"},
            {"case_key": "b", "PlanningAuthority": "Council", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "retention of a shed", "Decision": "GRANTED", "ReceivedDate": "2024-03-01"},
        ])
        self.assertTrue(build_revision_pairs(data).empty)

    def test_same_site_identifier_is_scoped_to_authority(self):
        data = pd.DataFrame([
            {"case_key": "a", "SiteId": "100", "PlanningAuthority": "Council A", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "REFUSED", "ReceivedDate": "2024-01-01"},
            {"case_key": "b", "SiteId": "100", "PlanningAuthority": "Council B", "DevelopmentAddress": "2 Other Road", "DevelopmentDescription": "40 apartments", "Decision": "GRANTED", "ReceivedDate": "2024-03-01"},
        ])
        self.assertTrue(build_revision_pairs(data).empty)

    def test_same_application_event_variant_is_not_a_revision_pair(self):
        data = pd.DataFrame([
            {"case_key": "council_sd05a_0090", "PlanningAuthority": "Council", "ApplicationNumber": "SD05A/0090", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "REFUSED", "ReceivedDate": "2024-01-01"},
            {"case_key": "council_sd05a_0090_ep", "PlanningAuthority": "Council", "ApplicationNumber": "SD05A/0090 EP", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "GRANTED", "ReceivedDate": "2024-03-01"},
        ])
        self.assertTrue(build_revision_pairs(data).empty)

    def test_single_e_event_suffix_is_not_a_revision_pair(self):
        data = pd.DataFrame([
            {"case_key": "council_d19a_0244", "PlanningAuthority": "Council", "ApplicationNumber": "D19A/0244", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "REFUSED", "ReceivedDate": "2024-01-01"},
            {"case_key": "council_d19a_0244_e", "PlanningAuthority": "Council", "ApplicationNumber": "D19A/0244 E", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "GRANTED", "ReceivedDate": "2024-03-01"},
        ])
        self.assertTrue(build_revision_pairs(data).empty)

    def test_extension_of_permission_slash_index_is_not_a_revision_pair(self):
        data = pd.DataFrame([
            {"case_key": "council_sd18a_0213", "PlanningAuthority": "Council", "ApplicationNumber": "SD18A/0213", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "REFUSED", "ReceivedDate": "2024-01-01"},
            {"case_key": "council_sd19a_0319_ep_2", "PlanningAuthority": "Council", "ApplicationNumber": "SD19A/0319/EP/2", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "GRANTED", "ReceivedDate": "2024-03-01"},
        ])
        self.assertTrue(build_revision_pairs(data).empty)

    def test_plain_reference_without_event_suffix_still_pairs(self):
        data = pd.DataFrame([
            {"case_key": "council_sd18a_0213", "PlanningAuthority": "Council", "ApplicationNumber": "SD18A/0213", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "REFUSED", "ReceivedDate": "2024-01-01"},
            {"case_key": "council_sd19a_0319", "PlanningAuthority": "Council", "ApplicationNumber": "SD19A/0319", "DevelopmentAddress": "1 Main Road", "DevelopmentDescription": "40 apartments", "Decision": "GRANTED", "ReceivedDate": "2024-03-01"},
        ])
        self.assertEqual(len(build_revision_pairs(data)), 1)


if __name__ == "__main__":
    unittest.main()
