"""Packer: PACK_17 - linking v2 adjudication (confirmed estate dictionary)."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    candidates = pd.read_csv(settings.SILVER_DIR / "phase_sales_candidates_v2.csv")
    parts = []
    for phase_id, group in candidates.groupby("phase_id"):
        parts.append(group.sample(min(3, len(group)), random_state=7))
    sample = pd.concat(parts, ignore_index=True)
    sample = sample.drop(columns=[c for c in ("verdict", "verdict_note") if c in sample.columns])
    sample["verdict"] = ""
    sample["verdict_note"] = ""
    csv_path = settings.SILVER_DIR / "audit" / "audit_phase_sale_links_v2.csv"
    sample.to_csv(csv_path, index=False)

    pack_dir = settings.SILVER_DIR / "audit_packs"
    zip_path = pack_dir / "PACK_17_phase_sale_links_v2.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 17: phase sale links v2 (estate names now come from your\n"
            "confirmed workbook fills / BCMS-notice matches, not raw text).\n"
            "Same verdicts: confirmed | probable | rejected.\n"
            "Focus on the B rows. Target >=95%% precision on confirmed.\n"
            "RETURN: save into the 'returned' folder next to this zip.\n"
        ))
    print(f"PACK_17 -> {zip_path} ({len(sample)} rows, {sample['phase_id'].nunique()} phases)")
