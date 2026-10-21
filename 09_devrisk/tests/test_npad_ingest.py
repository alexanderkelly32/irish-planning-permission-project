import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.ingestion import npad  # noqa: E402


def mini_register() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "PlanningAuthority": ["Meath County Council", "Kildare County Council", "Dublin City Council"],
            "ApplicationNumber": ["AA1001", "BB2002", "CC3003"],
            "DevelopmentDescription": [
                "construction of 24 houses with access road",
                "construction of 60 apartments in 2 blocks",
                "construction of 12 dwellings",
            ],
            "DevelopmentAddress": ["Main Street, Kilcock", "Newtown Road, Naas", "Ballymun Road, Dublin"],
            "ITMEasting": [701000.0, 692000.0, 716000.0],
            "ITMNorthing": [745000.0, 738000.0, 739000.0],
            "Decision": ["GRANTED", "GRANTED", "REFUSED"],
            "NumResidentialUnits": [24, 60, 12],
            "ReceivedDate": ["2018-05-01", "2019-02-01", "2020-06-01"],
            "DecisionDate": ["2018-11-01", "2019-09-01", "2021-01-01"],
            "GrantDate": ["2018-11-15", "2019-09-15", None],
            "SiteId": ["S1", "S2", "S3"],
        }
    )


class NpadIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "register.parquet"
        mini_register().to_parquet(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def test_build_bronze_writes_manifest_and_hashes(self):
        result = npad.build_bronze(self.source, self.base / "bronze", self.base / "manifests")
        bronze = pd.read_parquet(result["bronze_path"])
        self.assertEqual(len(bronze), 3)
        self.assertTrue((bronze["row_hash"] != "").all())
        self.assertTrue((self.base / "manifests" / "npad_register_bronze.manifest.json").exists())
        manifest = result["manifest"]
        self.assertEqual(manifest["row_counts"]["input_rows"], 3)
        self.assertEqual(manifest["row_counts"]["output_rows"], 3)

    def test_case_key_join_convention(self):
        self.assertEqual(npad.case_key_for("Meath County Council", "AA1001"), "Meath County Council__AA1001")

    def test_row_hash_deterministic(self):
        result_a = npad.build_bronze(self.source, self.base / "a", self.base / "ma")
        result_b = npad.build_bronze(self.source, self.base / "b", self.base / "mb")
        left = pd.read_parquet(result_a["bronze_path"])["row_hash"].tolist()
        right = pd.read_parquet(result_b["bronze_path"])["row_hash"].tolist()
        self.assertEqual(left, right)

    def test_missing_source_raises(self):
        with self.assertRaises(FileNotFoundError):
            npad.build_bronze(self.base / "nope.parquet", self.base / "bronze", self.base / "manifests")


if __name__ == "__main__":
    unittest.main()
