import unittest

import pandas as pd

from full_revision_linkage import (
    apply_known_audit_labels,
    audit_labels_from_review,
    build_full_revision_candidates,
    build_stratified_review_sample,
    evaluate_known_pair_recall,
    select_residential_scope,
)


def row(case, decision, date, address="1 Main Road", description="40 apartments", **extra):
    return {
        "case_key": case,
        "PlanningAuthority": "Example Council",
        "ApplicationNumber": case,
        "Decision": decision,
        "ReceivedDate": date,
        "DevelopmentAddress": address,
        "DevelopmentDescription": description,
        "ITMEasting": extra.pop("ITMEasting", 700000),
        "ITMNorthing": extra.pop("ITMNorthing", 730000),
        **extra,
    }


class FullRevisionLinkageTests(unittest.TestCase):
    def test_residential_scope_keeps_units_or_residential_text(self):
        data = pd.DataFrame([
            {"case_key": "units", "NumResidentialUnits": 12, "DevelopmentDescription": "mixed scheme"},
            {"case_key": "text", "NumResidentialUnits": None, "DevelopmentDescription": "new apartment development"},
            {"case_key": "retirement", "NumResidentialUnits": 0, "DevelopmentDescription": "retirement village of 98 units"},
            {"case_key": "shed", "NumResidentialUnits": None, "DevelopmentDescription": "retention of agricultural shed"},
        ])

        selected = select_residential_scope(data)

        self.assertEqual(selected["case_key"].tolist(), ["units", "text", "retirement"])

    def test_exact_address_block_handles_project_histories_longer_than_two_records(self):
        data = pd.DataFrame([
            row("A1", "REFUSED", "2020-01-01", description="40 apartments with new access"),
            row("A2", "GRANTED", "2020-06-01", description="36 apartments with revised access"),
            row("A3", "GRANTED", "2021-01-01", description="34 apartments with revised access"),
        ])

        candidates, diagnostics = build_full_revision_candidates(data)

        self.assertEqual(len(candidates), 2)
        self.assertEqual(set(candidates["revised_case_key"]), {"A2", "A3"})
        self.assertTrue(candidates["blocking_methods"].str.contains("exact_address").all())
        self.assertEqual(candidates.loc[0, "planning_authority"], "Example Council")
        self.assertIn(candidates.loc[0, "revised_application_number"], {"A2", "A3"})
        self.assertEqual(diagnostics["candidate_pair_count"], 2)

    def test_spatial_block_crosses_grid_boundary_and_records_distance(self):
        data = pd.DataFrame([
            row("A1", "REFUSED", "2020-01-01", address="North side of site", ITMEasting=700099),
            row("A2", "GRANTED", "2020-05-01", address="South side of site", ITMEasting=700101),
        ])

        candidates, _ = build_full_revision_candidates(data, spatial_radius_m=25)

        self.assertEqual(len(candidates), 1)
        self.assertIn("spatial_25m", candidates.loc[0, "blocking_methods"])
        self.assertAlmostEqual(candidates.loc[0, "coordinate_distance_m"], 2.0)

    def test_excludes_same_application_event_and_excessive_time_gap(self):
        data = pd.DataFrame([
            row("A1", "REFUSED", "2020-01-01", ApplicationNumber="SD20/001"),
            row("A1_EP", "GRANTED", "2020-04-01", ApplicationNumber="SD20/001 EP"),
            row("A3", "GRANTED", "2028-01-01", ApplicationNumber="SD28/003"),
        ])

        candidates, diagnostics = build_full_revision_candidates(data, maximum_gap_years=5)

        self.assertTrue(candidates.empty)
        self.assertEqual(diagnostics["candidate_pair_count"], 0)

    def test_excludes_later_extension_event_references_even_when_base_numbers_differ(self):
        data = pd.DataFrame([
            row("refused", "REFUSED", "2023-01-01", ApplicationNumber="F23A/0646"),
            row("extension", "GRANTED", "2025-01-01", ApplicationNumber="F25A/0166E"),
            row("ep_refused", "REFUSED", "2017-01-01", ApplicationNumber="SD12A/0195/EP"),
            row("ep_granted", "GRANTED", "2018-01-01", ApplicationNumber="SD12A/0195/EP(1)"),
        ])

        candidates, _ = build_full_revision_candidates(data)

        self.assertTrue(candidates.empty)

    def test_far_exact_address_match_cannot_be_ranked_above_low_strength(self):
        data = pd.DataFrame([
            row("refused", "REFUSED", "2020-01-01", address="Townland, Example", description="dwelling", ITMEasting=700000),
            row("granted", "GRANTED", "2021-01-01", address="Townland, Example", description="dwelling", ITMEasting=702000),
        ])

        candidates, _ = build_full_revision_candidates(data)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates.loc[0, "linkage_tier"], "low")

    def test_score_is_a_transparent_strength_tier_not_a_probability(self):
        data = pd.DataFrame([
            row(
                "A1", "REFUSED", "2020-01-01", description="40 apartments with access and open space",
                ApplicantSurname="Builder Limited", DevelopmentPostcode="D01 TEST", SiteId="site-1",
            ),
            row(
                "A2", "GRANTED", "2020-05-01", description="36 apartments with revised access and open space",
                ApplicantSurname="Builder Limited", DevelopmentPostcode="D01 TEST", SiteId="site-1",
            ),
        ])

        candidates, _ = build_full_revision_candidates(data)

        self.assertGreaterEqual(candidates.loc[0, "linkage_score"], 0.75)
        self.assertEqual(candidates.loc[0, "linkage_tier"], "high")
        self.assertEqual(candidates.loc[0, "manual_review_status"], "pending")
        self.assertNotIn("probability", " ".join(candidates.columns).lower())

    def test_review_sample_is_deterministic_and_represents_each_tier(self):
        candidates = pd.DataFrame([
            {"original_case_key": f"{tier}_{i}", "revised_case_key": f"r_{tier}_{i}", "linkage_tier": tier}
            for tier in ["high", "medium", "low"] for i in range(5)
        ])

        first = build_stratified_review_sample(candidates, per_tier=2)
        second = build_stratified_review_sample(candidates, per_tier=2)

        self.assertEqual(first[["original_case_key", "revised_case_key"]].to_dict("records"), second[["original_case_key", "revised_case_key"]].to_dict("records"))
        self.assertEqual(first["linkage_tier"].value_counts().to_dict(), {"high": 2, "medium": 2, "low": 2})
        self.assertTrue(first["manual_review_notes"].eq("").all())

    def test_applies_existing_audit_labels_despite_case_key_formatting(self):
        candidates = pd.DataFrame([
            {"original_case_key": "example__ab_1", "revised_case_key": "example__ab_2", "manual_review_status": "pending"},
            {"original_case_key": "new__1", "revised_case_key": "new__2", "manual_review_status": "pending"},
        ])
        audit = pd.DataFrame([{
            "original_case_key": "example_ab1", "revised_case_key": "example_ab2",
            "audit_status": "accepted", "audit_notes": "Same revised development.",
        }])

        labelled = apply_known_audit_labels(candidates, audit)

        self.assertEqual(labelled["manual_review_status"].tolist(), ["accepted", "pending"])
        self.assertEqual(labelled["manual_review_notes"].tolist(), ["Same revised development.", ""])

    def test_converts_completed_review_rows_to_reusable_audit_labels(self):
        review = pd.DataFrame([{
            "original_case_key": "example__ab_1", "revised_case_key": "example__ab_2",
            "manual_review_status": "accepted", "manual_review_notes": "Same revised development.",
        }])

        audit = audit_labels_from_review(review)

        self.assertEqual(audit.to_dict("records"), [{
            "original_case_key": "example__ab_1", "revised_case_key": "example__ab_2",
            "audit_status": "accepted", "audit_notes": "Same revised development.",
        }])

    def test_review_sample_excludes_already_reviewed_candidates(self):
        candidates = pd.DataFrame([
            {"original_case_key": "accepted", "revised_case_key": "accepted_r", "linkage_tier": "high", "manual_review_status": "accepted"},
            {"original_case_key": "pending", "revised_case_key": "pending_r", "linkage_tier": "high", "manual_review_status": "pending"},
        ])

        sample = build_stratified_review_sample(candidates, per_tier=5)

        self.assertEqual(sample["original_case_key"].tolist(), ["pending"])

    def test_known_pair_recall_ignores_case_key_formatting(self):
        candidates = pd.DataFrame([{
            "original_case_key": "example_council__ab_123",
            "revised_case_key": "example_council__cd_456",
        }])
        known = pd.DataFrame([
            {"original_case_key": "example_council_ab123", "revised_case_key": "example_council_cd456"},
            {"original_case_key": "missing_1", "revised_case_key": "missing_2"},
        ])

        result = evaluate_known_pair_recall(candidates, known)

        self.assertEqual(result["known_pair_count"], 2)
        self.assertEqual(result["recalled_pair_count"], 1)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(len(result["missed_pairs"]), 1)


if __name__ == "__main__":
    unittest.main()
