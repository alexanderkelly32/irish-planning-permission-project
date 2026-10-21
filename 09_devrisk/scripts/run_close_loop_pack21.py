"""Runner: close the loop - promote PACK_21 confirms, rebuild labels,
rerun the sale ladder, and pack the p>=0.95 band as PACK_22 (final round)."""
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, r"09_devrisk")
sys.path.insert(0, r"09_devrisk/scripts")

import pandas as pd

from devrisk import settings

if __name__ == "__main__":
    audit = pd.read_excel(settings.SILVER_DIR / "audit_packs" / "returned" / "audit_osm_band_confirm_COMPLETED_2026-10-02.xlsx", sheet_name="Audit")
    confirmed_schemes = set(audit[audit["verdict"].astype(str).str.strip().str.lower() == "confirmed"]["scheme_id"].astype(str))

    verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    mask = verified["scheme_id"].isin(confirmed_schemes) & verified["verification_status"].isin(["pending", "promoted_band"])
    verified.loc[mask, "verification_status"] = "verified_human_pack21"
    verified.to_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", index=False)
    print("promoted rows:", int(mask.sum()), "schemes:", len(confirmed_schemes))

    scored = pd.read_csv(settings.SILVER_DIR / "pending_rows_scored_v3.csv")
    band = scored[scored["p_link"] >= 0.95].copy()
    sample = band.groupby("scheme_id").first().reset_index().sample(min(60, band["scheme_id"].nunique()), random_state=7)
    sample["verdict"] = ""
    sample["verdict_note"] = ""
    csv_path = settings.SILVER_DIR / "audit" / "audit_band95_confirm.csv"
    sample[["scheme_id", "address", "sale_date", "price", "p_link", "verdict", "verdict_note"]].to_csv(csv_path, index=False)
    zip_path = settings.SILVER_DIR / "audit_packs" / "PACK_22_band95_confirm.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 22 (final round): p>=0.95 classifier band.\n"
            "Mark verdict PER ROW (confirmed/rejected).\n"
            "RETURN: into the 'returned' folder.\n"))
    print(f"PACK_22 -> {zip_path} ({len(sample)} rows)")

    # Rebuild labels with the enlarged verified set.
    import subprocess
    result = subprocess.run([sys.executable, "-u", "-X", "utf8",
                             str(settings.ROOT / "09_devrisk" / "scripts" / "run_labels_v2.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="ignore")
    tail = [line for line in (result.stdout or "").splitlines() if "sales_linked" in line or "activation" in line]
    print("\n".join(tail[-4:]))
