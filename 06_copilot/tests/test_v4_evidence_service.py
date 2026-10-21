import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "06_copilot" / "scripts"))
import v4_evidence_service as evidence  # noqa: E402
from v4_evidence_service import _objective_title, _sentence, _wilson_ci  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HAS_ARTIFACTS = (ROOT / "05_policy" / "current" / "model_v4" / "comparable_metadata.joblib").exists()
HAS_RECENT = (ROOT / "05_policy" / "current" / "model_v4" / "recent_precedents_reference.joblib").exists()

DLR_PROPOSAL = {
    "authority": "Dun Laoghaire Rathdown County Council",
    "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
    "units": 12,
    "site_area_sqm": 4000,
    "floor_area_sqm": 2400,
    "itm_easting": 722000,
    "itm_northing": 726500,
    "submission_year": 2026,
}


class EvidenceServiceTests(unittest.TestCase):
    def test_wilson_ci(self):
        lo, hi = _wilson_ci(0.5, 100)
        self.assertAlmostEqual(lo, 0.4038, places=3)
        self.assertAlmostEqual(hi, 0.5962, places=3)
        self.assertEqual(_wilson_ci(0.5, 0), (0.0, 1.0))

    def test_objective_title_cuts_at_code(self):
        title = _objective_title("PHP19", "=== PAGE 69 === random text before PHP19: Existing Housing Stock - Adaptation, Section 4.3.")
        self.assertTrue(title.startswith("PHP19"))
        self.assertNotIn("PAGE", title)

    def test_sentence_strips_page_markers(self):
        text = _sentence("=== PAGE 12 === It is an objective of the council to protect amenity. Further text.")
        self.assertIn("protect amenity", text)

    @unittest.skipUnless(HAS_ARTIFACTS, "comparable metadata artifact not built")
    def test_comparable_details_real(self):
        proposal = {
            "authority": "Dun Laoghaire Rathdown County Council",
            "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
            "units": 12,
            "site_area_sqm": 4000,
            "floor_area_sqm": 2400,
            "itm_easting": 722000,
            "itm_northing": 726500,
            "submission_year": 2026,
        }
        result = evidence.comparable_details(proposal, k=20)
        self.assertEqual(len(result["comparables"]), 20)
        first = result["comparables"][0]
        for key in ("application_number", "council", "received_date", "outcome", "similarity", "units"):
            self.assertIn(key, first)
        self.assertIn(first["outcome"], {"Refused", "Granted"})
        summary = result["summary"]
        self.assertEqual(summary["refused_count"] + summary["granted_count"], 20)
        self.assertGreaterEqual(summary["mean_similarity"], 0.0)

    @unittest.skipUnless(HAS_ARTIFACTS, "comparable metadata artifact not built")
    def test_plan_objectives_real(self):
        result = evidence.plan_objectives("Dun Laoghaire Rathdown County Council", 2026, "construction of 12 apartments")
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["summary"]["objective_count"], 0)
        self.assertTrue(all(item["status"] in {"addressed", "open", "flag"} for item in result["objectives"]))

    def test_plan_objectives_missing_council(self):
        result = evidence.plan_objectives("Not A Real Council", 2026)
        self.assertEqual(result["status"], "no_plan_on_file")

    @unittest.skipUnless(HAS_ARTIFACTS, "comparable metadata artifact not built")
    def test_plan_objectives_drop_numeric_codes(self):
        result = evidence.plan_objectives("Dun Laoghaire Rathdown County Council", 2026, "construction of 12 apartments")
        codes = [o["code"] for o in result["objectives"]]
        self.assertFalse(any(code.isdigit() for code in codes), f"numeric junk codes remain: {[c for c in codes if c.isdigit()][:5]}")

    @unittest.skipUnless(HAS_RECENT, "recent precedents reference not built")
    def test_matched_precedents_recent_window(self):
        result = evidence.matched_precedents(DLR_PROPOSAL, k=20)
        self.assertEqual(len(result["precedents"]), 20)
        summary = result["summary"]
        self.assertEqual(summary["retrieved"], 20)
        for item in result["precedents"]:
            self.assertIn(item["outcome"], {"Refused", "Granted"})
            self.assertIn("wording_label", item)
            self.assertIn("match_reasons", item)
            self.assertGreaterEqual(int(item["received_date"][:4]), DLR_PROPOSAL["submission_year"] - 5)
            self.assertLessEqual(int(item["received_date"][:4]), DLR_PROPOSAL["submission_year"])
        self.assertEqual(summary["refused_count"] + summary["granted_count"], 20)

    @unittest.skipUnless(HAS_RECENT, "recent precedents reference not built")
    def test_matched_precedents_excludes_undecided_and_future(self):
        proposal = {**DLR_PROPOSAL, "submission_year": 2024}
        result = evidence.matched_precedents(proposal, k=20)
        for item in result["precedents"]:
            self.assertLessEqual(int(item["received_date"][:4]), 2024)

    @unittest.skipUnless(HAS_RECENT, "recent precedents reference not built")
    def test_council_check_mismatch(self):
        check = evidence.council_check(722000, 726500, "Meath County Council")
        self.assertEqual(check["status"], "mismatch")
        self.assertIn("Dun Laoghaire", check["note"])
        ok = evidence.council_check(722000, 726500, "Dun Laoghaire Rathdown County Council")
        self.assertEqual(ok["status"], "ok")

    @unittest.skipUnless(HAS_RECENT, "recent precedents reference not built")
    def test_ge10_position(self):
        position = evidence.ge10_position(0.35, 12)
        self.assertIsNotNone(position)
        self.assertEqual(position["n"], 464)
        self.assertGreaterEqual(position["percentile"], 0)
        self.assertLessEqual(position["percentile"], 100)
        self.assertIn("percentile", position["note"])
        self.assertIsNone(evidence.ge10_position(0.35, 4))

    @unittest.skipUnless((ROOT / "07_context" / "current" / "constraint_niah.parquet").exists(), "constraint tables not built")
    def test_constraints_for_real(self):
        constraints = evidence.constraints_for(722000, 726500)
        for key in ("niah", "natura", "wwtp", "traffic"):
            self.assertIn(key, constraints)
            self.assertIsNotNone(constraints[key], f"{key} lookup empty")
        self.assertIn("distance_m", constraints["niah"])
        self.assertGreaterEqual(constraints["niah"]["distance_m"], 0)
        self.assertIn("sitename", constraints["natura"])
        self.assertIn("type", constraints["natura"])
        self.assertIn("within_2km", constraints["traffic"])

    @unittest.skipUnless((ROOT / "07_context" / "current" / "constraint_niah.parquet").exists(), "constraint tables not built")
    def test_site_context_includes_constraints(self):
        site = evidence.site_context(DLR_PROPOSAL)
        self.assertIsNotNone(site.get("constraints"))
        self.assertIn("niah", site["constraints"])

    def test_boundary_evidence_area_and_density(self):
        proposal = {"authority": "Dun Laoghaire Rathdown County Council", "units": 12, "submission_year": 2026}
        polygon = [[-6.185, 53.288], [-6.183, 53.288], [-6.183, 53.286], [-6.185, 53.286], [-6.185, 53.288]]
        result = evidence.boundary_evidence(proposal, polygon)
        self.assertIsNotNone(result)
        self.assertGreater(result["area_sqm"], 20_000)
        self.assertLess(result["area_sqm"], 50_000)
        self.assertAlmostEqual(result["density_units_per_ha"], 12.0 / result["area_ha"], delta=0.1)
        self.assertIn("niah_count", result["inside"])

    def test_boundary_evidence_rejects_junk(self):
        self.assertIsNone(evidence.boundary_evidence({"units": 12}, []))
        self.assertIsNone(evidence.boundary_evidence({"units": 12}, [[-6.185, 53.288], [-6.183, 53.288]]))


if __name__ == "__main__":
    unittest.main()
