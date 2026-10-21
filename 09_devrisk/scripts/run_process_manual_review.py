"""Runner: process the completed manual review workbook.

Converts the 1,322 estate-name fills into PPR pulls (estate tokens +
register-address anchor + chronology), merges into scheme_sales_verified.csv,
rebuilds exit/pain labels, reports the yield.
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

if __name__ == "__main__":
    completed = pd.read_excel(settings.SILVER_DIR / "audit_packs" / "returned" / "manual_review_workbook_COMPLETED.xlsx")
    filled = completed[completed["estate_name_1"].fillna("").astype(str).str.strip().ne("")].copy()
    print(f"filled rows: {len(filled)}", flush=True)

    pull_csv = settings.SILVER_DIR / "audit_packs" / "manual_fills_pull.csv"
    pull_rows = filled[["case_key", "authority", "register_address", "estate_name_1", "estate_name_2", "estate_name_3"]].rename(
        columns={"case_key": "scheme_id"})
    pull_rows["eircode"] = filled["bcms_eircode"].fillna("")
    pull_rows.to_csv(pull_csv, index=False)

    temp_out = settings.SILVER_DIR / "audit_packs" / "manual_fills_sales_temp.csv"
    summary = pull(pull_csv, out_path=temp_out)
    pulled = pd.read_csv(temp_out)
    pulled["scheme_id"] = pulled["scheme_id"].astype(str)
    pulled["ppr_source_row_id"] = pulled["ppr_source_row_id"].astype(str)

    verified_path = settings.SILVER_DIR / "scheme_sales_verified.csv"
    verified = pd.read_csv(verified_path)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    verified["ppr_source_row_id"] = verified["ppr_source_row_id"].astype(str)
    before_rows, before_schemes = len(verified), verified["scheme_id"].nunique()
    merged = pd.concat([verified, pulled.reindex(columns=verified.columns)], ignore_index=True)
    merged = merged.drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    merged.to_csv(verified_path, index=False)

    new_schemes = set(pulled["scheme_id"]) - set(verified["scheme_id"])
    report = {
        "filled_rows": int(len(filled)),
        "pulled_sales_rows": int(len(pulled)),
        "new_schemes_with_sales": len(new_schemes),
        "verified_rows": [int(before_rows), int(len(merged))],
        "verified_schemes": [int(before_schemes), int(merged["scheme_id"].nunique())],
    }
    (settings.SILVER_DIR / "manual_review_processing.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
