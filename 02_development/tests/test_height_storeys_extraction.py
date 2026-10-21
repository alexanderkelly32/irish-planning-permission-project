import json
import unittest

import pandas as pd

from height_storeys_extraction import (
    apply_plausibility,
    apply_verification,
    build_verification_sample,
    flatten_batch_output,
    merge_results,
    row_number_from_custom_id,
    select_rows,
)


class HeightStoreysExtractionTests(unittest.TestCase):
    def build_ground(self):
        return pd.DataFrame([
            {"case_key": "a", "PlanningAuthority": "C", "ApplicationNumber": "1", "DevelopmentDescription": "Six storey apartment building, 18m high."},
            {"case_key": "b", "PlanningAuthority": "C", "ApplicationNumber": "2", "DevelopmentDescription": "Two storey dwelling."},
            {"case_key": "c", "PlanningAuthority": "C", "ApplicationNumber": "3", "DevelopmentDescription": "New driveway and boundary treatment."},
        ])

    def test_selects_rows_with_storey_or_height_keywords_only(self):
        selected = select_rows(self.build_ground())
        self.assertEqual(set(selected["case_key"]), {"a", "b"})

    def test_custom_id_round_trip(self):
        self.assertEqual(row_number_from_custom_id("structured-extract-row-42"), 42)
        self.assertIsNone(row_number_from_custom_id("other-id"))

    def test_flatten_batch_output_handles_errors_and_payloads(self):
        jsonl = "\n".join([
            json.dumps({
                "custom_id": "structured-extract-row-0",
                "response": {"body": {"choices": [{"message": {"content": json.dumps({
                    "status": "ok", "max_height_m": 18.0, "height_context": "overall",
                    "max_storeys": 6, "upper_floor_setback_m": None, "confidence": "high", "note": "explicit",
                })}}]}},
            }),
            json.dumps({"custom_id": "structured-extract-row-1", "error": {"message": "rate limit"}}),
        ])
        flattened = flatten_batch_output(jsonl)
        self.assertEqual(len(flattened), 2)
        self.assertEqual(flattened.loc[0, "max_height_m"], 18.0)
        self.assertEqual(flattened.loc[0, "max_storeys"], 6)
        self.assertEqual(flattened.loc[1, "row_number"], 1)
        self.assertIn("rate limit", flattened.loc[1, "api_error"])

    def test_plausibility_drops_implausible_values(self):
        row = pd.Series({"max_height_m": 900.0, "max_storeys": 5.0, "upper_floor_setback_m": None, "confidence": "high", "note": ""})
        cleaned = apply_plausibility(row)
        self.assertIsNone(cleaned["max_height_m"])
        self.assertEqual(cleaned["max_storeys"], 5.0)
        self.assertEqual(cleaned["confidence"], "low")

    def test_merge_results_adds_provenance_columns(self):
        ground = self.build_ground()
        results = pd.DataFrame([
            {"row_number": 0, "status": "ok", "max_height_m": 18.0, "height_context": "overall", "max_storeys": 6.0, "upper_floor_setback_m": None, "confidence": "high", "note": "explicit", "api_error": ""},
            {"row_number": 1, "status": "ok", "max_height_m": None, "height_context": None, "max_storeys": 2.0, "upper_floor_setback_m": None, "confidence": "medium", "note": "", "api_error": ""},
        ])
        merged = merge_results(ground, results, model_version="gpt-5")
        self.assertEqual(merged.loc[0, "llm_max_height_m"], 18.0)
        self.assertEqual(merged.loc[0, "llm_extraction_model"], "gpt-5")
        self.assertEqual(merged.loc[1, "llm_max_storeys"], 2.0)
        self.assertEqual(merged.loc[2, "llm_extraction_status"], "")

    def test_verification_sample_balances_values_and_nulls(self):
        merged = pd.DataFrame([
            {"case_key": f"c{i}", "PlanningAuthority": "C", "ApplicationNumber": str(i),
             "DevelopmentDescription": "x", "llm_extraction_status": "ok",
             "llm_max_height_m": 10.0 + i, "llm_height_context": "overall",
             "llm_max_storeys": 3.0, "llm_upper_floor_setback_m": None,
             "llm_confidence": "high", "llm_note": ""}
            for i in range(30)
        ] + [
            {"case_key": f"n{i}", "PlanningAuthority": "C", "ApplicationNumber": str(100 + i),
             "DevelopmentDescription": "x", "llm_extraction_status": "ok",
             "llm_max_height_m": None, "llm_height_context": None,
             "llm_max_storeys": None, "llm_upper_floor_setback_m": None,
             "llm_confidence": "low", "llm_note": ""}
            for i in range(30)
        ])
        sample = build_verification_sample(merged, sample_size=20, seed=7)
        self.assertEqual(len(sample), 20)
        has_value = sample["llm_max_height_m"].notna() | sample["llm_max_storeys"].notna()
        self.assertEqual(int(has_value.sum()), 12)
        self.assertIn("verified_by", sample.columns)
        self.assertTrue(sample["verified_by"].isna().all() or (sample["verified_by"] == "").all())

    def test_apply_verification_overlays_and_measures_errors(self):
        merged = pd.DataFrame([
            {"case_key": "k1", "llm_max_storeys": 5.0, "llm_max_height_m": 15.0, "max_storeys_best": 5.0, "llm_extraction_status": "ok"},
            {"case_key": "k2", "llm_max_storeys": 2.0, "llm_max_height_m": None, "max_storeys_best": 2.0, "llm_extraction_status": "ok"},
            {"case_key": "k3", "llm_max_storeys": None, "llm_max_height_m": None, "max_storeys_best": 3.0, "llm_extraction_status": ""},
        ])
        verification = pd.DataFrame([
            {"case_key": "k1", "verified_storeys": 4.0, "verified_height_m": 15.0, "verified_upper_floor_setback_m": None},
            {"case_key": "k2", "verified_storeys": None, "verified_height_m": None, "verified_upper_floor_setback_m": None},
            {"case_key": "k3", "verified_storeys": 3.0, "verified_height_m": None, "verified_upper_floor_setback_m": None},
        ])
        frame, metrics = apply_verification(merged, verification)
        self.assertEqual(frame.loc[0, "storeys_final"], 4.0)
        self.assertEqual(frame.loc[0, "storeys_provenance"], "verified")
        self.assertEqual(frame.loc[1, "storeys_final"], 2.0)
        self.assertEqual(frame.loc[2, "storeys_final"], 3.0)
        self.assertEqual(metrics["storeys_exact_agreement"], 0)
        self.assertEqual(metrics["storeys_false_negatives"], 1)
        self.assertAlmostEqual(metrics["storeys_recall_estimate"], 0.0)


if __name__ == "__main__":
    unittest.main()
