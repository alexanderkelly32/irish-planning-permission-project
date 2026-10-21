import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from planning_repository import PlanningRepository
from prediction_service import build_model_query, predict_and_record


class PredictionServiceTests(unittest.TestCase):
    def test_query_adapter_allowlists_submission_inputs(self):
        query = build_model_query(
            {"planning_authority": "Dublin City Council", "latitude": 53.3, "longitude": -6.2},
            {"proposal_type": "new build", "units": 42, "site_area_sqm": 10000, "project_description": "Apartments", "decision": "REFUSED"},
        )
        self.assertEqual(query["PlanningAuthority"], "Dublin City Council")
        self.assertEqual(query["units_total_best"], 42)
        self.assertNotIn("decision", query)
        self.assertEqual(query["site_area_ha_best"], 1.0)

    def test_prediction_records_grant_complement(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = PlanningRepository(Path(directory) / "db.sqlite")
            site_id = repo.create_site({"address": "A", "planning_authority": "B"})
            scheme_id = repo.create_scheme(site_id, {"proposal_type": "new build", "units": 42, "project_description": "Apartments"})
            fake_score = {"status": "scored", "model_version": "v3", "refusal_score": 0.2, "risk_score_0_100": 20.0, "risk_band": "Medium"}
            with patch("prediction_service.score_submission_risk", return_value=fake_score):
                result = predict_and_record(repo, scheme_id, {"planning_authority": "B"}, {"units": 42}, object())
            self.assertAlmostEqual(result["grant_probability"], 0.8)
            run = repo.get_model_run(result["model_run_id"])
            self.assertNotIn("decision", json.loads(run["input_snapshot_json"]))
            repo.close()


if __name__ == "__main__":
    unittest.main()
