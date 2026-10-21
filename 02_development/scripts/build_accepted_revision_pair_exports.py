#!/usr/bin/env python3
"""Build evidence-only accepted revision pairs and related-project group memberships."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from accepted_revision_pairs import build_accepted_revision_exports, read_revision_audit_csv

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, default=CURRENT / "project_revision_pairs.csv")
    parser.add_argument("--audit", type=Path, default=CURRENT / "project_revision_pair_audit.csv")
    parser.add_argument("--accepted-output", type=Path, default=CURRENT / "accepted_revision_pairs.csv")
    parser.add_argument("--group-output", type=Path, default=CURRENT / "accepted_revision_pair_group_map.csv")
    args = parser.parse_args()
    accepted, group_map = build_accepted_revision_exports(pd.read_csv(args.pairs), read_revision_audit_csv(args.audit))
    accepted.to_csv(args.accepted_output, index=False)
    group_map.to_csv(args.group_output, index=False)
    print({"accepted_pairs": len(accepted), "group_memberships": len(group_map)})


if __name__ == "__main__":
    main()
