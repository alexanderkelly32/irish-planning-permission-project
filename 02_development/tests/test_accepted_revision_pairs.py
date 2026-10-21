import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from accepted_revision_pairs import build_accepted_revision_exports, read_revision_audit_csv


class AcceptedRevisionPairTests(unittest.TestCase):
    def test_exports_only_manually_accepted_pairs_and_two_case_group_memberships(self):
        pairs = pd.DataFrame([
            {"original_case_key": "a__1", "revised_case_key": "a__2", "original_outcome": "REFUSED", "revised_outcome": "GRANTED"},
            {"original_case_key": "b__1", "revised_case_key": "b__2", "original_outcome": "REFUSED", "revised_outcome": "GRANTED"},
        ])
        audit = pd.DataFrame([
            {"original_case_key": "a__1", "revised_case_key": "a__2", "audit_status": "accepted", "audit_notes": "Same site and revised scheme."},
            {"original_case_key": "b__1", "revised_case_key": "b__2", "audit_status": "rejected", "audit_notes": "Extension of permission."},
        ])

        accepted, group_map = build_accepted_revision_exports(pairs, audit)

        self.assertEqual(accepted["original_case_key"].tolist(), ["a__1"])
        self.assertEqual(accepted["audit_status"].tolist(), ["accepted"])
        self.assertEqual(group_map["case_key"].tolist(), ["a__1", "a__2"])
        self.assertEqual(group_map["project_group_id"].nunique(), 1)
        self.assertEqual(group_map["pair_role"].tolist(), ["original_refused", "revised_granted"])

    def test_rejects_unknown_audit_statuses_and_acceptance_without_a_note(self):
        pairs = pd.DataFrame([{"original_case_key": "a__1", "revised_case_key": "a__2"}])
        unknown = pd.DataFrame([{"original_case_key": "a__1", "revised_case_key": "a__2", "audit_status": "maybe", "audit_notes": ""}])
        unnoted = pd.DataFrame([{"original_case_key": "a__1", "revised_case_key": "a__2", "audit_status": "accepted", "audit_notes": ""}])

        with self.assertRaises(ValueError):
            build_accepted_revision_exports(pairs, unknown)
        with self.assertRaises(ValueError):
            build_accepted_revision_exports(pairs, unnoted)

    def test_reads_windows_encoded_audit_notes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "audit.csv"
            text = "original_case_key,revised_case_key,audit_status,audit_notes\n" + "a__1,a__2,accepted,That\u2019s the same scheme\n"
            path.write_bytes(text.encode("cp1252"))
            audit = read_revision_audit_csv(path)

        self.assertEqual(audit.loc[0, "audit_notes"], "That\u2019s the same scheme")

    def test_preserves_utf8_text_when_one_windows_punctuation_byte_is_present(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "audit.csv"
            text = "original_case_key,revised_case_key,audit_status,audit_notes\n" + "a__1,a__2,accepted,It\u2019s a genuine caf\u00e9 scheme\n"
            path.write_bytes(text.encode("utf-8").replace(b"\xe2\x80\x99", b"\x92"))
            audit = read_revision_audit_csv(path)

        self.assertEqual(audit.loc[0, "audit_notes"], "It\u2019s a genuine caf\u00e9 scheme")


if __name__ == "__main__":
    unittest.main()
