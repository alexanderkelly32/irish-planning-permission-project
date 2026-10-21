import unittest

from planner_report_downloader import (
    application_ref_from_url,
    build_agree_payload,
    build_view_files_payload,
    classify_planner_report,
    extract_idocs_url,
    find_files_pdf,
    find_pdf_url,
    parse_copyright_page,
    parse_document_rows,
)


class PlannerReportDownloaderTests(unittest.TestCase):
    def test_extracts_idocs_url_from_eplan_details_page(self):
        html = (
            '<input type="button" onclick="javascript: popupEnquirySubWindow(\''
            'https://idocswebdpss.meathcoco.ie/iDocsWebDPSS/copyright.aspx?catalog=planning&amp;id=22749    \', '
            '\'iDocsQuery\', \'resizable=yes\');" title="Show Related Documents Popup" value="View Scanned Files" />'
        )
        url = extract_idocs_url(html)
        self.assertEqual(url, "https://idocswebdpss.meathcoco.ie/iDocsWebDPSS/copyright.aspx?catalog=planning&id=22749")

    def test_returns_none_without_idocs_button(self):
        self.assertIsNone(extract_idocs_url("<html><body>nothing</body></html>"))

    def test_parses_aspnet_state_fields(self):
        html = (
            '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="vs1" />'
            '<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="ev1" />'
            '<input type="hidden" name="__VIEWSTATEGENERATOR" id="__VIEWSTATEGENERATOR" value="vg1" />'
        )
        state = parse_copyright_page(html)
        self.assertEqual(state["__VIEWSTATE"], "vs1")
        self.assertEqual(state["__EVENTVALIDATION"], "ev1")

    def test_builds_agree_payload(self):
        payload = build_agree_payload({"__VIEWSTATE": "v", "__EVENTVALIDATION": "e", "__VIEWSTATEGENERATOR": "g"})
        self.assertEqual(payload["__EVENTTARGET"], "chkAgree")
        self.assertEqual(payload["chkAgree"], "on")
        self.assertEqual(payload["__VIEWSTATE"], "v")

    def test_parses_document_rows_with_type_and_docid(self):
        html = (
            "<table><tr><td>Type</td><td>Comment</td><td># Files</td><td>Size</td></tr>"
            "<tr><td>Planner's Report</td><td>Planning report</td><td>1</td><td>6076 Kb</td>"
            "<td>&nbsp;</td><td><a target=_blank href='ViewFiles.aspx?docid=2465472&format=djvu'>View</a></td></tr>"
            "<tr><td>Site Layout Plan</td><td>Drawing</td><td>2</td><td>2770 Kb</td>"
            "<td>&nbsp;</td><td><a target=_blank href='ViewFiles.aspx?docid=2461350&format=djvu'>View</a></td></tr>"
            "</table>"
        )
        documents = parse_document_rows(html)
        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0]["type"], "Planner's Report")
        self.assertEqual(documents[0]["docid"], "2465472")
        self.assertEqual(documents[0]["format"], "djvu")

    def test_builds_view_files_payload(self):
        payload = build_view_files_payload({"__VIEWSTATE": "v", "__EVENTVALIDATION": "e", "__VIEWSTATEGENERATOR": "g"})
        self.assertEqual(payload["btnViewFiles"], "View Files")
        self.assertEqual(payload["chkAgree"], "on")

    def test_finds_pdf_url_inside_viewer_page(self):
        html = (
            '<input type="hidden" name="__VIEWSTATE" value="/wE...'
            'ViewPdf.aspx?count=1&file=7db89360-55c2-4fa5-9551-e722d48a3049.pdf'
            'ddk..."/>'
        )
        url = find_pdf_url(html)
        self.assertEqual(url, "ViewPdf.aspx?count=1&file=7db89360-55c2-4fa5-9551-e722d48a3049.pdf")

    def test_finds_files_pdf_inside_viewpdf_page(self):
        html = (
            '<iframe id="theFrame" src=".\\files\\7db89360-55c2-4fa5-9551-e722d48a3049.pdf#view=fit">'
            "</iframe>"
        )
        value = find_files_pdf(html)
        self.assertEqual(value, "files/7db89360-55c2-4fa5-9551-e722d48a3049.pdf")

    def test_classifies_planner_reports_but_not_engineer_reports(self):
        self.assertTrue(classify_planner_report("Planner's Report"))
        self.assertTrue(classify_planner_report("Planning Report - Case Officer"))
        self.assertFalse(classify_planner_report("Engineer's Report"))
        self.assertFalse(classify_planner_report("Site Layout Plan"))

    def test_application_ref_from_url(self):
        self.assertEqual(application_ref_from_url("http://www.eplanning.ie/MeathCC/AppFileRefDetails/22749/0"), "22749")
        self.assertIsNone(application_ref_from_url("http://www.eplanning.ie/MeathCC/searchtypes"))


if __name__ == "__main__":
    unittest.main()
