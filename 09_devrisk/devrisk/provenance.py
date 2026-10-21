"""Provenance: deterministic hashes, ingestion manifests, availability audit.

Every transformation records (brief section 8.3):
  - input file hashes
  - source URL and retrieval timestamp
  - transformation code/version
  - row counts and rejection counts
  - schema version
  - output hash or partition identifier
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from . import SCHEMA_MANIFEST

_HASH_CHUNK = 1 << 20


def sha256_file(path: Path | str) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def stable_row_hash(row: dict[str, Any]) -> str:
    """Deterministic hash of a record: canonical JSON, keys sorted."""
    canonical = json.dumps(row, sort_keys=True, default=_json_default, separators=(",", ":"))
    return sha256_text(canonical)


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serialisable: {type(value)}")


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def write_manifest(manifest: dict[str, Any], manifest_dir: Path, artifact_id: str) -> Path:
    manifest.setdefault("schema_version", SCHEMA_MANIFEST)
    manifest.setdefault("created_at", utc_now_iso())
    path = manifest_dir / f"{artifact_id}.manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_manifest(manifest_dir: Path, artifact_id: str) -> dict[str, Any]:
    path = manifest_dir / f"{artifact_id}.manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def build_manifest(
    artifact_id: str,
    source: dict[str, Any],
    inputs: list[dict[str, Any]],
    transformation: dict[str, Any],
    counts: dict[str, Any],
    outputs: list[dict[str, Any]],
    schema_columns: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_MANIFEST,
        "artifact_id": artifact_id,
        "source": source,
        "input_files": inputs,
        "transformation": transformation,
        "row_counts": counts,
        "outputs": outputs,
        "schema_columns": schema_columns,
        "created_at": utc_now_iso(),
    }


class AvailabilityError(ValueError):
    """Raised when a feature/label is available after its snapshot date."""


def enforce_available_at(feature_name: str, available_at: dt.datetime | str | None, snapshot_at: dt.datetime | str) -> None:
    """Fail loudly if a feature would leak future information into a snapshot."""
    if available_at is None:
        raise AvailabilityError(f"{feature_name}: missing available_at")
    avail = _to_dt(available_at)
    snap = _to_dt(snapshot_at)
    if avail > snap:
        raise AvailabilityError(
            f"{feature_name}: available_at {avail.isoformat()} > snapshot_at {snap.isoformat()}"
        )


def _to_dt(value: dt.datetime | str) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc)
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed
