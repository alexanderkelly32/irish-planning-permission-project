"""Runner: starter grant-condition family labels from available planner reports.

Uses the rule-based classifier on the repository's existing planner-report
texts (02_development/current/planner_report_verification_fixed.csv - 17
verified case keys). Writes a starter label table plus a coverage note; the
audited pilot-authority corpus (Sprint 6) replaces this with LLM extraction
under the condition_families_v1 contract.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.reporting.condition_families import classify_document, families_to_record  # noqa: E402

if __name__ == "__main__":
    source = settings.ROOT / "02_development" / "current" / "planner_report_verification_fixed.csv"
    frame = pd.read_csv(source, low_memory=False)
    records = []
    for case_key, group in frame.groupby("case_key"):
        text = " ".join(group["document_text"].fillna("").astype(str).tolist())
        if len(text.strip()) < 200:
            continue
        result = classify_document(text)
        records.append(families_to_record(str(case_key), result, granted=True))

    labels = pd.DataFrame(records)
    labels.to_csv(settings.SILVER_DIR / "condition_family_labels_starter.csv", index=False)

    summary = {
        "source": str(source),
        "schemes_labelled": int(len(labels)),
        "method": "regex_condition_families_v1",
        "family_prevalence": {
            column.replace("condition_", ""): int(labels[column].sum())
            for column in labels.columns if column.startswith("condition_") and column != "condition_family_count"
        },
        "note": "starter label set only; needs audited pilot-authority corpus + LLM extraction (condition_families_v1) and field-level audit before modelling P(condition_family|grant)",
    }
    out = settings.SILVER_DIR / "condition_family_labels_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
