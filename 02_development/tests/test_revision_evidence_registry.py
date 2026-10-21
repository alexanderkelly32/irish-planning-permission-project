import unittest

import pandas as pd

from revision_evidence_registry import (
    build_revision_evidence_registry,
    build_revision_intervention_evidence,
    summarize_completed_annotations,
    summarize_observed_deltas,
    validate_completed_annotations,
)


class RevisionEvidenceRegistryTests(unittest.TestCase):
    def test_builds_annotation_rows_without_treating_missing_deltas_as_no_change(self):
        accepted = pd.DataFrame([
            {
                "original_case_key": "a__1",
                "revised_case_key": "a__2",
                "audit_status": "accepted",
                "feature_delta_json": '{"units": {"from": 20, "to": 16, "delta": -4}}',
                "extracted_reason_for_refusal": "Excessive density and inadequate open space.",
                "original_source_url": "https://example.test/original",
                "revised_source_url": "https://example.test/revised",
            },
            {
                "original_case_key": "b__1",
                "revised_case_key": "b__2",
                "audit_status": "accepted",
                "feature_delta_json": "{}",
                "extracted_reason_for_refusal": "",
            },
        ])

        registry = build_revision_evidence_registry(accepted)

        self.assertEqual(registry["annotation_status"].tolist(), ["needs_change_annotation", "needs_change_annotation"])
        self.assertEqual(registry.loc[0, "observed_units_delta"], -4.0)
        self.assertTrue(pd.isna(registry.loc[1, "observed_units_delta"]))
        self.assertEqual(registry.loc[0, "refusal_reason_available"], True)
        self.assertEqual(registry.loc[0, "original_source_url"], "https://example.test/original")
        self.assertEqual(registry.loc[0, "revised_source_url"], "https://example.test/revised")

    def test_summarizes_only_observed_numeric_changes(self):
        registry = pd.DataFrame({"observed_units_delta": [-4.0, None, 0.0], "observed_storeys_delta": [None, 1.0, None]})

        summary = summarize_observed_deltas(registry)

        self.assertEqual(summary["units"]["observed_pairs"], 2)
        self.assertEqual(summary["units"]["decreased"], 1)
        self.assertEqual(summary["storeys"]["increased"], 1)

    def test_validates_completed_manual_annotations(self):
        annotations = pd.DataFrame([{
            "original_case_key": "a__1",
            "revised_case_key": "a__2",
            "annotation_status": "annotated",
            "addressed_refusal_theme": "partial",
            "change_layout_design": "True",
            "change_access_parking": "False",
            "change_open_space_amenity": "False",
            "change_drainage_environment": "False",
            "change_policy_land_use": "False",
            "source_backed_change_note": "Units reduced from 20 to 16.",
            "annotation_confidence": "high",
        }])

        validated = validate_completed_annotations(annotations)

        self.assertEqual(validated.loc[0, "addressed_refusal_theme"], "partial")
        self.assertTrue(validated.loc[0, "change_layout_design"])

    def test_rejects_completed_annotation_without_a_source_backed_note(self):
        annotations = pd.DataFrame([{
            "original_case_key": "a__1",
            "revised_case_key": "a__2",
            "annotation_status": "annotated",
            "addressed_refusal_theme": "yes",
            "change_layout_design": True,
            "change_access_parking": False,
            "change_open_space_amenity": False,
            "change_drainage_environment": False,
            "change_policy_land_use": False,
            "source_backed_change_note": "",
            "annotation_confidence": "high",
        }])

        with self.assertRaisesRegex(ValueError, "source_backed_change_note"):
            validate_completed_annotations(annotations)

    def test_intervention_export_excludes_unclear_relationships(self):
        annotations = pd.DataFrame([
            {
                "original_case_key": "a__1", "revised_case_key": "a__2",
                "annotation_status": "annotated", "addressed_refusal_theme": "partial",
                "change_layout_design": True, "change_access_parking": False,
                "change_open_space_amenity": False, "change_drainage_environment": False,
                "change_policy_land_use": False, "source_backed_change_note": "Units reduced.",
                "annotation_confidence": "high",
            },
            {
                "original_case_key": "b__1", "revised_case_key": "b__2",
                "annotation_status": "annotated", "addressed_refusal_theme": "unclear",
                "change_layout_design": True, "change_access_parking": False,
                "change_open_space_amenity": False, "change_drainage_environment": False,
                "change_policy_land_use": False, "source_backed_change_note": "Descriptions differ.",
                "annotation_confidence": "medium",
            },
        ])

        evidence = build_revision_intervention_evidence(annotations)

        self.assertEqual(evidence["original_case_key"].tolist(), ["a__1"])
        self.assertEqual(evidence["evidence_scope"].tolist(), ["partial_support"])

    def test_summarizes_usable_and_context_only_annotations(self):
        annotations = pd.DataFrame([
            {
                "original_case_key": key, "revised_case_key": f"{key}r",
                "annotation_status": "annotated", "addressed_refusal_theme": relationship,
                "change_layout_design": changed, "change_access_parking": False,
                "change_open_space_amenity": False, "change_drainage_environment": False,
                "change_policy_land_use": False, "source_backed_change_note": "Reviewed.",
                "annotation_confidence": confidence,
            }
            for key, relationship, changed, confidence in [
                ("a", "yes", True, "high"),
                ("b", "partial", True, "medium"),
                ("c", "unclear", True, "low"),
            ]
        ])

        summary = summarize_completed_annotations(annotations)

        self.assertEqual(summary["annotated_pair_count"], 3)
        self.assertEqual(summary["intervention_evidence_pair_count"], 2)
        self.assertEqual(summary["context_only_pair_count"], 1)
        self.assertEqual(summary["confidence_counts"], {"high": 1, "medium": 1, "low": 1})


if __name__ == "__main__":
    unittest.main()
