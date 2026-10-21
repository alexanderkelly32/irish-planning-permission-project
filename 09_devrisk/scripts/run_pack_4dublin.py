"""Packer: PACK_15 - 4Dublin pipeline-address PPR candidates (8 schemes).

These auto-matches are road/townland-level (overlap 3 on non-estate tokens),
so they need human confirmation before import - precision-first rule.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    auto = pd.read_csv(settings.SILVER_DIR / "scheme_sales_4dublin_auto.csv")
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    meta = cohort[cohort["case_key"].astype(str).isin(auto["scheme_id"])].set_index("case_key")
    pipe = pd.read_csv(settings.SILVER_DIR / "4dublin" / "pipeline_all.csv", low_memory=False)
    pipe = pipe.dropna(subset=["Development_Address"]).copy()
    pipe["app_norm"] = pipe["Planning_Reference"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    pipe = pipe.sort_values("Year_Quarter").groupby("app_norm").tail(1)[["app_norm", "Development_Address"]]

    rows = []
    for _, candidate in auto.iterrows():
        scheme = meta.loc[candidate["scheme_id"]]
        pipe_address = pipe.loc[pipe["app_norm"] == str(scheme["ApplicationNumber"]).strip().upper(), "Development_Address"]
        pipe_address = pipe_address.iloc[0] if len(pipe_address) else ""
        rows.append({
            "scheme_id": candidate["scheme_id"],
            "authority": scheme["PlanningAuthority"],
            "grant_year": int(scheme["grant_year"]),
            "units": scheme["NumResidentialUnits"],
            "register_address": str(scheme["DevelopmentAddress"])[:100],
            "pipeline_address": str(pipe_address)[:100],
            "ppr_candidate_address": candidate["address"],
            "sale_date": candidate["sale_date"],
            "price": candidate["price"],
            "token_overlap": candidate["token_overlap"],
            "verdict": "",
            "verdict_note": "",
        })
    workbook = pd.DataFrame(rows).drop_duplicates()
    csv_path = settings.SILVER_DIR / "audit" / "audit_ppr_4dublin_candidates.csv"
    workbook.to_csv(csv_path, index=False)

    pack_dir = settings.SILVER_DIR / "audit_packs"
    pack_dir.mkdir(parents=True, exist_ok=True)
    zip_path = pack_dir / "PACK_15_4dublin_ppr_candidates.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 15: 4Dublin pipeline-address PPR candidates (8 schemes, ~150 rows).\n"
            "------------------------------------------------------------------------\n"
            "The 4Dublin pipeline gave an independent address for these Dublin schemes.\n"
            "The PPR candidates match on road/townland tokens only (not estate names),\n"
            "so they might be a neighbouring estate. Set verdict per row:\n"
            "  confirmed - same scheme (estate/road/town agree, sale after grant).\n"
            "  probable  - likely but not certain.\n"
            "  rejected  - different scheme.\n"
            "verdict_note: optional evidence (e.g. 'check PPR: oldcourt lodge is\n"
            "the scheme on Oldcourt Road' or 'carrig court is adjacent, not ours').\n"
            "RETURN: save into the 'returned' folder next to this zip and tell us.\n"
        ))
    print(f"PACK_15 -> {zip_path} ({len(workbook)} rows, {workbook['scheme_id'].nunique()} schemes)")
