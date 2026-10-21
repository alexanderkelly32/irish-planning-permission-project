"""Runner: build the pilot cohort pool + stratified 100 proposal."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import cohort, settings  # noqa: E402

if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    pool = cohort.build_candidate_pool(register)
    annotated = cohort.annotate_pool(pool)
    annotated.to_parquet(settings.SILVER_DIR / "pilot_candidates_pool.parquet", index=False)
    pilot = cohort.stratify_pilot(annotated, target=100)
    pilot.to_parquet(settings.SILVER_DIR / "pilot_candidates_100.parquet", index=False)
    cohort.export_audit_workbook(pilot, settings.SILVER_DIR / "pilot_100_audit.csv")
    print(json.dumps(cohort.cohort_summary(annotated), indent=2, default=str))
