"""Packer: PACK_21 - OSM+chronology promoted band confirmation."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    promoted = pd.read_csv(settings.SILVER_DIR / "promoted_v3_osm_rows.csv")
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    addr_map = dict(zip(cohort["case_key"].astype(str), cohort["DevelopmentAddress"].fillna("").astype(str)))
    sample = promoted.groupby("scheme_id").first().reset_index().sample(min(60, promoted["scheme_id"].nunique()), random_state=7)
    sample = sample[["scheme_id", "address", "sale_date", "price", "days_after_grant"]]
    sample["register_address"] = sample["scheme_id"].map(addr_map)
    sample["verdict"] = ""
    sample["verdict_note"] = ""
    csv_path = settings.SILVER_DIR / "audit" / "audit_osm_band_confirm.csv"
    sample.to_csv(csv_path, index=False)
    pack_dir = settings.SILVER_DIR / "audit_packs"
    zip_path = pack_dir / "PACK_21_osm_band_confirm.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 21: OSM+chronology promoted band (112 schemes).\n"
            "Mark verdict PER ROW on the Audit sheet (confirmed/rejected).\n"
            "RETURN: into the 'returned' folder next to this zip.\n"
        ))
    print(f"PACK_21 -> {zip_path} ({len(sample)} rows, {sample['scheme_id'].nunique()} schemes)")
