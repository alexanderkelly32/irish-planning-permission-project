"""BCMS ingestion: download the NBCO commencements/completions CSV -> raw -> bronze -> silver.

Raw layer: immutable download with retrieval metadata (json sidecar) and a
content hash. Bronze: parsed, minimally normalised records with stable row
hashes and provenance manifest. Silver: canonical bcms_events table with
normalised address, typed dates, dwelling counts, planning reference, and
WGS84 -> ITM (EPSG:4326 -> EPSG:2157) conversion for spatial matching.

Commands refuse to overwrite an existing raw snapshot unless `--force`
(new version) is given (brief section 19).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from pyproj import Transformer

from .. import settings
from ..provenance import build_manifest, sha256_file, stable_row_hash, utc_now_iso, write_manifest

RAW_NAME = "bcms_buildingscnscccs.csv"
BRONZE_NAME = "bcms_bronze.parquet"
SILVER_NAME = "bcms_events_silver.parquet"
ARTIFACT_ID = "bcms_snapshot"

# Actual NBCO CSV columns observed 2026-09-27 (verbatim; do not rename without
# updating the manifest's schema_columns).
KEEP_COLUMNS = [
    "IDs",
    "CN_Proposed_use_of_building",
    "CN_Sub_Group",
    "CN_Number_of_Buildings_of_this_building_type",
    "CN_Type_of_Construction",
    "CN_Main_Method_of_Construction",
    "CN_Main_Construction_Material",
    "CN_Height",
    "CN_FSC_Number",
    "CN_DAC_Number",
    "CN_Material_Alteration_Works",
    "CN_Consequence_Class",
    "CN_Existing_use_of_Building",
    "CN_Type_of_Building_or_Works",
    "CN_Building_Name",
    "CN_Total_floor_area_of_building",
    "CN_Proposed_use_of_building_desc",
    "CN_Number_stories_below_ground",
    "CN_Number_stories_above_ground",
    "CN_Protected_structure",
    "CN_Number_room",
    "CN_Number_bedrooms",
    "CN_Number_wcs",
    "CN_Total_apartments",
    "CN_Dwelling_House_Type",
    "CN_Approved_housing_body",
    "CN_Project_Name",
    "CN_Description_proposed_development",
    "CN_Project_type",
    "CN_Activity_Type",
    "CN_Planning_Permission_Number",
    "CN_Date_Granted",
    "CN_Date_Expiry",
    "CN_Project_Status",
    "CN_Validation_Status",
    "CN_Planning_Permission_Required",
    "CN_Valid_Completion_Certificate",
    "CN_Date_Submitted_or_Received",
    "CN_LAT",
    "CN_LNG",
    "CN_Number",
    "CN_Commencement_Date",
    "CN_Units_for_phase",
    "CN_Phase_for_this_Notice",
    "CN_Proposed_end_date",
    "CN_Street",
    "CN_Town",
    "CN_Eircode",
    "CN_County",
    "CN_Total_Number_of_Dwelling_Units",
    "CN_Validation_Date",
    "CN_Total_Number_of_Phases",
    "CN_Number_of_New_Buildings",
    "CN_Total_Number_Multiple_Unit_Dwellings",
    "CN_Total_Number_of_Buildings",
    "CN_Not_Commenced",
    "CN_S11_Request",
    "CN_Fee_Waiver_Request_Accepted",
    "CCC_Description",
    "CCC_Number",
    "CCC_Date_Validated",
    "CCC_Type_of_Completion_Certificate",
    "CCC_Pre_Notification",
    "CCC_Pre_Notification_Info",
    "CCC_Due_date",
    "CCC_FSC",
    "CCC_DAC",
    "CCC_Units_Completed",
    "LocalAuthority",
    "Building_Number",
    "Submission_Number",
]

SILVER_COLUMNS = [
    "bcms_event_id",
    "source_row_id",
    "event_type",
    "authority",
    "county",
    "address_full",
    "eircode",
    "town",
    "street",
    "dwellings_total",
    "dwellings_phase",
    "apartments_total",
    "planning_reference",
    "planning_permission_required",
    "commencement_date_dt",
    "received_date_dt",
    "validation_date_dt",
    "grant_date_dt",
    "proposed_end_date_dt",
    "completion_certificate_date_dt",
    "completion_units",
    "project_name",
    "description_raw",
    "not_commenced",
    "valid_completion_certificate",
    "lat",
    "lng",
    "itm_easting",
    "itm_northing",
    "protected_structure",
    "approved_housing_body",
    # Phase-level fields (added 2026-09-30 - additive extension, v2)
    "phase_number",
    "total_phases",
    "s11_request",
    "new_buildings_count",
    "multiple_unit_dwellings",
    "total_buildings",
    "ccc_type",
    "ccc_pre_notification",
    "ccc_fsc",
    "ccc_dac",
    "project_status",
    "validation_status",
    "building_name",
    "height",
    "project_type",
    "activity_type",
    "fsc_number",
    "dac_number",
    "construction_method",
    "type_of_building_or_works",
    "date_expiry_dt",
    "planned_duration_days",
    "row_hash",
]

_WGS84_TO_ITM = Transformer.from_crs("EPSG:4326", "EPSG:2157", always_xy=True)


def download(url: str, raw_dir: Path, force: bool = False, timeout: int = 600) -> dict[str, Any]:
    """Download the BCMS CSV to the raw layer. Refuses to overwrite without force."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / RAW_NAME
    sidecar = raw_dir / f"{RAW_NAME}.meta.json"
    if target.exists() and not force:
        return {"status": "exists", "path": str(target), "note": "raw snapshot already present; pass force=True to replace"}
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    content = response.content
    if force and target.exists():
        target.unlink()
    target.write_bytes(content)
    meta = {
        "retrieved_at": utc_now_iso(),
        "source_url": url,
        "http_status": int(response.status_code),
        "content_type": response.headers.get("content-type"),
        "sha256": sha256_file(target),
        "size_bytes": len(content),
    }
    sidecar.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    return {"status": "downloaded", "path": str(target), "meta": meta}


