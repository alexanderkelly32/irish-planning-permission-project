PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sites (
    site_id TEXT PRIMARY KEY,
    address TEXT NOT NULL,
    eircode TEXT,
    latitude REAL,
    longitude REAL,
    site_area_sqm REAL,
    planning_authority TEXT NOT NULL,
    zoning TEXT,
    current_use TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    application_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    application_reference TEXT,
    application_date TEXT,
    applicant TEXT,
    development_description TEXT,
    decision TEXT,
    decision_date TEXT,
    appeal_reference TEXT,
    appeal_outcome TEXT,
    parent_application_id TEXT REFERENCES applications(application_id),
    source_url TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schemes (
    scheme_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    application_id TEXT REFERENCES applications(application_id),
    version INTEGER NOT NULL,
    parent_scheme_id TEXT REFERENCES schemes(scheme_id),
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(site_id, version)
);
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    application_id TEXT REFERENCES applications(application_id),
    document_type TEXT NOT NULL,
    source TEXT,
    text TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id TEXT PRIMARY KEY,
    baseline_scheme_id TEXT NOT NULL REFERENCES schemes(scheme_id),
    scenario_scheme_id TEXT REFERENCES schemes(scheme_id),
    name TEXT NOT NULL,
    delta_json TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    support_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_runs (
    model_run_id TEXT PRIMARY KEY,
    scheme_id TEXT NOT NULL REFERENCES schemes(scheme_id),
    scenario_id TEXT REFERENCES scenarios(scenario_id),
    model_version TEXT NOT NULL,
    calibration_version TEXT,
    input_snapshot_json TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS model_runs_append_only_update
BEFORE UPDATE ON model_runs BEGIN SELECT RAISE(ABORT, 'model_runs are append-only'); END;
CREATE TRIGGER IF NOT EXISTS model_runs_append_only_delete
BEFORE DELETE ON model_runs BEGIN SELECT RAISE(ABORT, 'model_runs are append-only'); END;
