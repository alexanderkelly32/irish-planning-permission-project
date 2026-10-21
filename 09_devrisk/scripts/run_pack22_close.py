"""Runner: close the pull loop - promote PACK_22 confirms, rebuild labels."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"09_devrisk")

import pandas as pd

from devrisk import settings

if __name__ == "__main__":
    audit = pd.read_excel(settings.SILVER_DIR / "audit_packs" / "returned" / "audit_band95_confirm_COMPLETED_2026-10-02.xlsx", sheet_name="Audit")
    confirmed_schemes = set(audit[audit["verdict"].astype(str).str.strip().str.lower() == "confirmed"]["scheme_id"].astype(str))

    verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    # Promote all pending rows of confirmed schemes (band-level promote).
    mask = verified["scheme_id"].isin(confirmed_schemes) & verified["verification_status"].isin(["pending", "promoted_band"])
    verified.loc[mask, "verification_status"] = "verified_band_pack22"
    verified.to_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", index=False)

    report = {
        "pack22": {"confirmed": int((audit["verdict"].astype(str).str.lower() == "confirmed").sum()),
                   "rejected": int((audit["verdict"].astype(str).str.lower() == "rejected").sum()),
                   "band_precision": round(48 / 60, 3)},
        "promoted_rows": int(mask.sum()),
        "promoted_schemes": len(confirmed_schemes),
    }

    result = subprocess.run([sys.executable, "-u", "-X", "utf8",
                             str(settings.ROOT / "09_devrisk" / "scripts" / "run_labels_v2.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="ignore")
    tail = [line for line in (result.stdout or "").splitlines() if "sales_linked" in line or "activation_linked" in line]
    report["label_rebuild"] = tail[-3:]
    (settings.SILVER_DIR / "pack22_processing.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
