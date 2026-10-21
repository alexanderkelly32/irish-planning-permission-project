import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from planning_repository import PlanningRepository
from prediction_service import predict_and_record
from scenario_service import create_scored_scenario


def fake_score(risk=0.2):
    return {
        "status": "scored",
        "model_version": "national_residential_v3_comparables",
        "refusal_score": risk,
        "ranking_score": 0.3,
        "risk_score_0_100": risk * 100,
        "risk_band": "Medium",
    }


class MilestoneWalkthroughTests(unittest.TestCase):
    def test_first_milestone_workflow_persists_baseline_and_scenarios(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = PlanningRepository(Path(directory) / "db.sqlite")
            site = {
                "address": "1 Example Road",
                "planning_authority": "Dublin City Council",
                "itm_easting": 715000,
                "itm_northing": 734500,
            }
            site_id = repo.create_site(site)
            scheme = {
                "proposal_type": "new build",
                "project_description": "Construction of 42 apartments with communal open space.",
                "units": 42,
                "max_storeys": 5,
                "max_height_m": 16.2,
                "upper_floor_setback_m": 0.5,
                "site_area_sqm": 2500,
                "communal_open_space_sqm": 150,
                "parking_spaces": 20,
                "submission_year": 2026,
            }
            baseline_scheme_id = repo.create_scheme(site_id, scheme)
            with patch("prediction_service.score_submission_risk", return_value=fake_score(0.2)):
                baseline_score = predict_and_record(repo, baseline_scheme_id, site, scheme, object())
                result = create_scored_scenario(
                    repo,
                    baseline_scheme_id,
                    "Scenario A",
                    scheme,
                    {"upper_floor_setback_m": 2.5, "communal_open_space_sqm": 400},
                    site,
                    object(),
                )

            self.assertAlmostEqual(baseline_score["grant_probability"], 0.8)
            scenario_row = repo.get_scheme(result["scenario_scheme_id"])
            self.assertEqual(scenario_row["version"], 2)
            self.assertEqual(scenario_row["parent_scheme_id"], baseline_scheme_id)
            scenario_snapshot = json.loads(scenario_row["snapshot_json"])
            self.assertEqual(scenario_snapshot["upper_floor_setback_m"], 2.5)
            self.assertEqual(scenario_snapshot["units"], 42)
            self.assertEqual(result["changed_fields"], ["communal_open_space_sqm", "upper_floor_setback_m"])
            self.assertNotIn("units", result["delta"])
            self.assertEqual(result["support"]["upper_floor_setback_m"], "captured_only")
            baseline_run = repo.get_model_run(baseline_score["model_run_id"])
            self.assertEqual(json.loads(baseline_run["input_snapshot_json"])["units_total_best"], 42)
            scenario_run = repo.get_model_run(result["score"]["model_run_id"])
            self.assertEqual(scenario_run["scenario_id"], result["scenario_id"])
            repo.close()

    def test_scenario_score_changes_only_with_mutated_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = PlanningRepository(Path(directory) / "db.sqlite")
            site = {"address": "A", "planning_authority": "B"}
            site_id = repo.create_site(site)
            scheme = {"proposal_type": "new build", "units": 20, "project_description": "Apartments"}
            baseline_id = repo.create_scheme(site_id, scheme)
            with patch("prediction_service.score_submission_risk", side_effect=[fake_score(0.2), fake_score(0.2), fake_score(0.2)]):
                predict_and_record(repo, baseline_id, site, scheme, object())
                first = create_scored_scenario(repo, baseline_id, "S1", scheme, {"units": 18}, site, object())
                second = create_scored_scenario(repo, baseline_id, "S2", scheme, {"units": 18}, site, object())
            self.assertEqual(first["score"]["grant_probability"], second["score"]["grant_probability"])
            self.assertEqual(first["score"]["model_run_id"] != second["score"]["model_run_id"], True)
            repo.close()

    def test_documents_record_provenance_and_do_not_mutate(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = PlanningRepository(Path(directory) / "db.sqlite")
            document_id = repo.record_document(
                application_id=None,
                document_type="decision_notice",
                source="https://example.test/decision.pdf",
                text="Permission refused for the following reasons.",
                page_range="2-3",
                chunk_index=1,
                extraction_model_version="gpt5-2026-03",
                confidence=0.9,
            )
            row = repo.get_document(document_id)
            self.assertEqual(row["document_type"], "decision_notice")
            self.assertEqual(row["page_range"], "2-3")
            self.assertAlmostEqual(row["confidence"], 0.9)
            again = repo.get_document(document_id)
            self.assertEqual(again["text"], row["text"], "documents are never silently overwritten")
            repo.close()


if __name__ == "__main__":
    unittest.main()
