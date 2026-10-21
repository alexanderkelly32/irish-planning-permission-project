"""Linkage failure dissection: attribute serious linkage misses to causes.

Cross-references replay linkage failures and quarantine evidence to
cause buckets: same-name estate / BCMS link quality / PPR attribution /
phase / sales-timing / CCC sequencing / other.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR


def main() -> None:
    quar = pd.read_csv(SILVER / "dq" / "quarantine.csv", dtype=str)
    failures = pd.read_csv(SILVER / "replay" / "replay_failure_taxonomy.csv", dtype=str)
    linkage = failures[failures["classification"] == "linkage_error"]
    bucket = {}
    for _, r in linkage.iterrows():
        key = r["case_key"]
        rules = set(quar[quar["case_key"] == key]["rule"])
        cause = []
        if "R5" in rules:
            cause.append("same_name_estate")
        if "R6" in rules:
            cause.append("bcms_link_quality")
        if "R4" in rules:
            cause.append("ppr_duplicate")
        if "R7" in rules:
            cause.append("phase")
        if "R2" in rules or "R3" in rules:
            cause.append("sales_timing")
        if "R8" in rules:
            cause.append("ccc_sequencing")
        if not cause:
            cause.append("other")
        for c in cause:
            bucket[c] = bucket.get(c, 0) + 1
    report = {
        "n_linkage_failures": int(len(linkage)),
        "attribution": bucket,
        "quarantine_volumes": quar.groupby("rule").size().to_dict(),
    }
    out = SILVER / "replay" / "linkage_dissection.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
