"""Runner: mark new pulled rows pending + build PACK_18 verification sample.

The 64,799 pulled rows carry ~80% spot precision (8/10 clean) - importable
as pending, not confirmed. Mark match_method='human_estate_name_tokens'
rows as verification_status='pending', sample ~80 new-scheme rows into a
verification pack for the user.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    verified_path = settings.SILVER_DIR / "scheme_sales_verified.csv"
    verified = pd.read_csv(verified_path, low_memory=False)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    if "verification_status" not in verified.columns:
        verified["verification_status"] = "verified_prior"
    pending_mask = verified["match_method"].fillna("").astype(str).eq("human_estate_name_tokens")
    verified.loc[pending_mask, "verification_status"] = "pending"
    verified.to_csv(verified_path, index=False)

    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    addr = dict(zip(cohort["case_key"].astype(str), cohort["DevelopmentAddress"].fillna("").astype(str)))
    pending = verified[verified["verification_status"] == "pending"].copy()
    new_schemes = pending.groupby("scheme_id").first().reset_index().sample(min(80, pending["scheme_id"].nunique()), random_state=7)
    pack = new_schemes[["scheme_id", "address", "eircode", "sale_date", "price"]].copy()
    pack["register_address"] = pack["scheme_id"].map(addr)
    pack["verdict"] = ""
    pack["verdict_note"] = ""
    pack = pack[["scheme_id", "register_address", "address", "eircode", "sale_date", "price", "verdict", "verdict_note"]]
    csv_path = settings.SILVER_DIR / "audit" / "audit_manual_pull_verify.csv"
    pack.to_csv(csv_path, index=False)

    pack_dir = settings.SILVER_DIR / "audit_packs"
    zip_path = pack_dir / "PACK_18_manual_pull_verify.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 18: verify the manual-workbook sales pulls.\n"
            "One row per newly-linked scheme (sample of ~80).\n"
            "verdict: confirmed (same estate) | rejected (wrong match).\n"
            "probable allowed but kept out of confirmed labels.\n"
            "RETURN: into the 'returned' folder next to this zip.\n"
        ))

    summary = {
        "pending_rows": int(pending_mask.sum()),
        "verified_prior_rows": int((~pending_mask).sum()),
        "pack_rows": int(len(pack)),
        "pack": str(zip_path),
    }
    (settings.SILVER_DIR / "manual_pull_verification_status.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
