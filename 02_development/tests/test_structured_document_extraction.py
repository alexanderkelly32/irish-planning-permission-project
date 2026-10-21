import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from structured_document_extraction import (
    build_document_cohort,
    build_verification_sample,
    campaign_coverage_report,
    chunk_text,
    flatten_doc_batch_output,
    merge_campaign_results,
    prepare_campaign,
)


class StructuredDocumentExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "ocr").mkdir()
        (self.tmp / "fi").mkdir()
        (self.tmp / "ocr" / "Carlow_County_Council_17373_Decision_ocr.txt").write_text(
            "22 no. dwellings in blocks of 2 storey townhouses. Provision of 40 car parking spaces.", encoding="utf-8"
        )
        (self.tmp / "ocr" / "Empty_County_Council_1_Decision_ocr.txt").write_text("", encoding="utf-8")
        (self.tmp / "fi" / "Carlow_County_Council_17154_carlow_county_council_17154_fi_text.txt").write_text(
            "FI request: clarify the upper floor setback of the 3 storey block.", encoding="utf-8"
        )

    def test_builds_cohort_from_both_document_sources(self):
        cohort = build_document_cohort(self.tmp / "ocr", self.tmp / "fi")
        self.assertEqual(len(cohort), 2)
        self.assertEqual(set(cohort["document_type"]), {"decision", "fi"})
        self.assertTrue((cohort["doc_chars"] > 0).all())

    def test_chunk_text_splits_with_overlap(self):
        text = "word " * 100
        chunks = chunk_text(text, max_chars=120, overlap=20)
        self.assertGreater(len(chunks), 1)
        self.assertLessEqual(max(len(chunk) for chunk in chunks), 120)

    def test_prepare_campaign_builds_request_parts_and_manifest(self):
        cohort = build_document_cohort(self.tmp / "ocr", self.tmp / "fi")
        parts, manifest = prepare_campaign(cohort, requests_per_part=1)
        self.assertEqual(len(parts), 2)
        self.assertEqual(len(manifest), 2)
        request = parts[0][0]
        self.assertEqual(request["method"], "POST")
        user = json.loads(request["body"]["messages"][1]["content"])
        self.assertIn("text", user)
        self.assertEqual(user["case_key"], "carlow_county_council_17373")

    def test_flatten_and_merge_with_provenance_and_plausibility(self):
        jsonl = "\n".join([
            json.dumps({
                "custom_id": "doc-extract-row-0-c0",
                "response": {"body": {"choices": [{"message": {"content": json.dumps({
                    "status": "ok", "max_height_m": None, "height_context": None,
                    "max_storeys": 2.0, "front_setback_m": None, "rear_setback_m": None,
                    "side_setback_m": None, "upper_floor_setback_m": None,
                    "nearest_dwelling_separation_m": None, "opposing_window_separation_m": None,
                    "parking_spaces": 40.0, "cycle_parking_spaces": None,
                    "private_open_space_sqm": None, "communal_open_space_sqm": None,
                    "vehicular_access_points": None, "confidence": "high", "note": "explicit",
                })}}]}},
            }),
            json.dumps({
                "custom_id": "doc-extract-row-0-c0",
                "response": {"body": {"choices": [{"message": {"content": json.dumps({
                    "status": "ok", "max_height_m": 900.0, "height_context": "overall",
                    "max_storeys": 3.0, "front_setback_m": None, "rear_setback_m": None,
                    "side_setback_m": None, "upper_floor_setback_m": None,
                    "nearest_dwelling_separation_m": None, "opposing_window_separation_m": None,
                    "parking_spaces": None, "cycle_parking_spaces": None,
                    "private_open_space_sqm": None, "communal_open_space_sqm": None,
                    "vehicular_access_points": None, "confidence": "medium", "note": "bogus height",
                })}}]}},
            }),
        ])
        cohort = build_document_cohort(self.tmp / "ocr", self.tmp / "fi")
        flattened = flatten_doc_batch_output(jsonl)
        self.assertEqual(len(flattened), 2)
        merged = merge_campaign_results(cohort, flattened, model_version="gpt-5")
        row = merged[merged["row_number"] == 0].iloc[0]
        self.assertEqual(row["doc_max_storeys"], 2.0, "the high-confidence extraction wins over the medium one")
        self.assertTrue(pd.isna(row["doc_max_height_m"]), "height was null in the winning extraction")
        self.assertEqual(row["doc_parking_spaces"], 40.0)
        self.assertEqual(row["doc_extraction_model"], "gpt-5")

    def test_plausibility_drops_implausible_height_even_when_high_confidence(self):
        jsonl = json.dumps({
            "custom_id": "doc-extract-row-0-c0",
            "response": {"body": {"choices": [{"message": {"content": json.dumps({
                "status": "ok", "max_height_m": 900.0, "height_context": "overall",
                "max_storeys": 3.0, "front_setback_m": None, "rear_setback_m": None,
                "side_setback_m": None, "upper_floor_setback_m": None,
                "nearest_dwelling_separation_m": None, "opposing_window_separation_m": None,
                "parking_spaces": None, "cycle_parking_spaces": None,
                "private_open_space_sqm": None, "communal_open_space_sqm": None,
                "vehicular_access_points": None, "confidence": "high", "note": "bogus height",
            })}}]}},
        })
        cohort = build_document_cohort(self.tmp / "ocr", self.tmp / "fi")
        merged = merge_campaign_results(cohort, flatten_doc_batch_output(jsonl), model_version="gpt-5")
        row = merged[merged["row_number"] == 0].iloc[0]
        self.assertIsNone(row["doc_max_height_m"])
        self.assertEqual(row["doc_max_storeys"], 3.0)

    def test_verification_sample_includes_verified_columns(self):
        cohort = build_document_cohort(self.tmp / "ocr", self.tmp / "fi")
        results = pd.DataFrame([
            {"row_number": 0, "api_error": "", "status": "ok", "confidence": "high", "note": "",
             **{field: (2.0 if field == "max_storeys" else None) for field in [
                 "max_height_m", "height_context", "max_storeys", "front_setback_m", "rear_setback_m",
                 "side_setback_m", "upper_floor_setback_m", "nearest_dwelling_separation_m",
                 "opposing_window_separation_m", "parking_spaces", "cycle_parking_spaces",
                 "private_open_space_sqm", "communal_open_space_sqm", "vehicular_access_points"]}},
        ])
        merged = merge_campaign_results(cohort, results, model_version="gpt-5")
        sample = build_verification_sample(merged, sample_size=5)
        self.assertIn("verified_max_storeys", sample.columns)
        self.assertIn("verified_by", sample.columns)

    def test_coverage_report_counts_non_null(self):
        merged = pd.DataFrame({
            "doc_max_storeys": [2.0, None, 4.0],
            "doc_max_height_m": [None, None, None],
        })
        report = campaign_coverage_report(merged)
        self.assertEqual(report["max_storeys"]["non_null"], 2)
        self.assertEqual(report["max_height_m"]["non_null"], 0)


if __name__ == "__main__":
    unittest.main()
