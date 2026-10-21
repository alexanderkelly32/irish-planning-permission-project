import json
import math
import unittest
from datetime import datetime, timezone

import pandas as pd

from prospective_shadow_ledger import (
    append_ledger,
    build_case_key,
    build_ledger_rows,
    ledger_summary,
    outcome_readout,
    snapshot_json,
)
from validate_v3_rolling_windows import block_summary, metric_block, window_summaries


def fake_scorer(query):
    if not query.get("PlanningAuthority"):
        return {"status": "skipped"}
    return {
        "status": "scored",
        "model_version": "national_residential_v3_comparables",
        "refusal_score": 0.2,
        "ranking_score": 0.3,
        "risk_band": "Medium",
    }


class ShadowLedgerTests(unittest.TestCase):
    def build_cases(self):
        return pd.DataFrame([
            {
                "PlanningAuthority": "Example Council",
                "ApplicationNumber": "A/1",
                "DevelopmentDescription": "40 apartments",
                "ApplicationType": "Permission",
                "ReceivedDate": "2026-01-15",
                "ITMEasting": 700000,
                "ITMNorthing": 730000,
                "NumResidentialUnits": 40,
                "OneOffHouse": "",
            },
            {
                "PlanningAuthority": "Example Council",
                "ApplicationNumber": "A/2",
                "DevelopmentDescription": "extension",
                "ApplicationType": "Permission",
                "ReceivedDate": "2026-01-20",
                "ITMEasting": None,
                "ITMNorthing": None,
                "NumResidentialUnits": 0,
                "OneOffHouse": "",
            },
            {
                "PlanningAuthority": "",
                "ApplicationNumber": "A/3",
                "DevelopmentDescription": "house",
                "ApplicationType": "Permission",
                "ReceivedDate": "2026-01-25",
                "NumResidentialUnits": 1,
                "OneOffHouse": "y",
            },
        ])

    def test_builds_ledger_rows_with_sanitized_snapshots_and_skips_unscoreable(self):
        rows = build_ledger_rows(self.build_cases(), fake_scorer, datetime(2026, 9, 4, tzinfo=timezone.utc))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows.iloc[0]["case_key"], "example_council__a_1")
        self.assertEqual(rows.iloc[0]["predicted_risk_band"], "Medium")
        snapshot = json.loads(rows.iloc[0]["input_snapshot"])
        self.assertIn("PlanningAuthority", snapshot)
        self.assertEqual(snapshot["ITMEasting"], 700000)
        self.assertEqual(snapshot["received_year"], 2026.0)

    def test_snapshot_json_sanitizes_non_finite_values(self):
        query = {"x": float("nan"), "y": float("inf"), "z": 1.5}
        snapshot = json.loads(snapshot_json(query))
        self.assertIsNone(snapshot["x"])
        self.assertIsNone(snapshot["y"])
        self.assertEqual(snapshot["z"], 1.5)

    def test_append_ledger_never_duplicates_or_overwrites(self):
        existing = pd.DataFrame([
            {
                "case_key": "a", "PlanningAuthority": "C", "ApplicationNumber": "1",
                "received_date": "2026-01-01", "registered_at": "first", "model_version": "v3",
                "predicted_refusal_risk": 0.1, "predicted_risk_band": "Low", "ranking_score": 0.2,
                "input_snapshot": "{}", "outcome_decision": "", "outcome_refused": "",
                "outcome_date": "", "outcome_source_note": "",
            },
        ])
        new_rows = pd.DataFrame([
            {
                "case_key": "a", "PlanningAuthority": "C", "ApplicationNumber": "1",
                "received_date": "2026-01-01", "registered_at": "second", "model_version": "v3",
                "predicted_refusal_risk": 0.9, "predicted_risk_band": "High", "ranking_score": 0.9,
                "input_snapshot": "{}", "outcome_decision": "", "outcome_refused": "",
                "outcome_date": "", "outcome_source_note": "",
            },
            {
                "case_key": "b", "PlanningAuthority": "C", "ApplicationNumber": "2",
                "received_date": "2026-01-02", "registered_at": "second", "model_version": "v3",
                "predicted_refusal_risk": 0.2, "predicted_risk_band": "Low", "ranking_score": 0.3,
                "input_snapshot": "{}", "outcome_decision": "", "outcome_refused": "",
                "outcome_date": "", "outcome_source_note": "",
            },
        ])

        merged = append_ledger(existing, new_rows)

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged.loc[merged["case_key"] == "a", "registered_at"].iloc[0], "first")
        self.assertEqual(merged.loc[merged["case_key"] == "a", "predicted_refusal_risk"].iloc[0], 0.1)

    def test_ledger_summary_counts_and_caveat(self):
        ledger = build_ledger_rows(self.build_cases(), fake_scorer, datetime(2026, 9, 4, tzinfo=timezone.utc))
        summary = ledger_summary(ledger, model_sha256="abc")
        self.assertEqual(summary["ledger_row_count"], 2)
        self.assertIn("must not be used to tune", summary["caveat"])

    def test_outcome_readout_stays_silent_until_outcomes_arrive(self):
        ledger = build_ledger_rows(self.build_cases(), fake_scorer, datetime(2026, 9, 4, tzinfo=timezone.utc))
        self.assertEqual(outcome_readout(ledger)["status"], "no_outcomes_yet")

    def test_case_key_matches_linkage_style(self):
        self.assertEqual(build_case_key("Dublin City Council", "3001/25"), "dublin_city_council__3001_25")


class RollingWindowTests(unittest.TestCase):
    def build_predictions(self):
        rows = []
        for month in range(1, 7):
            for index in range(30):
                rows.append({
                    "case_key": f"c_{month}_{index}",
                    "received_date_dt": f"2025-{month:02d}-{(index % 27) + 1:02d}",
                    "target_refused": 1 if index < 3 else 0,
                    "v3_ranking_score": 0.8 if index < 3 else 0.2,
                    "v3_platt_risk": 0.7 if index < 3 else 0.15,
                })
        return pd.DataFrame(rows)

    def test_metric_block_reports_none_for_single_class(self):
        frame = pd.DataFrame({"target_refused": [0, 0, 0], "score": [0.1, 0.2, 0.3]})
        metrics = metric_block(frame["target_refused"], frame["score"])
        self.assertIsNone(metrics["roc_auc"])

    def test_metric_block_computes_on_both_classes(self):
        frame = pd.DataFrame({"target_refused": [0, 0, 1, 1], "score": [0.1, 0.2, 0.8, 0.9]})
        metrics = metric_block(frame["target_refused"], frame["score"])
        self.assertEqual(metrics["roc_auc"], 1.0)

    def test_window_summaries_cover_months_quarters_and_cumulative(self):
        summary, diagnostics = window_summaries(self.build_predictions())
        windows = summary["window"].tolist()
        self.assertEqual(len([w for w in windows if w.startswith("2025-")]), 6)
        self.assertIn("Q1_2025", windows)
        self.assertIn("Q2_2025", windows)
        self.assertIn("cumulative_to_03", windows)
        self.assertIn("cumulative_to_06", windows)

    def test_block_summary_handles_empty_frame(self):
        summary = block_summary(pd.DataFrame(), "empty")
        self.assertEqual(summary["rows"], 0)
        self.assertIsNone(summary["refusal_rate"])


if __name__ == "__main__":
    unittest.main()
