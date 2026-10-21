import unittest

import sys

sys.path.insert(0, r"02_development\scripts")
from agile_applications_client import application_id_from_url, classify_document, client_code_from_url


class AgileApplicationsClientTests(unittest.TestCase):
    def test_application_id_extraction(self):
        self.assertEqual(
            application_id_from_url("https://planning.agileapplications.ie/wexford/application-details/102606"),
            "102606",
        )
        self.assertIsNone(application_id_from_url("https://www.eplanning.ie/MeathCC/AppFileRefDetails/231045/0"))

    def test_client_code_extraction(self):
        self.assertEqual(client_code_from_url("https://planning.agileapplications.ie/dublincity/application-details/158955"), "DUBLINCITY")
        self.assertEqual(client_code_from_url("https://planning.agileapplications.ie/wexford/application-details/1"), "WEXFORD")

    def test_classify_media_description_priority(self):
        self.assertEqual(classify_document({"name": "01190796.pdf", "mediaDescription": "Decision"}), "Decision Notice")
        self.assertEqual(classify_document({"name": "x.pdf", "mediaDescription": "Planners Report"}), "Planners Report")
        self.assertEqual(classify_document({"name": "x.pdf", "mediaDescription": "Report Received from External Body"}), "Report")
        self.assertEqual(classify_document({"name": "x.pdf", "mediaDescription": "F.I. Receipt Ack. Letter"}), None)
        self.assertEqual(classify_document({"name": "Site Layout Drawing", "mediaDescription": ""}), "Drawing")

    def test_unclassifiable_returns_none(self):
        self.assertIsNone(classify_document({"name": "Misc", "mediaDescription": "Other"}))


if __name__ == "__main__":
    unittest.main()
