"""Runner: pull-verification classifier from PACK_18 verdicts.

The sample verdicts (14 confirmed / 1 probable / 65 rejected of 80) mean
the manual-workbook pull runs ~17.5% precision - too low to promote the
60k pending rows. Build a classifier on the verdict features, re-score the
pending set, promote the confirmed schemes, and generate PACK_19 from the
high-confidence band for a second verification round.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402

from devrisk import settings  # noqa: E402
from run_phase_ppr_linking import tokens  # noqa: E402

RNG = 7


def features_of(row: pd.Series) -> dict:
    fill = tokens(row.get("estate_fill") or "")
    address = tokens(row.get("address") or "")
    anchor = tokens(row.get("register_address") or "")
    return {
        "estate_overlap": len(fill & address),
        "anchor_overlap": len(anchor & address),
        "total_overlap": len((fill | anchor) & address),
        "days_after_grant": float(row.get("days_after_grant") or 0),
        "label": int(row.get("label") or 0),
    }


if __name__ == "__main__":
    pack = pd.read_excel(settings.SILVER_DIR / "audit_packs" / "returned" / "audit_manual_pull_verify_COMPLETED_2026-10-01.xlsx")
    verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    fills = pd.read_csv(settings.SILVER_DIR / "audit_packs" / "manual_fills_pull.csv")
    fills["scheme_id"] = fills["scheme_id"].astype(str)

    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    addr_map = dict(zip(cohort["case_key"].astype(str), cohort["DevelopmentAddress"].fillna("").astype(str)))
    grant_map = dict(zip(cohort["case_key"].astype(str), pd.to_datetime(cohort["grant_date_dt"], utc=True, errors="coerce")))

    # Sample scheme ids from the pack (the 80 reviewed) - row-level verdicts
    # were summarised, so we have scheme-level counts only. Use scheme-level
    # labels: schemes whose sampled row was confirmed.
    # (The pack file is a summary; the 80 scheme_ids are in the pack CSV we
    # wrote. Reload that CSV and attach verdicts by position.)
    pack_csv = settings.SILVER_DIR / "audit" / "audit_manual_pull_verify.csv"
    sample_schemes = pd.read_csv(pack_csv)
    sample_schemes["verdict_filled"] = sample_schemes["verdict"].fillna("").astype(str).str.strip().ne("")

    # The completed workbook was summarised rather than row-filled; apply the
    # user's totals to the sample by matching confirmed counts is impossible
    # row-wise. Fall back: use the summary numbers to estimate precision and
    # require a SECOND pack with row-level verdicts for classifier training.
    summary = {
        "pack_rows": int(len(sample_schemes)),
        "user_confirmed": 14,
        "user_probable": 1,
        "user_rejected": 65,
        "sample_precision_estimate": round(14 / 80, 3),
        "action": "pending rows NOT promoted; row-level verdicts needed for classifier training",
    }

    # Promote only the sample's 14 confirmed schemes if row-level verdicts are
    # recoverable from the returned file (they are not; the file is a summary).
    # Record state and generate PACK_19 with row-level verdict columns.
    sample_schemes = sample_schemes.drop(columns=[c for c in ("verdict", "verdict_note") if c in sample_schemes.columns], errors="ignore")
    sample_schemes["verdict"] = ""
    sample_schemes["verdict_note"] = ""
    csv_path = settings.SILVER_DIR / "audit" / "audit_manual_pull_verify_v2.csv"
    sample_schemes.to_csv(csv_path, index=False)
    pack_dir = settings.SILVER_DIR / "audit_packs"
    zip_path = pack_dir / "PACK_19_manual_pull_verify_v2.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 19: same 80 rows, but please mark verdict PER ROW this time\n"
            "(confirmed / probable / rejected) - the summary sheet told us the\n"
            "totals but we need row-level labels to train the pull classifier.\n"
            "RETURN: into the 'returned' folder next to this zip.\n"
        ))

    summary["pack19"] = str(zip_path)
    out = settings.SILVER_DIR / "pack18_processing.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
