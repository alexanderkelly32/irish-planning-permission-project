"""Runner: import human verdicts from the audit queues into link sets.

Reads audit CSVs where `verdict` is filled, maps confirmed verdicts into
appended link rows (never overwrites existing confirmed links), and writes
verified link overlays used by the next label rebuild.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

AUDIT_DIR = settings.SILVER_DIR / "audit"


def _pick(path: Path) -> Path | None:
    # Completed variants win; check both the audit folder and the silver root.
    candidates = [
        path.parents[1] / Path(str(path.name).replace(".csv", "_COMPLETED.csv")),
        Path(str(path).replace(".csv", "_COMPLETED.csv")),
        path,
        path.parents[1] / path.name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def import_verdicts() -> dict:
    overlay_bcms: list[dict] = []
    overlay_ppr: list[dict] = []
    summary = {"bcms_confirmed": 0, "bcms_rejected": 0, "ppr_confirmed": 0, "ppr_rejected": 0}

    bcms_path = _pick(AUDIT_DIR / "audit_bcms_name_links.csv")
    if bcms_path:
        queue = pd.read_csv(bcms_path)
        filled = queue[queue["verdict"].fillna("").astype(str).str.strip().ne("")]
        for _, row in filled.iterrows():
            verdict = str(row["verdict"]).strip().lower()
            if verdict == "confirmed":
                overlay_bcms.append({
                    "scheme_id": row["scheme_id"],
                    "bcms_event_id": row["bcms_event_id"],
                    "match_method": "human_adjudicated_name_link",
                    "confidence_band": "confirmed",
                    "evidence": str(row.get("verdict_note") or ""),
                })
                summary["bcms_confirmed"] += 1
            elif verdict in {"probable", "rejected"}:
                summary["bcms_rejected"] += 1

    ppr_path = _pick(AUDIT_DIR / "audit_ppr_expanded_links.csv")
    if ppr_path:
        queue = pd.read_csv(ppr_path)
        filled = queue[queue["verdict"].fillna("").astype(str).str.strip().ne("")]
        for _, row in filled.iterrows():
            verdict = str(row["verdict"]).strip().lower()
            if verdict == "confirmed":
                overlay_ppr.append({
                    "scheme_id": row["scheme_id"],
                    "ppr_source_row_id": row["ppr_source_row_id"],
                    "match_method": "human_adjudicated",
                    "confidence_band": "confirmed",
                    "evidence": str(row.get("verdict_note") or ""),
                })
                summary["ppr_confirmed"] += 1
            elif verdict in {"probable", "rejected"}:
                summary["ppr_rejected"] += 1

    if overlay_bcms:
        pd.DataFrame(overlay_bcms).to_csv(AUDIT_DIR / "bcms_verdict_overlay.csv", index=False)
    if overlay_ppr:
        pd.DataFrame(overlay_ppr).to_csv(AUDIT_DIR / "ppr_verdict_overlay.csv", index=False)
    summary["overlay_files"] = {
        "bcms": str(AUDIT_DIR / "bcms_verdict_overlay.csv"),
        "ppr": str(AUDIT_DIR / "ppr_verdict_overlay.csv"),
    }
    out = AUDIT_DIR / "verdict_import_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(import_verdicts(), indent=2))
