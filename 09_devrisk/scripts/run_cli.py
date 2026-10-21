"""Runner: devrisk CLI. Usage: python 09_devrisk\\scripts\\run_cli.py --help"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
