"""Runner: process returned PACK_14 (hard-case estate fills) + PACK_15 verdicts.

PACK_14: pull PPR rows for the 226 filled schemes via the workbook puller,
merge into scheme_sales_verified.csv (append-only, dedupe).
PACK_15: record user verdicts (all rejected -> negative labels for the PPR
overlap classifier; no sales imported).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from run_pull_sales import pull  # noqa: E402

RETURNED = settings.SILVER_DIR / "audit_packs" / "returned"

if __name__ == "__main__":
    report: dict = {}

    # ---- PACK 14: hard-case workbook ----
    wb_path = RETURNED / "sales_workbook_HARD_CASES_v2_COMPLETED.xlsx"
    workbook = pd.read_excel(wb_path)
    filled = workbook[workbook[["estate_name_1", "estate_name_2", "estate_name_3", "eircode"]]
                      .fillna("").astype(str).apply(lambda row: row.str.strip().ne("").any(), axis=1)].copy()
    pull_csv = settings.SILVER_DIR / "audit_packs" / "pack14_filled.csv"
    filled[["scheme_id", "authority", "register_address", "estate_name_1", "estate_name_2", "estate_name_3", "eircode"]].to_csv(pull_csv, index=False)

    temp_out = settings.SILVER_DIR / "audit_packs" / "pack14_sales_temp.csv"
    summary = pull(pull_csv, out_path=temp_out)
    pulled = pd.read_csv(temp_out)
    pulled["scheme_id"] = pulled["scheme_id"].astype(str)
    pulled["ppr_source_row_id"] = pulled["ppr_source_row_id"].astype(str)

    verified_path = settings.SILVER_DIR / "scheme_sales_verified.csv"
    verified = pd.read_csv(verified_path)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    verified["ppr_source_row_id"] = verified["ppr_source_row_id"].astype(str)
    before = len(verified)
    before_schemes = verified["scheme_id"].nunique()
    merged = pd.concat([verified, pulled.reindex(columns=verified.columns)], ignore_index=True)
    merged = merged.drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    merged.to_csv(verified_path, index=False)
    new_schemes = set(pulled["scheme_id"]) - set(verified["scheme_id"])
    report["pack14"] = {
        "filled_rows": int(len(filled)),
        "pulled_sales_rows": int(len(pulled)),
        "new_schemes_with_sales": len(new_schemes),
        "verified_rows_before": before,
        "verified_rows_after": int(len(merged)),
        "verified_schemes_before": int(before_schemes),
        "verified_schemes_after": int(merged["scheme_id"].nunique()),
    }

    # ---- PACK 15: 4Dublin verdicts (negatives) ----
    pack15_path = RETURNED / "audit_ppr_4dublin_candidates_COMPLETED.xlsx"
    pack15 = pd.read_excel(pack15_path)
    pack15 = pack15.dropna(subset=["verdict"]).copy()
    negatives_path = settings.SILVER_DIR / "audit" / "ppr_negatives_accumulated.csv"
    negative_cols = ["scheme_id", "ppr_candidate_address", "sale_date", "price", "token_overlap", "verdict", "verdict_note"]
    if negatives_path.exists():
        negatives = pd.read_csv(negatives_path)
        negatives = pd.concat([negatives, pack15[negative_cols].reindex(columns=negatives.columns)], ignore_index=True)
    else:
        negatives = pack15[negative_cols].copy()
    negatives.to_csv(negatives_path, index=False)
    report["pack15"] = {
        "verdicts": pack15["verdict"].value_counts().to_dict(),
        "negatives_accumulated_rows": int(len(negatives)),
    }

    out = settings.SILVER_DIR / "pack14_15_processing.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
