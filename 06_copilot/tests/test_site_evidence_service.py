import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from site_evidence_service import (
    compare_open_space_ratio,
    current_authority_rules,
    lookup_zoning,
    policy_standards_for_scheme,
    retrieve_policy_passages,
    summarize_site_evidence,
)


def rule_row(plan_key, family, subject, threshold, unit, page="100", review_status="approved"):
    return {
        "plan_key": plan_key,
        "authority": "Example Council",
        "plan_start_year": 2022,
        "plan_end_year": 2028,
        "rule_family": family,
        "subject_type": subject,
        "threshold_kind": "min",
        "threshold_value": threshold,
        "threshold_unit": unit,
        "scope_note": "",
        "source_document_label": "Example Plan 2022-2028",
        "source_page_range": page,
        "source_section_title": "Open Space",
        "source_excerpt": "",
        "verbatim_quote": "At least 10% of the site area shall be provided as open space.",
        "review_status": review_status,
    }


class SiteEvidenceServiceTests(unittest.TestCase):
    def build_layers(self):
        return {
            "dublin_city_council__2022_2028": gpd.GeoDataFrame(
                [
                    {"zone_code": "Zone Z1 - DEV PLAN 2022-2028", "zone_description": "Residential"},
                    {"zone_code": "Zone Z12 - DEV PLAN 2022-2028", "zone_description": "Institutional"},
                ],
                geometry=[box(-6.5, 53.0, -6.0, 53.5), box(-6.0, 53.5, -5.5, 54.0)],
                crs="EPSG:4326",
            ),
        }

    def dcc_site(self, **extra):
        site = {"planning_authority": "Dublin City Council", "latitude": 53.3, "longitude": -6.2}
        site.update(extra)
        return site

    def test_zoning_matches_current_plan_layer_point(self):
        layers = self.build_layers()
        result = lookup_zoning(self.dcc_site(), layers)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["zone_code"], "Zone Z1 - DEV PLAN 2022-2028")
        self.assertEqual(result["plan_period"], "2022-2028")

    def test_zoning_missing_for_uncovered_authority(self):
        result = lookup_zoning({"planning_authority": "Kerry County Council", "latitude": 52.0, "longitude": -9.5}, self.build_layers())
        self.assertEqual(result["status"], "no_verified_coverage")

    def test_zoning_requires_coordinates(self):
        result = lookup_zoning({"planning_authority": "Dublin City Council"}, self.build_layers())
        self.assertEqual(result["status"], "coordinates_missing")

    def test_zoning_uses_itm_coordinates(self):
        layers = self.build_layers()
        site = self.dcc_site(latitude=None, longitude=None, itm_easting=715000, itm_northing=734500)
        result = lookup_zoning(site, layers)
        self.assertIn(result["status"], {"matched", "no_polygon_match"})

    def test_current_authority_rules_keep_current_plan_only(self):
        rules = pd.DataFrame([
            rule_row("dublin_city_council__2016_2022", "parking_min_spaces_per_unit", "1-bed", 1.0, "200"),
            rule_row("dublin_city_council__2022_2028", "open_space_min_site_ratio", "residential_z1_z2_z3_z4_z5_z6_z8_z10_z14", 0.10, "585"),
            rule_row("dublin_city_council__2022_2028", "open_space_min_site_ratio", "residential_z12_z15", 0.25, "585"),
        ])
        current = current_authority_rules(rules, "Dublin City Council")
        self.assertEqual(set(current["plan_key"]), {"dublin_city_council__2022_2028"})
        self.assertEqual(set(current["rule_family"]), {"open_space_min_site_ratio"})

    def test_open_space_ratio_compares_for_covered_zone(self):
        rules = pd.DataFrame([
            rule_row("dublin_city_council__2022_2028", "open_space_min_site_ratio", "residential_z1_z2_z3_z4_z5_z6_z8_z10_z14", 0.10, "585"),
            rule_row("dublin_city_council__2022_2028", "open_space_min_site_ratio", "residential_z12_z15", 0.25, "585"),
        ])
        site = self.dcc_site()
        result = compare_open_space_ratio(site, {"site_area_sqm": 1000, "communal_open_space_sqm": 40, "private_open_space_sqm": 30}, rules, "Zone Z1")
        self.assertEqual(result["status"], "compared")
        self.assertFalse(result["meets_threshold"])
        self.assertAlmostEqual(result["observed_ratio"], 0.07)

    def test_open_space_ratio_respects_zone_specific_threshold(self):
        rules = pd.DataFrame([
            rule_row("dublin_city_council__2022_2028", "open_space_min_site_ratio", "residential_z1_z2_z3_z4_z5_z6_z8_z10_z14", 0.10, "585"),
            rule_row("dublin_city_council__2022_2028", "open_space_min_site_ratio", "residential_z12_z15", 0.25, "585"),
        ])
        result = compare_open_space_ratio(
            self.dcc_site(),
            {"site_area_sqm": 1000, "communal_open_space_sqm": 200, "private_open_space_sqm": 100},
            rules,
            "Zone Z12",
        )
        self.assertTrue(result["meets_threshold"])

    def test_open_space_ratio_requires_fields(self):
        rules = pd.DataFrame([rule_row("dublin_city_council__2022_2028", "open_space_min_site_ratio", "residential_z1_z2_z3_z4_z5_z6_z8_z10_z14", 0.10, "585")])
        result = compare_open_space_ratio(self.dcc_site(), {"site_area_sqm": 1000}, rules, "Zone Z1")
        self.assertEqual(result["status"], "not_comparable_missing_fields")

    def test_apartment_and_amenity_standards_are_shown_without_comparison(self):
        rules = pd.DataFrame([
            rule_row("south_dublin_county_council__2022_2028", "apartment_min_floor_area", "studio", 37.0, "479"),
            rule_row("south_dublin_county_council__2022_2028", "communal_amenity_min_per_unit", "1-bed", 5.0, "480"),
        ])
        policy = policy_standards_for_scheme(
            {"planning_authority": "South Dublin County Council"},
            {"units": 40},
            rules,
        )
        self.assertEqual(policy["status"], "available")
        self.assertEqual(len(policy["apartment_min_floor_area"]["standards"]), 1)
        self.assertEqual(
            policy["communal_amenity_min_per_unit"]["comparison_status"],
            "not_comparable_missing_fields",
        )

    def test_policy_standards_missing_for_uncovered_authority(self):
        policy = policy_standards_for_scheme({"planning_authority": "Kerry County Council"}, {"units": 5}, pd.DataFrame())
        self.assertEqual(policy["status"], "no_verified_rules")

    def test_policy_passages_retrieve_with_citations(self):
        chunks = pd.DataFrame([
            {"authority": "Dublin City Council", "plan_start_year": 2022, "plan_end_year": 2028,
             "document_label": "Dublin City Development Plan 2022-2028", "section_title": "Transition",
             "page_range": "585-586", "chunk_text": "Appropriate transition in height to adjoining properties."},
            {"authority": "Dublin City Council", "plan_start_year": 2022, "plan_end_year": 2028,
             "document_label": "Dublin City Development Plan 2022-2028", "section_title": "Parking",
             "page_range": "700-701", "chunk_text": "Car parking standards."},
            {"authority": "Dublin City Council", "plan_start_year": 2016, "plan_end_year": 2022,
             "document_label": "Old Plan", "section_title": "Transition",
             "page_range": "10-11", "chunk_text": "Old plan transition text."},
        ])
        passages = retrieve_policy_passages(chunks, "Dublin City Council", ["transition"], limit=5)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["section_title"], "Transition")
        self.assertEqual(passages[0]["page_range"], "585-586")

    def test_summary_includes_coverage_gated_flood_note(self):
        layers = self.build_layers()
        summary = summarize_site_evidence(self.dcc_site(), {"site_area_sqm": 1000}, layers)
        self.assertEqual(summary["zoning"]["status"], "matched")
        self.assertEqual(summary["flood"]["status"], "no_site_level_coverage")
        self.assertIn("never assumed", summary["caveat"])


if __name__ == "__main__":
    unittest.main()
