#!/usr/bin/env python3
"""Create a Codex handoff scaffold in the current project."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import subprocess
import sys
from typing import Iterable


STATE_CANDIDATES = [
    "AGENTS.md",
    "state/SESSION.md",
    "state/TODO.md",
    "state/DECISIONS.md",
    "state/DEBUG_LOG.md",
]


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


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "handoff"


def detect_context_files(root: pathlib.Path) -> list[str]:
    return [path for path in STATE_CANDIDATES if (root / path).exists()]


def format_list(items: Iterable[str], fallback: str) -> str:
    values = [item for item in items if item]
    if not values:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in values)


def default_output(root: pathlib.Path, title: str) -> pathlib.Path:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    handoff_dir = root / ".codex" / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    return handoff_dir / f"{timestamp}-{slugify(title)}.md"


def resolve_output(root: pathlib.Path, raw_output: str, title: str) -> pathlib.Path:
    if not raw_output:
        return default_output(root, title)

    output = pathlib.Path(raw_output).expanduser()
    if not output.is_absolute():
        output = root / output
    return output.resolve()


def render_handoff(
    root: pathlib.Path,
    title: str,
    branch: str,
    head_commit: str,
    recent_commits: list[str],
    modified_files: list[str],
    context_files: list[str],
    next_command: str,
) -> str:
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    return f"""# Handoff: {title}

## Metadata

- Generated At: {generated_at}
- Project Root: {root}
- Git Branch: {branch or "unknown"}
- Head Commit: {head_commit or "unknown"}

## Original Goal

[TODO: 用户原始目标]

## Current State

[TODO: 当前正在做什么，最近做到哪里]

## Completed This Session

- [TODO: 已完成事项 1]
- [TODO: 已完成事项 2]

## Validated

- Command: [TODO: verification command / 验证命令]
- Result: [TODO: key result / 关键结果]

## Not Yet Validated

- Assumption: [TODO: pending assumption / 待验证假设]
- Risk: [TODO: risk if assumption is wrong / 假设错误的风险]

## Remaining Work

- [ ] [TODO: next priority task / 下一优先级任务]
- [ ] [TODO: later task / 后续任务]

## Decisions Made

- Decision: [TODO: key decision / 关键决策]
- Reason: [TODO: reason / 决策原因]

## Blockers / Open Questions

- [TODO: blocker or open question / 阻塞项或待确认问题]

## Critical Files

{format_list(context_files, "暂无，按实际任务补充")}

## Recent Commits

{format_list(recent_commits, "当前无可用 git 提交信息")}

## Modified Files

{format_list(modified_files, "当前无未提交修改或无法读取 git 状态")}

## Context To Load

{format_list(context_files, "请补充需要重新加载的关键文件")}

## Next Command

```text
{next_command or '[TODO: fill in one directly executable command / 填入下一条明确命令]'}
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root. Defaults to current directory.")
    parser.add_argument("--title", required=True, help="Short handoff title or task slug.")
    parser.add_argument("--next-command", default="", help="Executable next command for the next session.")
    parser.add_argument("--output", default="", help="Optional absolute or relative output path.")
    args = parser.parse_args()

    root = pathlib.Path(args.root).expanduser().resolve()
    if not root.exists():
        print(f"Project root does not exist: {root}", file=sys.stderr)
        return 1

    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    head_commit = run_git(["rev-parse", "--short", "HEAD"], root)
    recent_commits = run_git(["log", "--oneline", "-n", "5"], root).splitlines()
    modified_files = run_git(["status", "--short"], root).splitlines()
    context_files = detect_context_files(root)

    output = resolve_output(root, args.output, args.title)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_handoff(
            root=root,
            title=args.title,
            branch=branch,
            head_commit=head_commit,
            recent_commits=recent_commits,
            modified_files=modified_files,
            context_files=context_files,
            next_command=args.next_command,
        ),
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
