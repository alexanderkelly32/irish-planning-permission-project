#!/usr/bin/env python3
"""National flood feature run: all 219k cases against local OPW flood data."""
import sys
from pathlib import Path

SCRIPT = Path(r"01_flood\scripts\addition_of_flooding_data.py")
sys.path.insert(0, str(SCRIPT.parent))

import addition_of_flooding_data as flood  # noqa: E402

flood.BASE_DIR = Path(r"old_original_attempt\flood_data")
flood.INPUT_CSV = Path(r"07_context\raw\all_cases_flood_input.csv")
flood.INPUT_WKB_EPSG = 2157
flood.OUTPUT_SUFFIX = "_national_flood"

print("base_dir:", flood.BASE_DIR, flush=True)
print("input:", flood.INPUT_CSV, flush=True)

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("flood_run", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.BASE_DIR = flood.BASE_DIR
module.INPUT_CSV = flood.INPUT_CSV
module.INPUT_WKB_EPSG = 2157
module.OUTPUT_SUFFIX = "_national_flood"
module.main()
print("FLOOD RUN COMPLETE", flush=True)
