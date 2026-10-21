import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "06_copilot" / "scripts"))
import v4_brief_service as brief  # noqa: E402
from v4_brief_service import build_risk_register, load_model_changelog, transit_stops_near  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HAS_DATA = (ROOT / "03_refusal" / "current" / "refusal_reason_tag_counts_master.csv").exists()
HAS_RECENT = (ROOT / "05_policy" / "current" / "model_v4" / "recent_precedents_reference.joblib").exists()


def _minimal_review() -> dict:
    return {
        "proposal": {
            "authority": "Meath County Council",
            "description": "construction of 20 houses",
            "units": 20,
            "site_area_sqm": 8000,
            "floor_area_sqm": 4000,
            "itm_easting": 700000,
            "itm_northing": 750000,
            "submission_year": 2026,
        },
        "score": {"refusal_probability": 0.25, "risk_band": "medium", "grant_probability": 0.75},
        "digest": {"summary": "summary", "factors": []},
        "confidence": {"fallbacks": ["Location: council-centre coordinates were used (not the exact site)."],
                       "confidence_notes": [], "specialised": None},
        "calibration": {"band": "20-30%", "n": 900, "observed_rate": 0.25, "ci_lo": 0.2, "ci_hi": 0.3},
        "comparables": {
            "summary": {"bucket": "10+ units", "available_in_bucket": 2035, "retrieved": 20,
                        "refusal_rate": 0.45, "refused_count": 9, "granted_count": 11,
                        "mean_similarity": 0.2, "max_refused_similarity": 0.3, "max_granted_similarity": 0.25},
            "comparables": [
                {"application_number": "1", "council": "Meath County Council", "received_date": "2022-01-01",
                 "decision_date": "2022-06-01", "units": 20, "outcome": "Refused", "similarity": 0.3,
                 "rationale": "density grounds", "rationale_label": "Density / scale", "rationale_tag": "density_scale"},
            ],
        },
        "objectives": {"status": "ok", "summary": {"council": "Meath County Council", "plan_period": "2021-2027",
                       "plan_document": "Meath CDP", "objective_count": 40, "mention_count": 100,
                       "addressed": 5, "open": 35, "flagged": 0, "fallback_used": False},
                       "objectives": []},
        "site": {
            "coordinates": {"itm_easting": 700000, "itm_northing": 750000},
            "flood": {"flood_any": False, "nearest_fluvial_m": 2000.0, "nearest_coastal_m": 9000.0,
                      "fluvial_depth_max_m": 0.0, "coastal_depth_max_m": 0.0, "fluvial_hit_any": False,
                      "coastal_hit_any": False, "nearest_reference_point_m": 50.0},
            "small_area": None,
            "nearby_rates": {"within_1km": {"recent_24m_count": 5, "recent_24m_refusal_rate": 0.2, "all_time_count": 50},
                             "within_3km": {"recent_24m_count": 30, "recent_24m_refusal_rate": 0.15, "all_time_count": 200}},
            "nearby": {"points": [], "cap_note": ""},
            "zoning": {"status": "no_verified_coverage", "note": "no layer"},
        },
        "highlights": {"raising": [{"term": "housing development", "coefficient": 1.2, "pp_change": 6.0, "doc_frequency": 169}],
                       "lowering": []},
    }


class BriefServiceTests(unittest.TestCase):
    @unittest.skipUnless(HAS_RECENT, "recent precedents reference not built")
    def test_register_rows_have_valid_vocab(self):
        payload = build_risk_register(_minimal_review())
        self.assertGreaterEqual(len(payload["register"]), 8)
        for row in payload["register"]:
            self.assertIn(row["severity"], {"low", "medium", "high", "unverified"})
            self.assertIn(row["confidence"], {"high", "medium", "low", "unknown"})
            for key in ("issue", "evidence", "mitigation", "owner", "status", "source", "category"):
                self.assertTrue(row[key], f"{key} empty for {row['issue']}")

    @unittest.skipUnless(HAS_RECENT, "recent precedents reference not built")
    def test_constraint_severities_never_fabricated(self):
        payload = build_risk_register(_minimal_review())
        constraints = [r for r in payload["register"] if r["category"] == "constraints"]
        self.assertGreaterEqual(len(constraints), 4)
        for row in constraints:
            if row["severity"] != "unverified":
                self.assertRegex(row["evidence"], r"\d+ (m|km)", f"data-backed row without a distance: {row['issue']}")
            if row["confidence"] == "unknown":
                self.assertEqual(row["severity"], "unverified")

    @unittest.skipUnless(HAS_RECENT, "recent precedents reference not built")
    def test_next_actions_exclude_no_action_required(self):
        payload = build_risk_register(_minimal_review())
        for action in payload["next_actions"]:
            self.assertFalse(action["action"].startswith("No action required"))
        self.assertIn("owner", payload["next_actions"][0])

    @unittest.skipUnless(HAS_RECENT, "recent precedents reference not built")
    def test_evidence_quality_stamps(self):
        payload = build_risk_register(_minimal_review())
        stamps = payload["evidence_quality"]
        self.assertGreaterEqual(len(stamps), 8)
        inputs = {s["input"] for s in stamps}
        self.assertIn("National register", inputs)
        self.assertIn("Matched precedents", inputs)
        for stamp in stamps:
            self.assertIn(stamp["status"], {"ok", "thin", "partial", "approximate", "unverified", "fallback", "frozen_snapshot"})

    @unittest.skipUnless(HAS_DATA, "refusal tag counts not on file")
    def test_transit_lookup_dublin(self):
        stops = transit_stops_near(722000, 726500, radius=800)
        self.assertGreater(len(stops), 0)
        self.assertIn("stop_name", stops[0])
        self.assertLessEqual(stops[0]["distance_m"], 800)

    def test_changelog_loaded(self):
        entries = load_model_changelog()
        self.assertGreater(len(entries), 0)
        self.assertIn("date", entries[0])
        self.assertIn("summary", entries[0])

    @unittest.skipUnless(HAS_RECENT, "recent precedents reference not built")
    def test_specialised_row_appears_when_detected(self):
        review = _minimal_review()
        review["confidence"]["specialised"] = {"observed_rate_pre2024": 0.267, "n": 105,
                                               "general_score": 0.18, "specialised_prior_adjusted": 0.25}
        payload = build_risk_register(review)
        self.assertTrue(any(r["category"] == "scheme_type" for r in payload["register"]))


if __name__ == "__main__":
    unittest.main()
