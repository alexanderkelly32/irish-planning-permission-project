import json
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path

from planning_repository import PlanningRepository


class PlanningRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = PlanningRepository(Path(self.temp_dir.name) / "planning.sqlite")

    def tearDown(self):
        self.repo.close()
        self.temp_dir.cleanup()

    def test_migration_creates_all_domain_tables(self):
        tables = self.repo.table_names()
        self.assertEqual(
            tables,
            {"sites", "applications", "schemes", "documents", "scenarios", "model_runs"},
        )

    def test_site_scheme_scenario_and_model_run_round_trip(self):
        site_id = self.repo.create_site({"address": "12 Main Street", "planning_authority": "Dublin City Council"})
        scheme_id = self.repo.create_scheme(site_id, {"units": 42, "max_height_m": 16.2}, version=1)
        scenario_id = self.repo.create_scenario(
            scheme_id,
            scheme_id,
            "Setback option",
            {"upper_floor_setback_m": {"from": 0.5, "to": 2.5}},
            {"units": 42, "max_height_m": 16.2, "upper_floor_setback_m": 2.5},
        )
        run_id = self.repo.record_model_run(
            scheme_id=scheme_id,
            scenario_id=scenario_id,
            model_version="national_residential_v3_comparables",
            input_snapshot={"units": 42},
            output={"refusal_probability": 0.2, "grant_probability": 0.8},
        )
        run = self.repo.get_model_run(run_id)
        self.assertEqual(json.loads(run["input_snapshot_json"])["units"], 42)
        self.assertEqual(json.loads(run["output_json"])["grant_probability"], 0.8)
        self.assertEqual(self.repo.get_scheme(scheme_id)["site_id"], site_id)

    def test_scenario_records_its_own_scheme_version(self):
        site_id = self.repo.create_site({"address": "A", "planning_authority": "B"})
        baseline_id = self.repo.create_scheme(site_id, {"units": 42})
        scenario_scheme_id = self.repo.create_scheme(site_id, {"units": 40}, version=2, parent_scheme_id=baseline_id)
        scenario_id = self.repo.create_scenario(baseline_id, scenario_scheme_id, "Reduced units", {"units": {"from": 42, "to": 40}}, {"units": 40})
        row = self.repo.connection.execute("SELECT scenario_scheme_id FROM scenarios WHERE scenario_id=?", (scenario_id,)).fetchone()
        self.assertEqual(row["scenario_scheme_id"], scenario_scheme_id)

    def test_model_runs_are_append_only(self):
        site_id = self.repo.create_site({"address": "A", "planning_authority": "B"})
        scheme_id = self.repo.create_scheme(site_id, {"units": 1})
        run_id = self.repo.record_model_run(scheme_id, None, "v3", {}, {})
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.connection.execute("UPDATE model_runs SET model_version='changed' WHERE model_run_id=?", (run_id,))

    def test_repository_survives_streamlit_style_thread_change(self):
        with ThreadPoolExecutor(max_workers=1) as executor:
            site_id = executor.submit(
                self.repo.create_site,
                {"address": "Threaded site", "planning_authority": "Example Council"},
            ).result()

        self.assertEqual(self.repo.get_scheme("missing"), None)
        self.assertTrue(site_id.startswith("site_"))


if __name__ == "__main__":
    unittest.main()
