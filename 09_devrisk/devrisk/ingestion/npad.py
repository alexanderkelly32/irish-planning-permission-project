"""NPAD register ingestion: canonical register parquet -> bronze layer.

The repository already holds the NPAD-derived national register
(old_original_attempt/.../irish_planning_dataset_clean_model.parquet). This
module re-hashes it, derives a bronze frame with stable per-row hashes and
provenance, and writes a manifest. The source parquet is treated as immutable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .. import settings
from ..provenance import build_manifest, sha256_file, stable_row_hash, write_manifest

BRONZE_COLUMNS = [
    "case_key",
    "PlanningAuthority",
    "ApplicationNumber",
    "DevelopmentDescription",
    "DevelopmentAddress",
    "DevelopmentPostcode",
    "ITMEasting",
    "ITMNorthing",
    "ApplicationStatus",
    "ApplicationType",
    "ApplicantForename",
    "ApplicantSurname",
    "Decision",
    "LandUseCode",
    "AreaofSite",
    "NumResidentialUnits",
    "OneOffHouse",
    "FloorArea",
    "ReceivedDate",
    "WithdrawnDate",
    "DecisionDate",
    "DecisionDueDate",
    "GrantDate",
    "ExpiryDate",
    "AppealRefNumber",
    "AppealStatus",
    "AppealDecision",
    "AppealDecisionDate",
    "AppealSubmittedDate",
    "FIRequestDate",
    "FIRecDate",
    "LinkAppDetails",
    "SiteId",
    "ETL_DATE",
    "row_hash",
]


def case_key_for(authority: Any, application_number: Any) -> str:
    """Canonical join key: authority + application number (repo convention)."""
    return f"{str(authority or '').strip()}__{str(application_number or '').strip()}"


def build_bronze(source_path: Path, out_dir: Path, manifest_dir: Path) -> dict[str, Any]:
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"register not found: {source_path}")
    frame = pd.read_parquet(source_path)
    frame = frame.copy()
    frame["case_key"] = [case_key_for(a, n) for a, n in zip(frame["PlanningAuthority"], frame["ApplicationNumber"])]
    frame["ETL_DATE"] = pd.to_datetime(frame.get("ETL_DATE"), utc=True, errors="coerce")
    keep = [column for column in BRONZE_COLUMNS if column in frame.columns and column != "row_hash"]
    bronze = frame[keep].copy()
    bronze["row_hash"] = [stable_row_hash(row) for row in bronze[keep].to_dict(orient="records")]

    bronze_path = out_dir / "npad_register_bronze.parquet"
    bronze_path.parent.mkdir(parents=True, exist_ok=True)
    bronze.to_parquet(bronze_path, index=False)

    manifest = build_manifest(
        artifact_id="npad_register_bronze",
        source={
            "kind": "local_repo_parquet",
            "path": str(source_path),
            "description": "NPAD-derived national planning register held by the repository; treated as immutable input.",
            "access_notes": "Internal analysis only; reuse position to be confirmed before redistribution.",
        },
        inputs=[{"path": str(source_path), "sha256": sha256_file(source_path), "size_bytes": source_path.stat().st_size}],
        transformation={"code": "devrisk.ingestion.npad.build_bronze", "code_version": "v1", "params": {"columns": keep}},
        counts={
            "input_rows": int(len(frame)),
            "output_rows": int(len(bronze)),
            "rejected_rows": 0,
            "duplicate_case_keys": int(bronze["case_key"].duplicated().sum()),
        },
        outputs=[{"path": str(bronze_path), "sha256": sha256_file(bronze_path), "rows": int(len(bronze))}],
        schema_columns=keep,
    )
    write_manifest(manifest, manifest_dir, "npad_register_bronze")
    return {"bronze_path": bronze_path, "rows": len(bronze), "manifest": manifest}


if __name__ == "__main__":
    print(build_bronze(settings.REGISTER_FULL_PARQUET, settings.BRONZE_DIR, settings.MANIFEST_DIR))
