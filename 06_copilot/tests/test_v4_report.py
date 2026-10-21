import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "06_copilot" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))
from v4_report import ReviewReport  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def _fake_inputs() -> dict:
    return {
        "scheme_label": "Test scheme",
        "proposal": {
            "name": "Test scheme",
            "authority": "Meath County Council",
            "description": "construction of 20 houses with landscaping and bicycle parking",
            "units": 20,
            "site_area_sqm": 8000,
            "floor_area_sqm": 4000,
            "itm_easting": 700000,
            "itm_northing": 750000,
            "submission_year": 2026,
        },
        "score": {"model_version": "v4", "refusal_probability": 0.35, "grant_probability": 0.65, "risk_band": "high"},
        "digest": {
            "summary": "Together these factors give an estimated 35% chance of refusal.",
            "factors": [{"text": "This is a '10+ units' application; across Ireland these are refused 19% of the time."}],
        },
        "confidence": {"confidence_notes": ["Precedents: 20 matched past applications (3 in Meath County Council, median year 2023) - 5 refused and 15 granted."], "fallbacks": ["Floor area: not provided."], "specialised": None},
        "calibration": {"band": "30-40%", "n": 1027, "observed_rate": 0.355, "ci_lo": 0.327, "ci_hi": 0.385},
        "precedents": {
            "summary": {"bucket": "10+ units", "window": "2021-2026", "pool": 1077, "pool_same_council": 12,
                        "retrieved": 20, "refusal_rate": 0.25, "refused_count": 5, "granted_count": 15,
                        "same_council_count": 3, "mean_wording_match": 0.1, "median_year": 2023,
                        "units_range": (10.0, 16.0)},
            "precedents": [
                {"application_number": "20221165", "council": "Wexford County Council", "received_date": "2022-09-01",
                 "decision_date": "2023-03-24", "units": 12, "outcome": "Granted", "wording_match": 0.39,
                 "wording_label": "Close", "match_reasons": ["close wording"], "description": "x",
                 "rationale": None, "rationale_label": None, "rationale_tag": None},
                {"application_number": "20161244", "council": "Wexford County Council", "received_date": "2016-11-09",
                 "decision_date": "2017-01-06", "units": 12, "outcome": "Refused", "wording_match": 0.23,
                 "wording_label": "Partial", "match_reasons": ["similar unit count"], "description": "x",
                 "rationale": "The density of development would be well in excess of the existing development in the area.",
                 "rationale_label": "Density / scale out of character", "rationale_tag": "density_scale"},
            ],
        },
        "objectives": {
            "status": "ok",
            "summary": {"council": "Meath County Council", "plan_period": "2021-2027", "plan_document": "Meath County Development Plan",
                        "objective_count": 12, "mention_count": 40, "addressed": 3, "open": 9, "flagged": 0, "fallback_used": False,
                        "dropped_junk_codes": 0},
            "objectives": [
                {"code": "OB1", "title": "Support sustainable housing delivery.", "theme": "housing", "theme_label": "Housing & supply",
                 "mentions": 5, "status": "addressed"},
                {"code": "OB2", "title": "Protect residential amenity.", "theme": "design", "theme_label": "Design & quality",
                 "mentions": 2, "status": "open"},
            ],
        },
        "site": {
            "coordinates": {"itm_easting": 700000, "itm_northing": 750000},
            "flood": {"flood_any": False, "nearest_fluvial_m": 1200.0, "nearest_coastal_m": 5000.0,
                      "fluvial_depth_max_m": 0.0, "coastal_depth_max_m": 0.0},
            "small_area": {"pop_density_per_sqkm": 800.0, "is_urban": True, "urban_area_name": "Navan",
                           "owner_share": 70.0, "private_rent_share": 10.0, "septic_share": 1.0, "cars_per_hh": 1.5},
            "nearby_rates": {"within_1km": {"recent_24m_count": 12, "recent_24m_refusal_rate": 0.08, "all_time_count": 100},
                             "within_3km": {"recent_24m_count": 60, "recent_24m_refusal_rate": 0.1, "all_time_count": 500}},
            "nearby": {"points": [], "cap_note": ""},
            "zoning": {"status": "no_verified_coverage", "note": "No plan-versioned zoning layer is currently verified for this authority."},
        },
        "brief": None,
        "override": None,
    }


class ReportTests(unittest.TestCase):
    def test_build_pdf_bytes(self):
        pdf_bytes = ReviewReport().build(**_fake_inputs())
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 3000)
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(pdf_bytes))
        self.assertGreaterEqual(len(reader.pages), 2)
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("Pre-Submission Planning Risk Review", text)
        self.assertIn("35%", text)
        self.assertIn("20221165", text)
        self.assertIn("Density / scale out of character", text)
        self.assertIn("The closest past applications", text)
        self.assertNotIn("ROC-AUC", text)

    def test_brief_and_override_sections(self):
        inputs = _fake_inputs()
        inputs["brief"] = {
            "register": [{
                "category": "constraints", "issue": "Wastewater capacity",
                "evidence": "No servicing-capacity data is ingested by the model.",
                "severity": "unverified", "confidence": "unknown",
                "mitigation": "Confirm capacity with Irish Water.",
                "owner": "Engineer (Irish Water / drainage)", "status": "open",
                "source": "no data ingested - external confirmation required",
            }],
            "next_actions": [{"owner": "Engineer (Irish Water / drainage)", "severity": "unverified",
                              "issue": "Wastewater capacity", "action": "Confirm capacity with Irish Water."}],
            "evidence_quality": [{"input": "National register", "stamp": "Decisions through 2025-12-23.",
                                  "status": "frozen_snapshot"}],
            "strengths": [],
        }
        inputs["override"] = {"target": "Risk band", "original_value": "HIGH", "override_value": "MEDIUM",
                              "rationale": "Manual review disagrees.", "planner_name": "Jane Planner",
                              "created_at": "2026-09-23T19:00:00+00:00"}
        pdf_bytes = ReviewReport().build(**inputs)
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("Risk register and unknowns", text)
        self.assertIn("UNVERIFIED", text)
        self.assertIn("Planner note (override)", text)
        self.assertIn("Jane Planner", text)
        self.assertNotIn("Model changelog", text)

    def test_latin_normalisation(self):
        from v4_report import _latin

        self.assertEqual(_latin("it\u2019s a 12 m\u00b2 scheme"), "it's a 12 m2 scheme")


if __name__ == "__main__":
    unittest.main()
