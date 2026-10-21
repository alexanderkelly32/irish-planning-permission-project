"""Runner: ingest a source snapshot. Usage: python 09_devrisk\\scripts\\run_ingest.py bcms|npad|ppr"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402
from devrisk.ingestion import bcms, npad, ppr  # noqa: E402

if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "bcms"
    if source == "bcms":
        print(bcms.run(settings.RAW_DIR, settings.BRONZE_DIR, settings.MANIFEST_DIR))
    elif source == "npad":
        print(npad.build_bronze(settings.REGISTER_FULL_PARQUET, settings.BRONZE_DIR, settings.MANIFEST_DIR))
    elif source == "ppr":
        force = "--force" in sys.argv
        print(ppr.run(settings.RAW_DIR, settings.BRONZE_DIR, settings.SILVER_DIR, settings.MANIFEST_DIR, force=force))
    else:
        raise SystemExit(f"unknown source: {source}")
