#!/usr/bin/env python3
"""Sequential, resume-safe runner for all flood shards."""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"")
SHARD_DIR = ROOT / "07_context" / "raw" / "flood_shards"
LOG = SHARD_DIR / "flood_runner_log.txt"

shards = sorted(SHARD_DIR.glob("flood_input_shard_*.csv"))
for shard in shards:
    output = Path(str(shard.with_suffix("")) + "_national_flood.csv")
    if output.exists() and output.stat().st_size > 0:
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} SKIP {shard.name} (output exists)\n")
        continue
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%H:%M:%S')} START {shard.name}\n")
    result = subprocess.run(
        [sys.executable, str(ROOT / "01_flood" / "scripts" / "run_one_flood_shard.py"), str(shard)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(result.stdout[-2000:] if result.stdout else "")
        handle.write(result.stderr[-2000:] if result.stderr else "")
        handle.write(f"{time.strftime('%H:%M:%S')} END {shard.name} rc={result.returncode}\n")
    print(result.stdout[-500:] if result.stdout else "", flush=True)
    print(result.stderr[-500:] if result.stderr else "", flush=True)
print("ALL SHARDS PROCESSED", flush=True)
