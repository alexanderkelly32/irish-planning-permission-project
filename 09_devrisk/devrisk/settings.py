"""Central path/settings for devrisk. Single source of truth for layer layout."""
from __future__ import annotations

from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]  # 09_devrisk/
ROOT = WORKSPACE.parent  # repository root
CONFIG_DIR = WORKSPACE / "configs"
DATA_DIR = WORKSPACE / "data"
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
MANIFEST_DIR = DATA_DIR / "manifests"

SOURCES_YAML = CONFIG_DIR / "sources.yaml"
PILOT_GATES_YAML = CONFIG_DIR / "rules" / "pilot_gates.yaml"
FRICTION_RULES_YAML = CONFIG_DIR / "rules" / "friction_v1.yaml"
PILOT_COHORT_YAML = CONFIG_DIR / "cohorts" / "pilot_100.yaml"

# Existing repository assets this workspace reads (never writes).
REGISTER_FULL_PARQUET = ROOT / "old_original_attempt" / "first_attempt_messy" / "irish_planning_dataset_clean_model.parquet"
REGISTER_2026_PARQUET = ROOT / "00_base" / "source_data" / "register_2026.parquet"
FROZEN_MODEL_JOBLIB = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"
FROZEN_MANIFEST_JSON = ROOT / "05_policy" / "current" / "model_v4" / "manifest.json"
PLANNING_SCRIPTS_DIR = ROOT / "05_policy" / "scripts"

# External source URLs (mirrors configs/sources.yaml; used by ingestion code).
BCMS_CSV_URL = (
    "https://data.nbco.gov.ie/dataset/2704a333-874d-46f5-b3bc-3673766bf816/"
    "resource/0774e781-7af8-46da-b623-872e74cf541e/download/buildingscnscccs.csv"
)
