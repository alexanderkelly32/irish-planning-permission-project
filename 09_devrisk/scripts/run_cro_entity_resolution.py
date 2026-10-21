"""Runner: CRO company lookup + applicant entity resolution (background chain).

After the CRO companies.csv.zip download: unzip, build a compact parquet
lookup (company number, name, status, registered address, incorporation
date), then match applicant entities to CRO numbers by normalised name.
Writes cro_company_lookup.parquet + applicant_entities_with_cro.csv.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from run_applicant_features import entity_key  # noqa: E402

ZIP_PATH = settings.RAW_DIR / "companies.csv.zip"


def build_lookup() -> pd.DataFrame:
    with zipfile.ZipFile(ZIP_PATH) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        frame = pd.read_csv(archive.open(name), low_memory=False, dtype=str)
    print(f"cro csv: {len(frame)} rows, columns: {frame.columns.tolist()[:12]}", flush=True)
    col_map = {}
    for column in frame.columns:
        lowered = column.strip().lower()
        if lowered in {"company_num", "company_number", "regnumber", "cro_number", "company number"}:
            col_map["company_number"] = column
        elif lowered in {"company_name", "companyname", "name"}:
            col_map["company_name"] = column
        elif lowered in {"company_status", "company_status_code"}:
            col_map.setdefault("company_status", column)
        elif lowered.startswith("company_address"):
            col_map.setdefault("registered_address", column)
        elif lowered in {"company_reg_date", "incorporation_date", "registration date"}:
            col_map["incorporation_date"] = column
        elif lowered in {"company_type", "company_type_code"}:
            col_map.setdefault("company_type", column)
        elif lowered in {"comp_dissolved_date", "dissolved_date"}:
            col_map["dissolved_date"] = column
        elif lowered == "nace_v2_code":
            col_map["nace_code"] = column
        elif lowered == "eircode":
            col_map["eircode"] = column
    lookup = pd.DataFrame()
    for target, source in col_map.items():
        lookup[target] = frame[source].astype(str)
    if "company_number" not in lookup.columns or "company_name" not in lookup.columns:
        raise ValueError(f"could not map CRO columns; actual: {frame.columns.tolist()[:20]}")
    lookup["name_key"] = lookup["company_name"].map(entity_key)
    lookup = lookup[lookup["name_key"].str.len().ge(3)].drop_duplicates("company_number")
    out = settings.SILVER_DIR / "cro_company_lookup.parquet"
    lookup.to_parquet(out, index=False)
    return lookup


def match_applicants(lookup: pd.DataFrame) -> pd.DataFrame:
    entities = pd.read_csv(settings.SILVER_DIR / "applicant_entities.csv") if (settings.SILVER_DIR / "applicant_entities.csv").exists() else pd.DataFrame()
    if entities.empty:
        return entities
    entities["entity_key"] = entities["entity_key"].astype(str)
    cro_by_key = lookup.drop_duplicates("name_key").set_index("name_key")
    entities = entities.merge(cro_by_key[["company_number", "company_name", "company_status", "registered_address", "incorporation_date"]],
                              left_on="entity_key", right_index=True, how="left")
    out = settings.SILVER_DIR / "applicant_entities_with_cro.csv"
    entities.to_csv(out, index=False)
    summary = {
        "applicant_rows": int(len(entities)),
        "matched_to_cro": int(entities["company_number"].notna().sum()),
        "match_rate": round(float(entities["company_number"].notna().mean()), 4),
        "out": str(out),
    }
    (settings.SILVER_DIR / "cro_match_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return entities


if __name__ == "__main__":
    if not ZIP_PATH.exists():
        print("companies.csv.zip not present yet", flush=True)
        raise SystemExit(0)
    lookup = build_lookup()
    match_applicants(lookup)
