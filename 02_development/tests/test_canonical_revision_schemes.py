import json
import unittest

import pandas as pd

from canonical_revision_schemes import (
    build_canonical_records,
    build_delta_rows,
    build_pair_deltas,
    load_accepted_pairs,
    normalize_key,
    scheme_id,
    summarize_records,
)


def pair_row(original, revised, tier="high", gap=200):
    return {
        "original_case_key": original,
        "revised_case_key": revised,
        "planning_authority": "Example Council",
        "manual_review_status": "accepted",
        "original_received_date": "2020-01-01",
        "revised_received_date": "2020-07-01",
        "gap_days": gap,
        "linkage_tier": tier,
        "original_source_url": f"https://example.test/{original}",
        "revised_source_url": f"https://example.test/{revised}",
    }


class CanonicalRevisionSchemesTests(unittest.TestCase):
    def build_structured(self):
        return pd.DataFrame([
            {"case_key": "example_council_100", "units_total_best": 40, "max_storeys_best": 5, "floor_area_sqm_best": 4000, "parking_spaces_best": 20},
            {"case_key": "example_council_101", "units_total_best": 36, "max_storeys_best": 5, "floor_area_sqm_best": 3600, "parking_spaces_best": 22},
            {"case_key": "example_council_200", "units_total_best": 30},
            {"case_key": "example_council_201", "units_total_best": None},
        ])

    def test_key_normalization_matches_queue_and_structured_formats(self):
        self.assertEqual(normalize_key("example_council__100"), normalize_key("example_council_100"))
        self.assertEqual(scheme_id("example_council__100"), scheme_id("example_council_100"))

    def test_load_accepted_pairs_filters_and_requires_columns(self):
        queue = pd.DataFrame([pair_row("a", "ar"), pair_row("b", "br"), {**pair_row("c", "cr"), "manual_review_status": "rejected"}])
        accepted = load_accepted_pairs(queue)
        self.assertEqual(len(accepted), 2)
        with self.assertRaises(ValueError):
            load_accepted_pairs(pd.DataFrame([{"case_key": "x"}]))

    def test_pair_deltas_only_when_both_sides_observed(self):
        deltas = build_pair_deltas(
            {"units_total_best": 40, "max_storeys_best": None, "floor_area_sqm_best": 4000},
            {"units_total_best": 36, "max_storeys_best": 5, "floor_area_sqm_best": None},
        )
        self.assertEqual(set(deltas), {"units_total_best"})
        self.assertEqual(deltas["units_total_best"], {"from": 40, "to": 36, "delta": -4})

    def test_builds_records_with_annotation_and_refusal_joins(self):
        queue = pd.DataFrame([
            pair_row("example_council__100", "example_council__101"),
            pair_row("example_council__200", "example_council__201", tier="medium"),
        ])
        annotations = pd.DataFrame([{
            "original_case_key": "example_council__100",
            "revised_case_key": "example_council__101",
            "extracted_refusal_reason": "Height and scale excessive.",
            "addressed_refusal_theme": "density_scale",
            "annotation_confidence": "high",
            "source_backed_change_note": "Units reduced from 40 to 36.",
            "observed_units_delta": -4,
        }])
        refusal_master = pd.DataFrame([{
            "case_key": "example_council_100",
            "case_primary_tags": "density_scale;design_layout",
            "case_top_primary_tag": "density_scale",
        }])
        accepted = load_accepted_pairs(queue)

        records = build_canonical_records(accepted, self.build_structured(), refusal_master, annotations)

        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first["confidence_change_extraction"], "annotation_verified")
        self.assertEqual(first["refusal_themes_original"], "density_scale;design_layout")
        structured = json.loads(first["feature_delta_json"])
        self.assertEqual(structured["units_total_best"], {"from": 40, "to": 36, "delta": -4})
        self.assertEqual(structured["floor_area_sqm_best"], {"from": 4000, "to": 3600, "delta": -400})
        self.assertIn("parking_spaces_best", structured)
        second = records[1]
        self.assertEqual(second["confidence_change_extraction"], "description_only")
        self.assertEqual(json.loads(second["feature_delta_json"]), {})

    def test_delta_rows_include_structured_and_annotation_sources(self):
        queue = pd.DataFrame([pair_row("example_council__100", "example_council__101")])
        annotations = pd.DataFrame([{
            "original_case_key": "example_council__100",
            "revised_case_key": "example_council__101",
            "extracted_refusal_reason": "x",
            "annotation_confidence": "high",
            "observed_units_delta": -4,
        }])
        records = build_canonical_records(load_accepted_pairs(queue), self.build_structured(), None, annotations)
        deltas = build_delta_rows(records)
        self.assertEqual(set(deltas["source"]), {"structured", "annotation_registry"})
        annotation_row = deltas[deltas["source"] == "annotation_registry"].iloc[0]
        self.assertEqual(annotation_row["delta"], -4)

    def test_summary_counts_never_fabricate(self):
        queue = pd.DataFrame([pair_row("example_council__100", "example_council__101")])
        records = build_canonical_records(load_accepted_pairs(queue), self.build_structured(), None, None)
        summary = summarize_records(records)
        self.assertEqual(summary["pair_count"], 1)
        self.assertEqual(summary["with_structured_deltas"], 1)
        self.assertIn("never zero-filled", summary["caveat"])

    def test_empty_inputs_yield_empty_records(self):
        records = build_canonical_records(pd.DataFrame(), pd.DataFrame(), None, None)
        self.assertEqual(records, [])
        self.assertEqual(summarize_records(records), {"pair_count": 0})


if __name__ == "__main__":
    unittest.main()
