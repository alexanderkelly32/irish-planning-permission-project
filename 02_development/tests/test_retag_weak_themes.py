import json
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "03_refusal" / "scripts"))

from retag_weak_themes import WEAK_THEMES, build_request, flatten, merge, prepare, select_weak_theme_cases

MASTER_ROWS = [
    {
        "case_key": "a1",
        "council": "Meath",
        "application_number": "AA/1",
        "reason_count": 2,
        "reasons_joined": "The proposal is contrary to the zoning objective. Design is out of character.",
        "case_primary_tags": "land_use_policy",
        "case_top_primary_tag": "land_use_policy",
    },
    {
        "case_key": "a2",
        "council": "Meath",
        "application_number": "AA/2",
        "reason_count": 1,
        "reasons_joined": "The development would seriously injure the visual amenities of the area.",
        "case_primary_tags": "heritage_archaeology",
        "case_top_primary_tag": "heritage_archaeology",
    },
    {
        "case_key": "a3",
        "council": "Meath",
        "application_number": "AA/3",
        "reason_count": 1,
        "reasons_joined": "The density would be excessive on this site.",
        "case_primary_tags": "density_scale",
        "case_top_primary_tag": "density_scale",
    },
    {
        "case_key": "a4",
        "council": "Meath",
        "application_number": "AA/4",
        "reason_count": 1,
        "reasons_joined": "",
        "case_primary_tags": "other",
        "case_top_primary_tag": "other",
    },
]


class RetagWeakThemesTests(unittest.TestCase):
    def test_select_weak_theme_cases_filters_by_tag_and_text(self):
        master = pd.DataFrame(MASTER_ROWS)
        selected = select_weak_theme_cases(master)
        keys = set(selected["case_key"])
        self.assertEqual(keys, {"a1", "a2"})

    def test_strict_prompt_includes_disambiguation_rules(self):
        from retag_weak_themes import SYSTEM_PROMPT
        self.assertIn("heritage_archaeology", SYSTEM_PROMPT)
        self.assertIn("density_scale, NOT land_use_policy", SYSTEM_PROMPT)
        self.assertIn("verbatim quote", SYSTEM_PROMPT)

    def test_build_request_uses_strict_system_prompt(self):
        request = build_request("retag-row-3", "{}")
        system = request["body"]["messages"][0]["content"]
        self.assertIn("strict definitions", system)
        self.assertEqual(request["custom_id"], "retag-row-3")

    def test_flatten_parses_evidence_and_errors(self):
        lines = [
            json.dumps({"custom_id": "retag-row-1", "response": {"body": {"choices": [
                {"message": {"content": json.dumps({
                    "case_primary_tags": "design_layout",
                    "case_top_primary_tag": "design_layout",
                    "confidence": "high",
                    "evidence": {"design_layout": "out of character"},
                    "note": "note",
                })}},
            ]}}}),
            json.dumps({"custom_id": "retag-row-2", "error": {"message": "boom"}}),
        ]
        frame = flatten("\n".join(lines) + "\n")
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.iloc[0]["case_primary_tags"], "design_layout")
        self.assertEqual(json.loads(frame.iloc[0]["evidence"]), {"design_layout": "out of character"})
        self.assertTrue(frame.iloc[1]["api_error"])


if __name__ == "__main__":
    unittest.main()
