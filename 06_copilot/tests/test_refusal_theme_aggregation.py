import tempfile
import unittest
from pathlib import Path

import pandas as pd

from refusal_theme_aggregation import (
    aggregate_refusal_themes_sourced,
    build_refusal_theme_index,
    extraction_provenance_label,
    refusal_theme_coverage_note,
)
from scenario_evidence_service import summarize_scenario_evidence


class RefusalThemeAggregationTests(unittest.TestCase):
    def setUp(self):
        self.index_csv = Path(tempfile.mkdtemp()) / "refusal_reasons_cases_master.csv"
        pd.DataFrame([
            {
                "case_key": "council_1",
                "source_file": "rejected_decisions\\Council_1_Decision.pdf",
                "available_files": "Council_1_Decision.pdf",
                "extraction_source": "pdf_ocr",
                "extraction_method": "numbered",
                "reason_count": 2,
                "reasons_joined": "The proposal would harm residential amenity.",
                "case_primary_tags": "residential_amenity",
                "case_top_primary_tag": "residential_amenity",
            },
            {
                "case_key": "council_2",
                "source_file": "rejected_decisions\\Council_2_Decision.pdf",
                "available_files": "Council_2_Decision.pdf",
                "extraction_source": "pdf_text",
                "extraction_method": "fallback",
                "reason_count": 1,
                "reasons_joined": "Inadequate access arrangements.",
                "case_primary_tags": "traffic_access",
                "case_top_primary_tag": "traffic_access",
            },
        ]).to_csv(self.index_csv, index=False)

    def test_builds_index_keyed_and_deduplicated_by_case_key(self):
        frame = pd.DataFrame([
            {
                "case_key": "council_1",
                "source_file": "first.pdf",
                "extraction_source": "pdf_ocr",
                "extraction_method": "numbered",
                "reason_count": 1,
                "reasons_joined": "x",
                "case_primary_tags": "design_layout",
                "case_top_primary_tag": "design_layout",
            },
            {
                "case_key": "council_1",
                "source_file": "second.pdf",
                "extraction_source": "pdf_text",
                "extraction_method": "fallback",
                "reason_count": 2,
                "reasons_joined": "y",
                "case_primary_tags": "design_layout",
                "case_top_primary_tag": "design_layout",
            },
        ])
        path = self.index_csv.parent / "dup.csv"
        frame.to_csv(path, index=False)
        index = build_refusal_theme_index(path)
        self.assertEqual(len(index), 1)
        self.assertEqual(index.loc["council_1", "source_file"], "first.pdf")

    def test_returns_empty_index_when_file_missing(self):
        index = build_refusal_theme_index(self.index_csv.parent / "missing.csv")
        self.assertTrue(index.empty)

    def test_aggregates_themes_with_source_linked_case_records(self):
        refused = pd.DataFrame([
            {
                "hybrid_score": 0.9,
                "case_key": "council_1",
                "PlanningAuthority": "Council One",
                "ApplicationNumber": "C/1",
                "Decision": "Refused",
                "case_primary_tags": "residential_amenity",
                "case_top_primary_tag": "residential_amenity",
                "source_url": "https://example.test/c1",
                "refusal_excerpt": "",
            },
            {
                "hybrid_score": 0.8,
                "case_key": "council_2",
                "PlanningAuthority": "Council Two",
                "ApplicationNumber": "C/2",
                "Decision": "Refused",
                "case_primary_tags": "traffic_access",
                "case_top_primary_tag": "traffic_access",
                "source_url": "https://example.test/c2",
                "refusal_excerpt": "Inadequate access arrangements.",
            },
        ])
        index = build_refusal_theme_index(self.index_csv)

        aggregation = aggregate_refusal_themes_sourced(refused, index, limit=4)

        self.assertEqual(aggregation["refused_case_count"], 2)
        self.assertEqual(aggregation["tagged_case_count"], 2)
        self.assertEqual(aggregation["linked_case_count"], 2)
        self.assertEqual([theme["tag"] for theme in aggregation["themes"]], ["residential_amenity", "traffic_access"])
        top = aggregation["themes"][0]
        self.assertEqual(top["case_count"], 1)
        case = top["cases"][0]
        self.assertEqual(case["citation"], "Council One C/1 (Refused)")
        self.assertEqual(case["source_url"], "https://example.test/c1")
        self.assertIn("Decision.pdf", case["source_file"])
        self.assertIn("OCR", case["extraction_provenance"])
        self.assertIn("amenity", case["excerpt"])

    def test_theme_case_order_ranks_higher_similarity_case_first(self):
        refused = pd.DataFrame([
            {
                "hybrid_score": 0.6,
                "case_key": "council_1",
                "PlanningAuthority": "Council One",
                "ApplicationNumber": "C/1",
                "Decision": "Refused",
                "case_primary_tags": "design_layout",
                "case_top_primary_tag": "design_layout",
                "source_url": "https://example.test/low",
            },
            {
                "hybrid_score": 0.95,
                "case_key": "council_2",
                "PlanningAuthority": "Council Two",
                "ApplicationNumber": "C/2",
                "Decision": "Refused",
                "case_primary_tags": "design_layout",
                "case_top_primary_tag": "design_layout",
                "source_url": "https://example.test/high",
            },
        ])
        aggregation = aggregate_refusal_themes_sourced(refused, None, limit=4)
        cases = aggregation["themes"][0]["cases"]
        self.assertEqual(cases[0]["source_url"], "https://example.test/high")

    def test_unindexed_case_keeps_ranked_row_provenance_without_fabrication(self):
        refused = pd.DataFrame([
            {
                "hybrid_score": 0.7,
                "case_key": "unknown_case",
                "PlanningAuthority": "Council Three",
                "ApplicationNumber": "C/3",
                "Decision": "Refused",
                "case_primary_tags": "ecology_trees",
                "case_top_primary_tag": "ecology_trees",
                "source_url": "",
                "refusal_excerpt": "",
            },
        ])
        aggregation = aggregate_refusal_themes_sourced(refused, build_refusal_theme_index(self.index_csv), limit=4)
        self.assertEqual(aggregation["linked_case_count"], 0)
        case = aggregation["themes"][0]["cases"][0]
        self.assertEqual(case["source_file"], "")
        self.assertEqual(case["extraction_provenance"], "no refusal extraction record")

    def test_empty_refused_frame_produces_no_themes(self):
        aggregation = aggregate_refusal_themes_sourced(pd.DataFrame(), None)
        self.assertEqual(aggregation["themes"], [])
        self.assertEqual(aggregation["refused_case_count"], 0)

    def test_coverage_note_is_conservative_and_counted(self):
        note = refusal_theme_coverage_note({
            "refused_case_count": 6,
            "tagged_case_count": 4,
            "linked_case_count": 3,
        })
        self.assertIn("4 of 6", note)
        self.assertIn("not predictions", note)
        self.assertEqual(refusal_theme_coverage_note({"refused_case_count": 0}), "")

    def test_provenance_label_exposes_low_confidence_extraction(self):
        label = extraction_provenance_label(pd.Series({
            "extraction_source": "pdf_text",
            "extraction_method": "fallback",
        }))
        self.assertIn("low-confidence", label)

    def test_summarize_scenario_evidence_uses_sourced_themes_when_index_given(self):
        ranked = pd.DataFrame([
            {
                "hybrid_score": 0.9,
                "case_key": "council_1",
                "PlanningAuthority": "Council One",
                "ApplicationNumber": "C/1",
                "Decision": "Refused",
                "decision_normalized": "REFUSED",
                "case_primary_tags": "residential_amenity",
                "case_top_primary_tag": "residential_amenity",
                "match_reasons": "same authority",
                "source_url": "https://example.test/c1",
                "refusal_excerpt": "",
            },
        ])
        index = build_refusal_theme_index(self.index_csv)
        summary = summarize_scenario_evidence(ranked, top_k=4, refusal_index=index)
        self.assertEqual(summary["refusal_themes"][0]["tag"], "residential_amenity")
        self.assertEqual(summary["refusal_themes"][0]["cases"][0]["case_key"], "council_1")
        self.assertIn("not predictions", summary["refusal_theme_coverage_note"])

    def test_summarize_scenario_evidence_falls_back_without_index(self):
        ranked = pd.DataFrame([
            {
                "hybrid_score": 0.9,
                "case_key": "council_1",
                "PlanningAuthority": "Council One",
                "ApplicationNumber": "C/1",
                "Decision": "Refused",
                "decision_normalized": "REFUSED",
                "case_primary_tags": "residential_amenity",
                "case_top_primary_tag": "residential_amenity",
                "match_reasons": "same authority",
                "source_url": "https://example.test/c1",
            },
        ])
        summary = summarize_scenario_evidence(ranked, top_k=4)
        self.assertEqual(summary["refusal_themes"][0]["tag"], "residential_amenity")
        self.assertNotIn("cases", summary["refusal_themes"][0])
        self.assertEqual(summary["refusal_theme_coverage_note"], "")


if __name__ == "__main__":
    unittest.main()
