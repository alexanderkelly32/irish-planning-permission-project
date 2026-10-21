#!/usr/bin/env python3
"""Process ONE flood shard. Usage: python run_one_flood_shard.py <shard_csv>"""
import importlib.util
import sys
from pathlib import Path

shard_path = Path(sys.argv[1])
SCRIPT = Path(r"01_flood\scripts\addition_of_flooding_data.py")

spec = importlib.util.spec_from_file_location("flood_shard", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.BASE_DIR = Path(r"old_original_attempt\flood_data")
module.INPUT_CSV = shard_path
module.INPUT_WKB_EPSG = 2157
module.OUTPUT_SUFFIX = "_national_flood"
module.main()
print("SHARD DONE:", shard_path.name, flush=True)
