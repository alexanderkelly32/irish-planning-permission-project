"""Small SQLite repository for the V1 planning domain."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = Path(__file__).resolve().parent / "migrations" / "001_canonical_domain.sql"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class PlanningRepository:
    def __init__(self, db_path: str | Path | None = None):
        self.path = Path(db_path) if db_path else ROOT / "06_copilot" / "current" / "planning.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(MIGRATION.read_text(encoding="utf-8"))
        scenario_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(scenarios)")}
        if "scenario_scheme_id" not in scenario_columns:
            self.connection.execute("ALTER TABLE scenarios ADD COLUMN scenario_scheme_id TEXT REFERENCES schemes(scheme_id)")
        document_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(documents)")}
        for column, ddl in {
            "page_range": "ALTER TABLE documents ADD COLUMN page_range TEXT",
            "chunk_index": "ALTER TABLE documents ADD COLUMN chunk_index INTEGER",
            "extraction_model_version": "ALTER TABLE documents ADD COLUMN extraction_model_version TEXT",
            "confidence": "ALTER TABLE documents ADD COLUMN confidence REAL",
        }.items():
            if column not in document_columns:
                self.connection.execute(ddl)
        self.connection.commit()

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def table_names(self) -> set[str]:
        with self._lock:
            rows = self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            return {row[0] for row in rows}

    def create_site(self, site: dict[str, Any]) -> str:
        site_id = _id("site")
        fields = ("address", "eircode", "latitude", "longitude", "site_area_sqm", "planning_authority", "zoning", "current_use")
        values = [site.get(field) for field in fields]
        with self._lock:
            self.connection.execute(
                "INSERT INTO sites (site_id,address,eircode,latitude,longitude,site_area_sqm,planning_authority,zoning,current_use,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (site_id, *values, _now()),
            )
            self.connection.commit()
        return site_id

    def create_scheme(self, site_id: str, snapshot: dict[str, Any], version: int = 1, parent_scheme_id: str | None = None) -> str:
        scheme_id = _id("scheme")
        with self._lock:
            self.connection.execute(
                "INSERT INTO schemes (scheme_id,site_id,version,parent_scheme_id,snapshot_json,created_at) VALUES (?,?,?,?,?,?)",
                (scheme_id, site_id, version, parent_scheme_id, _json(snapshot), _now()),
            )
            self.connection.commit()
        return scheme_id

    def next_scheme_version(self, site_id: str) -> int:
        with self._lock:
            row = self.connection.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM schemes WHERE site_id=?", (site_id,)).fetchone()
            return int(row[0])

    def create_scenario(self, baseline_scheme_id: str, scenario_scheme_id: str, name: str, delta: dict[str, Any], snapshot: dict[str, Any], support: dict[str, Any] | None = None) -> str:
        scenario_id = _id("scenario")
        with self._lock:
            self.connection.execute(
                "INSERT INTO scenarios (scenario_id,baseline_scheme_id,scenario_scheme_id,name,delta_json,snapshot_json,support_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (scenario_id, baseline_scheme_id, scenario_scheme_id, name, _json(delta), _json(snapshot), _json(support or {}), _now()),
            )
            self.connection.commit()
        return scenario_id

    def record_model_run(self, scheme_id: str, scenario_id: str | None, model_version: str, input_snapshot: dict[str, Any], output: dict[str, Any], calibration_version: str | None = None) -> str:
        run_id = _id("run")
        with self._lock:
            self.connection.execute(
                "INSERT INTO model_runs (model_run_id,scheme_id,scenario_id,model_version,calibration_version,input_snapshot_json,output_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, scheme_id, scenario_id, model_version, calibration_version, _json(input_snapshot), _json(output), _now()),
            )
            self.connection.commit()
        return run_id

    def get_scheme(self, scheme_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.connection.execute("SELECT * FROM schemes WHERE scheme_id=?", (scheme_id,)).fetchone()

    def get_model_run(self, run_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.connection.execute("SELECT * FROM model_runs WHERE model_run_id=?", (run_id,)).fetchone()

    def record_document(
        self,
        application_id: str | None,
        document_type: str,
        source: str | None,
        text: str,
        page_range: str | None = None,
        chunk_index: int | None = None,
        extraction_model_version: str | None = None,
        confidence: float | None = None,
    ) -> str:
        """Store a document with provenance; never mutates an existing record."""
        document_id = _id("doc")
        with self._lock:
            self.connection.execute(
                "INSERT INTO documents (document_id,application_id,document_type,source,text,page_range,chunk_index,extraction_model_version,confidence,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    document_id, application_id, document_type, source, text,
                    page_range, chunk_index, extraction_model_version, confidence, _now(),
                ),
            )
            self.connection.commit()
        return document_id

    def get_document(self, document_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.connection.execute("SELECT * FROM documents WHERE document_id=?", (document_id,)).fetchone()

    def list_documents_for_application(self, application_id: str) -> list[sqlite3.Row]:
        with self._lock:
            return self.connection.execute(
                "SELECT * FROM documents WHERE application_id=? ORDER BY created_at",
                (application_id,),
            ).fetchall()