def build_bronze(raw_path: Path, bronze_dir: Path, manifest_dir: Path) -> dict[str, Any]:
    raw_path = Path(raw_path)
    frame = pd.read_csv(raw_path, low_memory=False)
    input_rows = len(frame)
    keep = [column for column in KEEP_COLUMNS if column in frame.columns]
    missing = [column for column in KEEP_COLUMNS if column not in frame.columns]
    bronze = frame[keep].copy()
    bronze["row_hash"] = [stable_row_hash(row) for row in bronze[keep].to_dict(orient="records")]

    bronze_path = bronze_dir / BRONZE_NAME
    bronze_path.parent.mkdir(parents=True, exist_ok=True)
    bronze.to_parquet(bronze_path, index=False)

    manifest = build_manifest(
        artifact_id=ARTIFACT_ID,
        source={
            "kind": "url",
            "url": settings.BCMS_CSV_URL,
            "dataset": "BCMS/NBCO commencements and completions",
            "access_notes": "Technical accessibility is not automated commercial reuse rights; terms to be reviewed before scaling.",
        },
        inputs=[{"path": str(raw_path), "sha256": sha256_file(raw_path), "size_bytes": raw_path.stat().st_size}],
        transformation={"code": "devrisk.ingestion.bcms.build_bronze", "code_version": "v1", "params": {"keep_columns": keep}},
        counts={"input_rows": input_rows, "output_rows": int(len(bronze)), "rejected_rows": 0, "source_columns_missing": missing},
        outputs=[{"path": str(bronze_path), "sha256": sha256_file(bronze_path), "rows": int(len(bronze))}],
        schema_columns=list(bronze.columns),
    )
    write_manifest(manifest, manifest_dir, ARTIFACT_ID)
    return {"bronze_path": bronze_path, "rows": len(bronze), "columns": list(bronze.columns), "manifest": manifest}


def _to_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _build_address(row: pd.Series) -> str:
    # CN_Number holds the notice identifier (e.g. CN0145582CW), never a house
    # number; it is excluded from the address.
    parts = [str(row.get("CN_Street") or ""), str(row.get("CN_Town") or "")]
    return ", ".join(part for part in parts if part.strip() and part.strip().lower() != "nan").strip()


