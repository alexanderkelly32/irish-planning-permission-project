"""Packer: bundle each audit into its own zip with tailored instructions."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

PACK_DIR = settings.SILVER_DIR / "audit_packs"
RETURN_DIR = PACK_DIR / "returned"


def _zip(pack_dir: Path, zip_name: str, files: list[Path], instructions: str) -> Path:
    zip_path = pack_dir / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, arcname=file.name)
        archive.writestr("INSTRUCTIONS.txt", instructions)
    return zip_path


if __name__ == "__main__":
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    RETURN_DIR.mkdir(exist_ok=True)

    packs = []

    # Pack 1: sales workbook (priority)
    sales_csv = settings.SILVER_DIR / "sales_workbook.csv"
    if sales_csv.exists():
        workbook = pd.read_csv(sales_csv)
        for col in ["estate_name_1", "estate_name_2", "estate_name_3", "eircode", "sellable_units", "is_build_to_sell", "notes"]:
            workbook[col] = workbook[col].fillna("").astype(str)
        sales_pack = PACK_DIR / "sales_workbook.csv"
        workbook.to_csv(sales_pack, index=False)
        packs.append(_zip(PACK_DIR, "PACK_1_sales_workbook.zip", [sales_pack], (
            "PACK 1 (PRIORITY): Sales workbook - fill estate names so PPR sales can be pulled.\n"
            "------------------------------------------------------------------\n"
            "Open sales_workbook.csv. For each scheme you recognise (or can check on\n"
            "propertypriceregister.ie search):\n"
            "  estate_name_1/2/3: the development's name AS PPR SPELLS IT (variants in\n"
            "                      separate columns; PPR has typos - e.g. 'burrinroad').\n"
            "  eircode: any one unit's eircode if known (helps enormously).\n"
            "  sellable_units: actual individually-sold unit count if known (blank = use\n"
            "                  proposed units).\n"
            "  is_build_to_sell: Y for ordinary build-to-sell; N for BTR/social/PRS/\n"
            "                    retained (N schemes are excluded from sell-through).\n"
            "  notes: phases, marketing names, anything material.\n"
            "Partial filling is fine - every filled row is one scheme we can pull.\n"
            "suggested_estate_tokens is a hint from BCMS records, not a fact.\n"
            "RETURN: save the filled CSV (same name) into the 'returned' folder\n"
            "next to this zip and tell us - or email/return it anywhere and say where.\n"
        )))

    # Pack 2: BCMS name links
    bcms_csv = settings.SILVER_DIR / "audit" / "audit_bcms_name_links.csv"
    if bcms_csv.exists():
        packs.append(_zip(PACK_DIR, "PACK_2_bcms_name_links.zip", [bcms_csv], (
            "PACK 2: BCMS name-link adjudication (200 rows, 176 schemes).\n"
            "------------------------------------------------------------\n"
            "Each row pairs a scheme with a BCMS candidate found nearby by name/address.\n"
            "Set verdict:\n"
            "  confirmed  - clearly the same development (estate name + town agree,\n"
            "               distance small, dates sensible).\n"
            "  probable   - likely but not certain (kept out of training).\n"
            "  rejected   - clearly different scheme (note why; 'no BCMS notice exists'\n"
            "               is a legitimate finding, not a failure).\n"
            "Use verdict_note for anything material. Blank rows are ignored.\n"
            "RETURN: save into the 'returned' folder next to this zip and tell us.\n"
        )))

    # Pack 3: PPR expanded links
    ppr_csv = settings.SILVER_DIR / "audit" / "audit_ppr_expanded_links.csv"
    if ppr_csv.exists():
        packs.append(_zip(PACK_DIR, "PACK_3_ppr_expanded_links.zip", [ppr_csv], (
            "PACK 3: PPR sale-candidate adjudication (450 rows, 150 schemes).\n"
            "---------------------------------------------------------------\n"
            "Each row pairs a scheme with a PPR transaction matched by estate-name\n"
            "tokens. Check the address against the scheme (propertypriceregister.ie\n"
            "search helps). Set verdict:\n"
            "  confirmed - same scheme (estate + town agree, sale after grant).\n"
            "  probable  - likely but not certain.\n"
            "  rejected  - different scheme.\n"
            "sale_after_grant=1 means the sale date is after the grant date.\n"
            "RETURN: save into the 'returned' folder next to this zip and tell us.\n"
        )))

    # Pack 4: older pilot queues (optional, mostly superseded)
    pilot_bcms = settings.SILVER_DIR / "audit_queue_bcms_links.csv"
    pilot_ppr = settings.SILVER_DIR / "audit_queue_ppr_links.csv"
    if pilot_bcms.exists() and pilot_ppr.exists():
        packs.append(_zip(PACK_DIR, "PACK_4_legacy_pilot_queues.zip", [pilot_bcms, pilot_ppr], (
            "PACK 4 (OPTIONAL): legacy pilot queues - mostly superseded by packs 2-3.\n"
            "Only fill if you want extra coverage beyond packs 1-3.\n"
            "Same verdict options: confirmed | probable | rejected (+ note).\n"
        )))

    # Pack 5: vertical slice identity review
    vs_csv = settings.SILVER_DIR / "vertical_slice_10_review.csv"
    if vs_csv.exists():
        packs.append(_zip(PACK_DIR, "PACK_5_vertical_slice_10_schemes.zip", [vs_csv], (
            "PACK 5 (OPTIONAL): ten-scheme identity vertical slice.\n"
            "23 candidate rows across 10 schemes with full identity evidence.\n"
            "Fill review_decision (confirmed/rejected) + review_note.\n"
        )))

    (PACK_DIR / "README.txt").write_text(
        "AUDIT PACKS - fill any/all, return filled CSVs to the 'returned' folder.\n"
        "Pack 1 (sales workbook) is the highest return; packs 2-3 expand BCMS/PPR\n"
        "linkage; packs 4-5 are optional legacy/identity checks.\n",
        encoding="utf-8",
    )

    print(f"PACK_DIR: {PACK_DIR}")
    print(f"RETURN_DIR: {RETURN_DIR}")
    for pack in packs:
        print(f"  {pack.name} ({pack.stat().st_size // 1024} KB)")
