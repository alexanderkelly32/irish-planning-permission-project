#!/usr/bin/env python3
"""Check whether a handoff still matches the current repository state."""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys


def run_git(args: list[str], cwd: pathlib.Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def extract_field(text: str, field: str) -> str:
    match = re.search(rf"^- {re.escape(field)}: (.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def classify(branch_match: bool, commits_since: int) -> str:
    if not branch_match:
        return "VERY_STALE"
    if commits_since <= 3:
        return "FRESH"
    if commits_since <= 10:
        return "SLIGHTLY_STALE"
    if commits_since <= 20:
        return "STALE"
    return "VERY_STALE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", help="Path to handoff markdown file.")
    args = parser.parse_args()

    handoff = pathlib.Path(args.handoff).expanduser().resolve()
    if not handoff.exists():
        print(f"Handoff does not exist: {handoff}", file=sys.stderr)
        return 1

    text = handoff.read_text(encoding="utf-8")
    project_root = extract_field(text, "Project Root")
    handoff_branch = extract_field(text, "Git Branch")
    handoff_commit = extract_field(text, "Head Commit")
    if not project_root:
        print("STALE")
        print("Reason: handoff missing Project Root metadata")
        return 0

    root = pathlib.Path(project_root)
    current_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    no_git = not current_branch and (handoff_branch in {"", "unknown"})
    branch_match = no_git or (bool(handoff_branch) and handoff_branch == current_branch)

    commits_since = 999
    if handoff_commit and handoff_commit != "unknown" and current_branch:
        count = run_git(["rev-list", "--count", f"{handoff_commit}..HEAD"], root)
        if count.isdigit():
            commits_since = int(count)
    elif no_git:
        commits_since = 0

    status = classify(branch_match, commits_since)
    print(status)
    print(f"Handoff branch: {handoff_branch or 'unknown'}")
    print(f"Current branch: {current_branch or 'unknown'}")
    print(f"Commits since handoff commit: {commits_since if commits_since != 999 else 'unknown'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