def build_silver(bronze: pd.DataFrame, silver_dir: Path, manifest_dir: Path) -> dict[str, Any]:
    """Canonical bcms_events table for matching and survival labels."""
    frame = bronze.copy()
    lat = _to_num(frame.get("CN_LAT"))
    lng = _to_num(frame.get("CN_LNG"))
    valid_geo = lat.notna() & lng.notna() & lat.abs().le(90) & lng.abs().le(180)
    itm_easting = pd.Series(np.nan, index=frame.index)
    itm_northing = pd.Series(np.nan, index=frame.index)
    if valid_geo.any():
        easting, northing = _WGS84_TO_ITM.transform(lng[valid_geo].to_numpy(), lat[valid_geo].to_numpy())
        itm_easting.loc[valid_geo] = easting
        itm_northing.loc[valid_geo] = northing

    rows = frame[["row_hash"]].copy()
    rows["source_row_id"] = frame["IDs"].astype(str) + "__" + frame["row_hash"].str.slice(0, 12)
    rows["bcms_event_id"] = rows["source_row_id"]
    has_ccc = frame.get("CCC_Number").notna() & frame["CCC_Number"].astype(str).str.strip().ne("")
    rows["event_type"] = np.where(has_ccc, "commencement_with_completion_record", "commencement_notice")
    rows["authority"] = frame.get("LocalAuthority").fillna("")
    rows["county"] = frame.get("CN_County").fillna("").astype(str)
    rows["address_full"] = frame.apply(_build_address, axis=1)
    rows["eircode"] = frame.get("CN_Eircode").fillna("").astype(str)
    rows["town"] = frame.get("CN_Town").fillna("").astype(str)
    rows["street"] = frame.get("CN_Street").fillna("").astype(str)
    rows["dwellings_total"] = _to_num(frame.get("CN_Total_Number_of_Dwelling_Units"))
    rows["dwellings_phase"] = _to_num(frame.get("CN_Units_for_phase"))
    rows["apartments_total"] = _to_num(frame.get("CN_Total_apartments"))
    rows["planning_reference"] = frame.get("CN_Planning_Permission_Number").fillna("").astype(str)
    rows["planning_permission_required"] = frame.get("CN_Planning_Permission_Required").fillna("").astype(str)
    rows["commencement_date_dt"] = _to_dt(frame.get("CN_Commencement_Date"))
    rows["received_date_dt"] = _to_dt(frame.get("CN_Date_Submitted_or_Received"))
    rows["validation_date_dt"] = _to_dt(frame.get("CN_Validation_Date"))
    rows["grant_date_dt"] = _to_dt(frame.get("CN_Date_Granted"))
    rows["proposed_end_date_dt"] = _to_dt(frame.get("CN_Proposed_end_date"))
    rows["completion_certificate_date_dt"] = _to_dt(frame.get("CCC_Date_Validated"))
    rows["completion_units"] = _to_num(frame.get("CCC_Units_Completed"))
    rows["project_name"] = frame.get("CN_Project_Name").fillna("")
    rows["description_raw"] = frame.get("CN_Description_proposed_development").fillna("")
    rows["not_commenced"] = frame.get("CN_Not_Commenced").fillna("").astype(str)
    rows["valid_completion_certificate"] = frame.get("CN_Valid_Completion_Certificate").fillna("").astype(str)
    rows["lat"] = lat
    rows["lng"] = lng
    rows["itm_easting"] = itm_easting.round(1)
    rows["itm_northing"] = itm_northing.round(1)
    rows["protected_structure"] = frame.get("CN_Protected_structure").fillna("").astype(str)
    rows["approved_housing_body"] = frame.get("CN_Approved_housing_body").fillna("").astype(str)

    # Phase-level fields (v2 extension). Missing source columns become
    # empty defaults so the silver schema is stable across snapshots.
    rows["phase_number"] = _to_num(frame.get("CN_Phase_for_this_Notice", pd.Series(dtype=float)))
    rows["total_phases"] = _to_num(frame.get("CN_Total_Number_of_Phases", pd.Series(dtype=float)))
    rows["s11_request"] = frame.get("CN_S11_Request", pd.Series(dtype=str)).fillna("").astype(str)
    rows["new_buildings_count"] = _to_num(frame.get("CN_Number_of_New_Buildings", pd.Series(dtype=float)))
    rows["multiple_unit_dwellings"] = _to_num(frame.get("CN_Total_Number_Multiple_Unit_Dwellings", pd.Series(dtype=float)))
    rows["total_buildings"] = _to_num(frame.get("CN_Total_Number_of_Buildings", pd.Series(dtype=float)))
    rows["ccc_type"] = frame.get("CCC_Type_of_Completion_Certificate", pd.Series(dtype=str)).fillna("").astype(str)
    rows["ccc_pre_notification"] = frame.get("CCC_Pre_Notification", pd.Series(dtype=str)).fillna("").astype(str)
    rows["ccc_fsc"] = frame.get("CCC_FSC", pd.Series(dtype=str)).fillna("").astype(str)
    rows["ccc_dac"] = frame.get("CCC_DAC", pd.Series(dtype=str)).fillna("").astype(str)
    rows["project_status"] = frame.get("CN_Project_Status", pd.Series(dtype=str)).fillna("").astype(str)
    rows["validation_status"] = frame.get("CN_Validation_Status", pd.Series(dtype=str)).fillna("").astype(str)
    rows["building_name"] = frame.get("CN_Building_Name", pd.Series(dtype=str)).fillna("").astype(str)
    rows["height"] = _to_num(frame.get("CN_Height", pd.Series(dtype=float)))
    rows["project_type"] = frame.get("CN_Project_type", pd.Series(dtype=str)).fillna("").astype(str)
    rows["activity_type"] = frame.get("CN_Activity_Type", pd.Series(dtype=str)).fillna("").astype(str)
    rows["fsc_number"] = frame.get("CN_FSC_Number", pd.Series(dtype=str)).fillna("").astype(str)
    rows["dac_number"] = frame.get("CN_DAC_Number", pd.Series(dtype=str)).fillna("").astype(str)
    rows["construction_method"] = frame.get("CN_Main_Method_of_Construction", pd.Series(dtype=str)).fillna("").astype(str)
    rows["type_of_building_or_works"] = frame.get("CN_Type_of_Building_or_Works", pd.Series(dtype=str)).fillna("").astype(str)
    rows["date_expiry_dt"] = _to_dt(frame.get("CN_Date_Expiry", pd.Series(dtype=object)))
    planned_duration = rows["proposed_end_date_dt"] - rows["commencement_date_dt"]
    rows["planned_duration_days"] = _to_num(planned_duration.dt.days)

    silver = rows[SILVER_COLUMNS].copy()
    silver_path = silver_dir / SILVER_NAME
    silver_path.parent.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(silver_path, index=False)

    manifest = build_manifest(
        artifact_id="bcms_events_silver",
        source={"kind": "derived", "from_artifact": ARTIFACT_ID, "note": "canonical bcms_events table for matching/survival labels"},
        inputs=[],
        transformation={"code": "devrisk.ingestion.bcms.build_silver", "code_version": "v1", "params": {"crs": "EPSG:4326 -> EPSG:2157"}},
        counts={
            "input_rows": int(len(frame)),
            "output_rows": int(len(silver)),
            "rejected_rows": 0,
            "rows_with_geo": int(valid_geo.sum()),
            "rows_with_planning_reference": int(rows["planning_reference"].str.strip().ne("").sum()),
            "rows_with_completion_record": int(has_ccc.sum()),
        },
        outputs=[{"path": str(silver_path), "sha256": sha256_file(silver_path), "rows": int(len(silver))}],
        schema_columns=SILVER_COLUMNS,
    )
    write_manifest(manifest, manifest_dir, "bcms_events_silver")
    return {"silver_path": silver_path, "rows": len(silver), "manifest": manifest}


def run(raw_dir: Path, bronze_dir: Path, manifest_dir: Path, force: bool = False) -> dict[str, Any]:
    result = download(settings.BCMS_CSV_URL, raw_dir, force=force)
    if result["status"] not in {"downloaded"} and not (raw_dir / RAW_NAME).exists():
        raise RuntimeError("BCMS download unavailable and no prior snapshot exists")
    raw_path = Path(result["path"])
    bronze = build_bronze(raw_path, bronze_dir, manifest_dir)
    silver = build_silver(pd.read_parquet(bronze["bronze_path"]), settings.SILVER_DIR, manifest_dir)
    return {"download": result, "bronze": bronze, "silver": silver}


if __name__ == "__main__":
    print(run(settings.RAW_DIR, settings.BRONZE_DIR, settings.MANIFEST_DIR))
