import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.extraction import connectors, contracts  # noqa: E402
from devrisk.provenance import sha256_file  # noqa: E402


class ContractTests(unittest.TestCase):
    def test_valid_payload(self):
        payload = contracts.minimal_template("PA1234")
        payload["events"].append({
            "event_type": "further_information_request",
            "event_date": "2019-02-01",
            "summary": "water services details requested",
            "evidence": [{"document_id": "d1", "page": 3, "quote": "submit details of proposed drainage"}],
            "confidence": 0.9,
        })
        payload["risk_factors"].append({
            "type": "wastewater_dependency", "status": "present", "severity": "material",
            "evidence": [{"document_id": "d1", "page": 3, "quote": "..."}], "confidence": 0.8,
        })
        self.assertEqual(contracts.validate_extraction(payload), [])

    def test_unknown_event_type(self):
        payload = contracts.minimal_template("PA1")
        payload["events"].append({"event_type": "weather_report", "evidence": [{"page": 1, "quote": "x"}]})
        errors = contracts.validate_extraction(payload)
        self.assertTrue(any("unknown event_type" in error for error in errors))

    def test_present_requires_evidence(self):
        payload = contracts.minimal_template("PA1")
        payload["risk_factors"].append({"type": "flood_mitigation", "status": "present"})
        errors = contracts.validate_extraction(payload)
        self.assertTrue(any("present without evidence" in error for error in errors))

    def test_unknown_status_allowed(self):
        payload = contracts.minimal_template("PA1")
        payload["risk_factors"].append({"type": "archaeology", "status": "unknown"})
        self.assertEqual(contracts.validate_extraction(payload), [])

    def test_wrong_schema_version(self):
        payload = contracts.minimal_template("PA1")
        payload["schema_version"] = "planning_friction_v9"
        errors = contracts.validate_extraction(payload)
        self.assertTrue(any("schema_version" in error for error in errors))


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        (self.base / "PA100").mkdir(parents=True)
        (self.base / "PA100" / "fi_request.txt").write_text("Further information requested.", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_local_connector_lists_and_extracts(self):
        connector = connectors.LocalFileConnector(self.base)
        documents = connector.list_documents("PA100")
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["document_type"], "txt")
        path = connector.fetch_document("PA100", "fi_request.txt")
        extraction = connector.extract_text(path)
        self.assertIn("Further information", extraction["native_text"])
        self.assertEqual(extraction["quality"], "native")

    def test_content_addressed_store(self):
        connector = connectors.LocalFileConnector(self.base)
        path = connector.fetch_document("PA100", "fi_request.txt")
        stored = connectors.content_addressed_store(path, self.base / "store")
        digest = sha256_file(path)
        self.assertTrue(stored.name.startswith(digest))
        self.assertEqual(sha256_file(stored), digest)


if __name__ == "__main__":
    unittest.main()
