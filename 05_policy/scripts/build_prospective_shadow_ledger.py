#!/usr/bin/env python3
"""Register frozen Model v3 predictions for post-2025 submissions in a shadow ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
LEDGER_PATH = OUTPUT_DIR / "prospective_shadow_ledger.csv"
MODEL_PATH = OUTPUT_DIR / "model_v3" / "national_residential_v3_comparables.joblib"
DEFAULT_INPUT = ROOT / "old_original_attempt" / "first_attempt_messy" / "irish_planning_dataset_clean_model.parquet"

sys.path.insert(0, str(ROOT / "06_copilot" / "scripts"))
sys.path.insert(0, str(ROOT / "02_development" / "scripts"))
from precedent_copilot_logic import score_submission_risk  # noqa: E402
from revision_pairs import is_administrative_event_reference  # noqa: E402
from full_revision_linkage import select_residential_scope  # noqa: E402

from prospective_shadow_ledger import append_ledger, build_ledger_rows, ledger_summary, outcome_readout  # noqa: E402

INPUT_COLUMNS = [
    "PlanningAuthority", "ApplicationNumber", "DevelopmentDescription", "DevelopmentAddress",
    "DevelopmentPostcode", "ITMEasting", "ITMNorthing", "ApplicationType", "Decision",
    "ReceivedDate", "DecisionDate", "SiteId", "ApplicantForename", "ApplicantSurname",
    "NumResidentialUnits", "OneOffHouse", "LinkAppDetails",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument("--received-on-or-after", type=str, default="2026-01-01")
    args = parser.parse_args()

    bundle = joblib.load(MODEL_PATH)
    raw = pd.read_parquet(args.input, columns=[c for c in INPUT_COLUMNS if c != "DecisionDate"] or INPUT_COLUMNS)
    raw["received_dt"] = pd.to_datetime(raw["ReceivedDate"], utc=True, errors="coerce")
    recent = raw[raw["received_dt"] >= args.received_on_or_after].copy()
    scoped = select_residential_scope(recent)
    scoped = scoped[~scoped["ApplicationNumber"].fillna("").astype(str).map(is_administrative_event_reference)]
    new_rows = build_ledger_rows(scoped, lambda query: score_submission_risk(query, bundle))

    existing = pd.read_csv(args.ledger, low_memory=False) if args.ledger.exists() else None
    ledger = append_ledger(existing, new_rows)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(args.ledger, index=False)

    summary = ledger_summary(
        ledger,
        model_sha256=hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
    )
    summary["source"] = str(args.input.resolve())
    summary["received_on_or_after"] = args.received_on_or_after
    summary["scoped_source_rows"] = int(len(scoped))
    summary["registered_this_run"] = int(len(new_rows))
    summary["outcome_readout"] = outcome_readout(ledger)
    (OUTPUT_DIR / "prospective_shadow_ledger_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
