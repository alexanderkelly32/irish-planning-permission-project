"""Runner: build phase_master (plan step 1).

One row per BCMS commencement notice (a notice ~ a construction phase),
linked to its development via confirmed BCMS links. Includes phase
morphology, declared dates, permitted/phase units, tenure/route class
(rule-based), developer SPV/group, and coordinates. Duplicate notices are
flagged, not merged.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

BTR_RE = re.compile(r"build to rent|build-to-rent|private rental|\bprs\b|rental scheme|multifamily|forward fund|forward-fund", re.IGNORECASE)
SOCIAL_RE = re.compile(r"social housing|approved housing body|\bahb\b|turnkey|part v", re.IGNORECASE)
PARTV_RE = re.compile(r"part v", re.IGNORECASE)
TURNKEY_RE = re.compile(r"turnkey", re.IGNORECASE)
FORWARD_RE = re.compile(r"forward fund|forward-fund|advance purchas", re.IGNORECASE)


def classify_route(row: pd.Series) -> str:
    text = f"{row.get('description_raw') or ''} {row.get('project_name') or ''}".lower()
    ahb = str(row.get("approved_housing_body") or "").strip().lower() in {"yes", "y", "true"}
    apartments = float(row.get("apartments") or 0) if pd.notna(row.get("apartments")) else 0
    dwellings = float(row.get("phase_units") or 0) if pd.notna(row.get("phase_units")) else 0
    apartment_share = apartments / dwellings if dwellings else 0.0
    if ahb:
        return "social_ahb"
    if TURNKEY_RE.search(text) and SOCIAL_RE.search(text):
        return "turnkey"
    if FORWARD_RE.search(text):
        return "forward_funded"
    if BTR_RE.search(text) and apartment_share >= 0.8:
        return "private_rental"
    if PARTV_RE.search(text) and SOCIAL_RE.search(text):
        return "part_v"
    if BTR_RE.search(text) or apartment_share >= 0.8:
        return "private_rental"
    if apartment_share > 0.5:
        return "mixed"
    if apartment_share == 0 and dwellings > 0:
        return "private_sale"
    return "unknown"


if __name__ == "__main__":
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    link_cols = [c for c in ["scheme_id", "bcms_event_id", "confidence_band"] if c in confirmed.columns]
    confirmed = confirmed[link_cols].drop_duplicates(subset=["scheme_id", "bcms_event_id"])
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    groups = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv")

    phase = confirmed.merge(bcms, on="bcms_event_id", how="inner")
    phase = phase[pd.to_datetime(phase["commencement_date_dt"], utc=True, errors="coerce").notna()].copy()
    phase = phase.rename(columns={
        "scheme_id": "development_id",
        "bcms_event_id": "phase_id",
        "planning_reference": "planning_reference",
        "commencement_date_dt": "commencement_date",
        "proposed_end_date_dt": "declared_end_date",
        "dwellings_phase": "phase_units",
        "dwellings_total": "permitted_units_bcms",
        "apartments_total": "apartments",
    })
    phase["houses"] = pd.to_numeric(phase["phase_units"], errors="coerce") - pd.to_numeric(phase["apartments"], errors="coerce").fillna(0)
    phase["phase_number"] = pd.to_numeric(phase["phase_number"], errors="coerce")
    phase["total_phases"] = pd.to_numeric(phase["total_phases"], errors="coerce")
    phase["commencement_date"] = pd.to_datetime(phase["commencement_date"], utc=True)
    phase["declared_end_date"] = pd.to_datetime(phase["declared_end_date"], utc=True, errors="coerce")

    register_map = register.set_index("case_key")[["PlanningAuthority", "NumResidentialUnits", "DevelopmentDescription", "GrantDate"]]
    phase = phase.merge(register_map.rename(columns={"NumResidentialUnits": "permitted_units_register",
                                                     "DevelopmentDescription": "planning_description",
                                                     "GrantDate": "permission_granted"}),
                        left_on="development_id", right_index=True, how="left")

    phase = phase.merge(applicants[["case_key", "entity_key", "applicant_name"]],
                        left_on="development_id", right_on="case_key", how="left").drop(columns=["case_key"])
    phase = phase.merge(groups[["case_key", "group_id"]], left_on="development_id", right_on="case_key",
                        how="left").drop(columns=["case_key"])

    phase["route"] = phase.apply(classify_route, axis=1)
    phase["duplicate_notice_flag"] = phase.duplicated(
        subset=["development_id", "phase_number", "street", "commencement_date"], keep=False).astype(int)

    # Aggregate notices that share a phase number (building-type splits) into
    # one phase row; notices without a phase number stay as their own phase.
    group_keys = ["development_id", "phase_number", "commencement_date", "street", "town"]
    agg = phase.groupby(group_keys, dropna=False).agg(
        houses=("houses", "sum"),
        apartments=("apartments", "sum"),
        phase_units=("phase_units", "sum"),
        notice_count=("phase_id", "size"),
        phase_id=("phase_id", "first"),
        declared_end_date=("declared_end_date", "min"),
        planning_reference=("planning_reference", "first"),
        total_phases=("total_phases", "first"),
        route=("route", "first"),
        eircode=("eircode", "first"),
        itm_easting=("itm_easting", "first"),
        itm_northing=("itm_northing", "first"),
        project_name=("project_name", "first"),
        description_raw=("description_raw", "first"),
        planning_description=("planning_description", "first"),
        permitted_units_register=("permitted_units_register", "first"),
        permission_granted=("permission_granted", "first"),
        developer_spv=("applicant_name", "first"),
        developer_spv_key=("entity_key", "first"),
        developer_group=("group_id", "first"),
    ).reset_index()

    columns = ["phase_id", "development_id", "planning_reference", "phase_number", "total_phases",
               "commencement_date", "declared_end_date", "permitted_units_register",
               "phase_units", "houses", "apartments", "route", "developer_spv", "developer_group",
               "town", "street", "eircode", "itm_easting", "itm_northing",
               "planning_description", "description_raw", "project_name", "notice_count"]
    out = agg.rename(columns={"applicant_name": "developer_spv", "group_id": "developer_group"})
    keep = [c for c in columns if c in out.columns]
    out = out[keep].copy()
    out_path = settings.SILVER_DIR / "phase_master.csv"
    out.to_csv(out_path, index=False)

    summary = {
        "phases": int(len(out)),
        "developments": int(out["development_id"].nunique()),
        "with_phase_number": int(out["phase_number"].notna().sum()),
        "route_distribution": out["route"].value_counts().to_dict(),
        "notice_count_total": int(out["notice_count"].sum()),
        "private_sale_housing_phases_10_150": int(((out["route"] == "private_sale") & out["houses"].between(10, 150)).sum()),
        "out": str(out_path),
    }
    (settings.SILVER_DIR / "phase_master_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
