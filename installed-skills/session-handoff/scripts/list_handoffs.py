#!/usr/bin/env python3
"""List project handoff files."""

from __future__ import annotations

import argparse
import pathlib


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root. Defaults to current directory.")
    args = parser.parse_args()

    root = pathlib.Path(args.root).expanduser().resolve()
    handoff_dir = root / ".codex" / "handoffs"
    if not handoff_dir.exists():
        print(f"No handoffs found in {handoff_dir}")
        return 0

    for path in sorted(handoff_dir.glob("*.md"), reverse=True):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
