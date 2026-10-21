import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk import provenance  # noqa: E402


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_sha256_is_stable(self):
        path = self.base / "f.txt"
        path.write_text("hello world", encoding="utf-8")
        self.assertEqual(provenance.sha256_file(path), provenance.sha256_file(path))

    def test_stable_row_hash_ignores_key_order(self):
        self.assertEqual(
            provenance.stable_row_hash({"a": 1, "b": "x"}),
            provenance.stable_row_hash({"b": "x", "a": 1}),
        )

    def test_manifest_round_trip(self):
        manifest = provenance.build_manifest(
            artifact_id="test_artifact",
            source={"kind": "test"},
            inputs=[{"path": "x", "sha256": "abc"}],
            transformation={"code": "t", "code_version": "v1"},
            counts={"input_rows": 1, "output_rows": 1, "rejected_rows": 0},
            outputs=[],
            schema_columns=["a"],
        )
        path = provenance.write_manifest(manifest, self.base, "test_artifact")
        loaded = provenance.read_manifest(self.base, "test_artifact")
        self.assertEqual(loaded["artifact_id"], "test_artifact")
        self.assertEqual(loaded["schema_version"], "manifest_v1")
        self.assertTrue(path.exists())

    def test_available_at_after_snapshot_raises(self):
        with self.assertRaises(provenance.AvailabilityError):
            provenance.enforce_available_at("feature_x", "2024-06-01", "2024-01-01")

    def test_available_at_before_snapshot_ok(self):
        provenance.enforce_available_at("feature_x", "2023-06-01", "2024-01-01")

    def test_available_at_datetime_objects(self):
        provenance.enforce_available_at(
            "feature_x", dt.datetime(2023, 6, 1, tzinfo=dt.timezone.utc), dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
        )

    def test_missing_available_at_raises(self):
        with self.assertRaises(provenance.AvailabilityError):
            provenance.enforce_available_at("feature_x", None, "2024-01-01")


if __name__ == "__main__":
    unittest.main()
