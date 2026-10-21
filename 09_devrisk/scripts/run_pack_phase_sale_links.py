"""Packer: PACK_16 phase-level sale-link audit (plan step 3E).

Stratified sample of B-class candidates + all A + a C sample. Verdicts:
confirmed (same phase estate), probable, rejected. Target >=95% precision on
B/A for the training cohort.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    candidates = pd.read_csv(settings.SILVER_DIR / "phase_sales_candidates.csv")
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    phase_meta = phases.set_index("phase_id")[["town", "street", "project_name", "phase_units", "development_id"]]
    candidates = candidates.drop(columns=[c for c in ("town", "street", "phase_units", "development_id") if c in candidates.columns])
    candidates = candidates.merge(phase_meta, left_on="phase_id", right_index=True, how="left")

    rng = 7
    a = candidates[candidates["confidence"] == "A"]
    b = candidates[candidates["confidence"] == "B"]
    c = candidates[candidates["confidence"] == "C"].sample(min(100, len(candidates[candidates["confidence"] == "C"])), random_state=rng)
    b_sample = b.groupby("phase_id", group_keys=False).apply(lambda g: g.sample(min(3, len(g)), random_state=rng))
    pack = pd.concat([a, b_sample, c], ignore_index=True)
    pack = pack[["phase_id", "development_id", "town", "street", "project_name", "phase_units",
                 "address", "eircode", "sale_date", "price", "confidence", "verdict", "verdict_note"]]
    csv_path = settings.SILVER_DIR / "audit" / "audit_phase_sale_links.csv"
    pack.to_csv(csv_path, index=False)

    pack_dir = settings.SILVER_DIR / "audit_packs"
    zip_path = pack_dir / "PACK_16_phase_sale_links.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 16: phase-level sale-link adjudication (step 3E of the\n"
            "phase time-to-sale plan).\n"
            "Each row pairs a construction phase with a PPR sale candidate.\n"
            "Set verdict:\n"
            "  confirmed - same estate/phase (address + town + timing agree).\n"
            "  probable  - likely but not certain.\n"
            "  rejected  - different development.\n"
            "Focus on B and A rows (the C rows are exploratory). Target is\n"
            "95%% precision on the confirmed set, not recall.\n"
            "RETURN: save into the 'returned' folder next to this zip.\n"
        ))
    print(f"PACK_16 -> {zip_path} ({len(pack)} rows: A={len(a)}, B={len(b_sample)}, C={len(c)})")
