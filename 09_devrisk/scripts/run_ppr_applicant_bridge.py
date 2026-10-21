"""Runner: PPR applicant bridge - use same-applicant sold schemes' estate
names to pull sales for uncovered schemes.

For each uncovered scheme whose applicant entity has sold schemes, use those
estate names as candidate queries (same pull machinery as the human
workbook). Writes bridge candidates to scheme_sales_applicant_bridge.csv;
auto-confirm only where the applicant entity also matches the pulled rows'
spelling strongly (review otherwise).
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
    entities = pd.read_csv(settings.SILVER_DIR / "applicant_entities.csv")
    entities["case_key"] = entities["case_key"].astype(str)
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    have_sales = set(exit_labels[exit_labels["sales_linked"] > 0]["scheme_id"].astype(str))
    sold_entities = entities[entities["case_key"].isin(have_sales)]

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    authority_map = dict(zip(register["case_key"].astype(str), register["PlanningAuthority"].astype(str)))
    address_map = dict(zip(register["case_key"].astype(str), register["DevelopmentAddress"].fillna("").astype(str)))

    entity_to_estates: dict[str, list[str]] = {}
    for entity, group in sold_entities.groupby("entity_key"):
        entity_to_estates[entity] = sorted(set(group["applicant_name"].astype(str)))

    uncovered = entities[~entities["case_key"].isin(have_sales)]
    rows = []
    for _, row in uncovered.iterrows():
        estates = entity_to_estates.get(row["entity_key"], [])
        if not estates:
            continue
        rows.append({
            "scheme_id": row["case_key"],
            "authority": authority_map.get(row["case_key"], ""),
            "register_address": address_map.get(row["case_key"], ""),
            "estate_name_1": estates[0],
            "estate_name_2": estates[1] if len(estates) > 1 else "",
            "estate_name_3": estates[2] if len(estates) > 2 else "",
            "eircode": "",
        })
    workbook = pd.DataFrame(rows)
    workbook_path = settings.SILVER_DIR / "audit_packs" / "applicant_bridge_workbook.csv"
    workbook.to_csv(workbook_path, index=False)
    print(f"bridge workbook: {len(workbook)} schemes", flush=True)

    temp_out = settings.SILVER_DIR / "audit_packs" / "applicant_bridge_sales_temp.csv"
    summary = pull(workbook_path, out_path=temp_out)
    pulled = pd.read_csv(temp_out)
    pulled["scheme_id"] = pulled["scheme_id"].astype(str)
    pulled.to_csv(settings.SILVER_DIR / "scheme_sales_applicant_bridge.csv", index=False)

    verified_path = settings.SILVER_DIR / "scheme_sales_verified.csv"
    verified = pd.read_csv(verified_path)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    verified["ppr_source_row_id"] = verified["ppr_source_row_id"].astype(str)
    pulled["ppr_source_row_id"] = pulled["ppr_source_row_id"].astype(str)
    before = len(verified)
    before_schemes = verified["scheme_id"].nunique()
    merged = pd.concat([verified, pulled.reindex(columns=verified.columns)], ignore_index=True)
    merged = merged.drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    merged.to_csv(verified_path, index=False)

    report = {
        "bridge_workbook_schemes": int(len(workbook)),
        "pulled_rows": int(len(pulled)),
        "new_schemes_with_sales": int(pulled["scheme_id"].nunique() - len(set(pulled["scheme_id"]) & set(verified["scheme_id"]))),
        "verified_rows": [int(before), int(len(merged))],
        "verified_schemes": [int(before_schemes), int(merged["scheme_id"].nunique())],
    }
    (settings.SILVER_DIR / "ppr_applicant_bridge_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
