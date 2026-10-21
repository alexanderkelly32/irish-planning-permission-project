"""v4 portfolio store: durable project memory for the Pre-Submission Review.

SQLite-backed store for scored proposals, scenario runs and evidence
snapshots. Every scoring run records model version, inputs and timestamp;
nothing is overwritten. Snapshots power the monitor/alerts view: rescoring
compares the live evidence context against what was true at save time.

App state lives in 06_copilot/current/portfolio.sqlite (not a model artifact).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "06_copilot" / "current" / "portfolio.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    authority TEXT NOT NULL,
    description TEXT NOT NULL,
    units REAL,
    site_area_sqm REAL,
    floor_area_sqm REAL,
    itm_easting REAL,
    itm_northing REAL,
    submission_year INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    model_version TEXT NOT NULL,
    refusal_probability REAL NOT NULL,
    raw_ranking_score REAL,
    risk_band TEXT,
    inputs_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    refusal_probability REAL NOT NULL,
    delta_pp REAL NOT NULL,
    verdict TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS score_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version TEXT NOT NULL,
    kind TEXT NOT NULL,
    proposal_json TEXT NOT NULL,
    refusal_probability REAL,
    meta_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    target TEXT NOT NULL,
    original_value TEXT NOT NULL,
    override_value TEXT NOT NULL,
    rationale TEXT NOT NULL,
    planner_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _proposal_row(proposal: dict) -> dict:
    return {
        "name": proposal.get("name") or "Untitled scheme",
        "authority": proposal["authority"],
        "description": proposal.get("description") or "",
        "units": proposal.get("units"),
        "site_area_sqm": proposal.get("site_area_sqm"),
        "floor_area_sqm": proposal.get("floor_area_sqm"),
        "itm_easting": proposal.get("itm_easting"),
        "itm_northing": proposal.get("itm_northing"),
        "submission_year": proposal.get("submission_year"),
    }


def _proposal_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "authority": row["authority"],
        "description": row["description"],
        "units": row["units"],
        "site_area_sqm": row["site_area_sqm"],
        "floor_area_sqm": row["floor_area_sqm"],
        "itm_easting": row["itm_easting"],
        "itm_northing": row["itm_northing"],
        "submission_year": row["submission_year"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_project(proposal: dict, score: dict | None, evidence: dict | None, project_id: int | None = None) -> int:
    """Insert or update a project and record a scoring run."""
    connection = _connect()
    try:
        now = _now()
        row = _proposal_row(proposal)
        if project_id is None:
            cursor = connection.execute(
                "INSERT INTO projects (name, authority, description, units, site_area_sqm, floor_area_sqm, itm_easting, itm_northing, submission_year, created_at, updated_at) "
                "VALUES (:name, :authority, :description, :units, :site_area_sqm, :floor_area_sqm, :itm_easting, :itm_northing, :submission_year, :created_at, :updated_at)",
                {**row, "created_at": now, "updated_at": now},
            )
            project_id = cursor.lastrowid
        else:
            connection.execute(
                "UPDATE projects SET name=:name, authority=:authority, description=:description, units=:units, site_area_sqm=:site_area_sqm, "
                "floor_area_sqm=:floor_area_sqm, itm_easting=:itm_easting, itm_northing=:itm_northing, submission_year=:submission_year, updated_at=:updated_at WHERE id=:id",
                {**row, "updated_at": now, "id": project_id},
            )
        if score is not None:
            connection.execute(
                "INSERT INTO runs (project_id, model_version, refusal_probability, raw_ranking_score, risk_band, inputs_json, evidence_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    score.get("model_version") or "unknown",
                    score["refusal_probability"],
                    score.get("raw_ranking_score"),
                    score.get("risk_band"),
                    json.dumps(score.get("inputs") or row),
                    json.dumps(evidence or {}),
                    now,
                ),
            )
        if evidence is not None:
            connection.execute(
                "INSERT INTO snapshots (project_id, evidence_json, created_at) VALUES (?, ?, ?)",
                (project_id, json.dumps(evidence), now),
            )
        connection.commit()
        return int(project_id)
    finally:
        connection.close()


def save_scenario(project_id: int, label: str, changes: dict, refusal_probability: float, delta_pp: float, verdict: str = "", run_id: int | None = None) -> int:
    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO scenarios (project_id, run_id, label, changes_json, refusal_probability, delta_pp, verdict, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, run_id, label, json.dumps(changes), refusal_probability, delta_pp, verdict, _now()),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def save_snapshot(project_id: int, evidence: dict) -> int:
    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO snapshots (project_id, evidence_json, created_at) VALUES (?, ?, ?)",
            (project_id, json.dumps(evidence), _now()),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def list_projects() -> list[dict]:
    connection = _connect()
    try:
        rows = connection.execute(
            "SELECT p.*, (SELECT refusal_probability FROM runs r WHERE r.project_id = p.id ORDER BY r.created_at DESC, r.id DESC LIMIT 1) AS latest_risk, "
            "(SELECT risk_band FROM runs r WHERE r.project_id = p.id ORDER BY r.created_at DESC, r.id DESC LIMIT 1) AS latest_band "
            "FROM projects p ORDER BY p.updated_at DESC"
        ).fetchall()
        return [_proposal_from_row(row) | {"latest_risk": row["latest_risk"], "latest_band": row["latest_band"]} for row in rows]
    finally:
        connection.close()


def get_project(project_id: int) -> dict | None:
    connection = _connect()
    try:
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _proposal_from_row(row) if row else None
    finally:
        connection.close()


def latest_run(project_id: int) -> dict | None:
    connection = _connect()
    try:
        row = connection.execute("SELECT * FROM runs WHERE project_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", (project_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "model_version": row["model_version"],
            "refusal_probability": row["refusal_probability"],
            "raw_ranking_score": row["raw_ranking_score"],
            "risk_band": row["risk_band"],
            "inputs_json": row["inputs_json"],
            "evidence_json": row["evidence_json"],
            "created_at": row["created_at"],
        }
    finally:
        connection.close()


def latest_snapshot(project_id: int) -> dict | None:
    connection = _connect()
    try:
        row = connection.execute("SELECT * FROM snapshots WHERE project_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", (project_id,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "project_id": row["project_id"], "evidence_json": row["evidence_json"], "created_at": row["created_at"]}
    finally:
        connection.close()


def list_scenarios(project_id: int) -> list[dict]:
    connection = _connect()
    try:
        rows = connection.execute(
            "SELECT * FROM scenarios WHERE project_id = ? ORDER BY created_at DESC, id DESC", (project_id,)
        ).fetchall()
        return [
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "run_id": row["run_id"],
                "label": row["label"],
                "changes": json.loads(row["changes_json"]),
                "refusal_probability": row["refusal_probability"],
                "delta_pp": row["delta_pp"],
                "verdict": row["verdict"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    finally:
        connection.close()


def delete_project(project_id: int) -> None:
    connection = _connect()
    try:
        connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        connection.commit()
    finally:
        connection.close()


def record_event(model_version: str, kind: str, proposal: dict, refusal_probability: float | None, meta: dict | None = None) -> int:
    """Append-only log of every scoring action (model version, inputs, timestamp)."""
    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO score_events (model_version, kind, proposal_json, refusal_probability, meta_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (model_version, kind, json.dumps(proposal), refusal_probability, json.dumps(meta or {}), _now()),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def save_override(project_id: int, run_id: int | None, target: str, original_value: str,
                  override_value: str, rationale: str, planner_name: str) -> int:
    """Record a planner override - the audit trail never overwrites the model value."""
    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO overrides (project_id, run_id, target, original_value, override_value, rationale, planner_name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, run_id, target, original_value, override_value, rationale, planner_name or "Unnamed planner", _now()),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def list_overrides(project_id: int) -> list[dict]:
    connection = _connect()
    try:
        rows = connection.execute(
            "SELECT * FROM overrides WHERE project_id = ? ORDER BY created_at DESC, id DESC", (project_id,)
        ).fetchall()
        return [
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "run_id": row["run_id"],
                "target": row["target"],
                "original_value": row["original_value"],
                "override_value": row["override_value"],
                "rationale": row["rationale"],
                "planner_name": row["planner_name"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    finally:
        connection.close()


def delete_override(override_id: int) -> None:
    connection = _connect()
    try:
        connection.execute("DELETE FROM overrides WHERE id = ?", (override_id,))
        connection.commit()
    finally:
        connection.close()


def count_runs() -> int:
    """Number of append-only scoring events logged (every scored action)."""
    connection = _connect()
    try:
        return int(connection.execute("SELECT COUNT(*) FROM score_events").fetchone()[0])
    finally:
        connection.close()
