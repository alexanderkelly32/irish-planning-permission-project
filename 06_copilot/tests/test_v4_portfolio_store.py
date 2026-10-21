import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "06_copilot" / "scripts"))
import v4_portfolio_store as portfolio  # noqa: E402


class PortfolioStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self._original = portfolio.DB_PATH
        portfolio.DB_PATH = Path(self.temp.name) / "test_portfolio.sqlite"

    def tearDown(self):
        portfolio.DB_PATH = self._original
        self.temp.cleanup()

    def _proposal(self):
        return {
            "name": "Test scheme",
            "authority": "Meath County Council",
            "description": "construction of 20 houses",
            "units": 20,
            "site_area_sqm": 8000,
            "floor_area_sqm": 4000,
            "itm_easting": 700000,
            "itm_northing": 750000,
            "submission_year": 2026,
        }

    def test_save_and_retrieve_project(self):
        project_id = portfolio.save_project(
            self._proposal(),
            {"model_version": "v4", "refusal_probability": 0.21, "raw_ranking_score": 0.3,
             "risk_band": "medium", "inputs": {"units": 20}},
            {"nearby_1km": {"recent_24m_count": 5, "refusal_rate": 0.2}},
        )
        projects = portfolio.list_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], "Test scheme")
        self.assertEqual(projects[0]["latest_risk"], 0.21)
        loaded = portfolio.get_project(project_id)
        self.assertEqual(loaded["units"], 20)
        run = portfolio.latest_run(project_id)
        self.assertEqual(run["model_version"], "v4")
        self.assertEqual(run["refusal_probability"], 0.21)
        snapshot = portfolio.latest_snapshot(project_id)
        self.assertEqual(json.loads(snapshot["evidence_json"])["nearby_1km"]["refusal_rate"], 0.2)

    def test_update_keeps_history(self):
        project_id = portfolio.save_project(self._proposal(), {"model_version": "v4", "refusal_probability": 0.2}, {})
        portfolio.save_project({**self._proposal(), "units": 30},
                               {"model_version": "v4", "refusal_probability": 0.3}, {}, project_id=project_id)
        projects = portfolio.list_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["latest_risk"], 0.3)

    def test_scenarios_and_events(self):
        project_id = portfolio.save_project(self._proposal(), {"model_version": "v4", "refusal_probability": 0.2}, {})
        portfolio.save_scenario(project_id, "fewer units", {"units": 10}, 0.15, -5.0, "lowers")
        scenarios = portfolio.list_scenarios(project_id)
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0]["delta_pp"], -5.0)
        events_before = portfolio.count_runs()
        portfolio.record_event("v4", "review", self._proposal(), 0.2, {"band": "high"})
        self.assertEqual(portfolio.count_runs(), events_before + 1)

    def test_delete_cascades(self):
        project_id = portfolio.save_project(self._proposal(), {"model_version": "v4", "refusal_probability": 0.2}, {})
        portfolio.delete_project(project_id)
        self.assertEqual(portfolio.list_projects(), [])
        self.assertIsNone(portfolio.latest_run(project_id))

    def test_override_audit_trail(self):
        project_id = portfolio.save_project(self._proposal(), {"model_version": "v4", "refusal_probability": 0.2}, {})
        portfolio.save_override(project_id, None, "Risk band", "HIGH", "MEDIUM",
                                "Density precedent set mostly granted; manual review disagrees.", "Jane Planner")
        overrides = portfolio.list_overrides(project_id)
        self.assertEqual(len(overrides), 1)
        self.assertEqual(overrides[0]["original_value"], "HIGH")
        self.assertEqual(overrides[0]["override_value"], "MEDIUM")
        self.assertEqual(overrides[0]["planner_name"], "Jane Planner")
        portfolio.save_override(project_id, None, "Refusal probability", "53%", "40%", "Second look.", "Jane Planner")
        self.assertEqual(len(portfolio.list_overrides(project_id)), 2)
        portfolio.delete_override(overrides[0]["id"])
        self.assertEqual(len(portfolio.list_overrides(project_id)), 1)


if __name__ == "__main__":
    unittest.main()
