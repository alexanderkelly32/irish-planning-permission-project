"""Runner: process PACK_17 verdicts + record the structural finding.

PACK_17 result: 2 confirmed / 493 probable / 482 rejected of 977. The
rejections decompose into locality-only (367), phase-reference-unstated
(91), and house-number-out-of-range (24) - i.e. phase-level attribution
cannot be determined from public data alone. Verdicts are accumulated with
reason taxonomy; the label gate remains not met for phase-level sale links.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    pack = pd.read_excel(settings.SILVER_DIR / "audit_packs" / "returned" / "phase_sale_links_v2_COMPLETED.xlsx")
    filled = pack[pack["verdict"].fillna("").astype(str).str.strip().str.lower().isin(["confirmed", "probable", "rejected"])].copy()

    def reason_of(row: pd.Series) -> str:
        note = str(row.get("verdict_note") or "").lower()
        if "range" in note or "house number" in note:
            return "range_mismatch"
        if "phase" in note or "unit" in note:
            return "phase_ref_unstated"
        if "town" in note or "road" in note or "locality" in note:
            return "locality_only"
        return "other"

    filled["reason_category"] = filled.apply(
        lambda r: reason_of(r) if r["verdict"].strip().lower() == "rejected" else
        ("insufficient_evidence" if r["verdict"].strip().lower() == "probable" else "confirmed"), axis=1)

    out_path = settings.SILVER_DIR / "audit" / "phase_sale_adjudication_accumulated.csv"
    if out_path.exists():
        previous = pd.read_csv(out_path)
        merged = pd.concat([previous, filled.reindex(columns=previous.columns)], ignore_index=True)
    else:
        merged = filled
    merged.to_csv(out_path, index=False)

    report = {
        "pack17_verdicts": filled["verdict"].value_counts().to_dict(),
        "rejection_taxonomy": filled[filled["verdict"] == "rejected"]["reason_category"].value_counts().to_dict(),
        "b_v2_precision_confirmed_only": round(float((filled["verdict"] == "confirmed").sum() / max(1, len(filled))), 4),
        "label_gate": "NOT MET - phase-level sale attribution undeterminable from public data (unit addresses / phase ranges unpublished)",
        "structural_finding": (
            "PPR addresses identify estate + house number; BCMS publishes phase number and units "
            "but not per-phase house-number ranges or unit addresses. Therefore 'is this sale in this "
            "phase' is unanswerable from public data except when the sale address itself states the "
            "phase/block. Unit-address-level sources (ECAD Created Dates, BER addresses) or planning "
            "phasing schedules are required."
        ),
        "revised_verdict_schema_for_future_packs": [
            "confirmed", "probable_insufficient_evidence", "rejected_wrong_development",
        ],
        "next_actions": [
            "development-level sale leg proceeds on the 763 scheme-level verified links (estate-level, spot-checked 8/8-10/10)",
            "phase-level sale attribution resumes when ECAD/BER unit addresses land",
            "phase-level commencement/CCC targets remain valid (BCMS is phase-native)",
        ],
    }
    out = settings.SILVER_DIR / "pack17_processing.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
