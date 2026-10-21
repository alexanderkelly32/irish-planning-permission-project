import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk.ingestion import bcms  # noqa: E402

MINI_CSV = """IDs,CN_Proposed_use_of_building,CN_Sub_Group,CN_Number_of_Buildings_of_this_building_type,CN_Type_of_Construction,CN_Commencement_Date,CN_Planning_Permission_Number,CN_Date_Granted,CN_Date_Submitted_or_Received,CN_Validation_Date,CN_Proposed_end_date,CN_LAT,CN_LNG,CN_Number,CN_Street,CN_Town,CN_Eircode,CN_County,CN_Total_Number_of_Dwelling_Units,CN_Units_for_phase,CN_Total_apartments,CN_Project_Name,CN_Description_proposed_development,CN_Not_Commenced,CN_Valid_Completion_Certificate,CN_Protected_structure,CN_Approved_housing_body,CN_Project_Status,CN_Validation_Status,CN_Planning_Permission_Required,CCC_Number,CCC_Date_Validated,CCC_Units_Completed,LocalAuthority
1,New Building,Houses,24,Masonry,2019-01-10,PA1234,2018-11-15,2019-01-08,2019-01-09,2021-01-10,53.3591,-6.6500,1,Main Street,Kilcock,W23 XXXX,Meath,24,24,0,Kilcock Wood,construction of 24 dwellings,No,Yes,No,No,Completed,Validated,Yes,CCC111,2021-02-01,24,Meath
2,New Building,Apartments,60,Concrete,2019-10-01,PA5678,2019-09-15,2019-09-20,2019-09-21,2021-10-01,53.2206,-6.6593,5,Newtown Road,Naas,W91 YYYY,Kildare,60,60,60,Naas Central,construction of 60 apartments,No,No,No,No,Completed,Validated,Yes,,,60,Kildare
"""


class BcmsIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.raw = self.base / "bcms.csv"
        self.raw.write_text(MINI_CSV, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_build_bronze(self):
        result = bcms.build_bronze(self.raw, self.base / "bronze", self.base / "manifests")
        bronze = pd.read_parquet(result["bronze_path"])
        self.assertEqual(len(bronze), 2)
        self.assertIn("row_hash", bronze.columns)
        manifest = result["manifest"]
        self.assertIn("bcms_snapshot", manifest["artifact_id"])
        self.assertEqual(manifest["row_counts"]["output_rows"], 2)

    def test_build_silver_canonical_events(self):
        bronze = pd.read_parquet(bcms.build_bronze(self.raw, self.base / "bronze", self.base / "manifests")["bronze_path"])
        result = bcms.build_silver(bronze, self.base / "silver", self.base / "manifests")
        silver = pd.read_parquet(result["silver_path"])
        self.assertEqual(len(silver), 2)
        self.assertIn("address_full", silver.columns)
        self.assertIn("planning_reference", silver.columns)
        self.assertEqual(silver.loc[0, "planning_reference"], "PA1234")
        self.assertEqual(silver.loc[0, "county"], "Meath")
        self.assertIn("completion_certificate_date_dt", silver.columns)
        self.assertEqual(silver.loc[0, "event_type"], "commencement_with_completion_record")
        self.assertEqual(silver.loc[1, "event_type"], "commencement_notice")
        itm = silver["itm_easting"].dropna()
        self.assertEqual(len(itm), 2)  # WGS84 -> ITM conversion worked

    def test_build_bronze_deterministic(self):
        first = pd.read_parquet(bcms.build_bronze(self.raw, self.base / "a", self.base / "ma")["bronze_path"])
        second = pd.read_parquet(bcms.build_bronze(self.raw, self.base / "b", self.base / "mb")["bronze_path"])
        self.assertEqual(first["row_hash"].tolist(), second["row_hash"].tolist())

    def test_download_skipped_if_exists(self):
        target = self.base / "raw" / bcms.RAW_NAME
        target.parent.mkdir(parents=True)
        target.write_text("placeholder", encoding="utf-8")
        result = bcms.download("https://example.invalid/file.csv", self.base / "raw")
        self.assertEqual(result["status"], "exists")


if __name__ == "__main__":
    unittest.main()
