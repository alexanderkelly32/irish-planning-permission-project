---
name: session-handoff
description: Create or resume a project handoff for Codex when work spans multiple sessions, the conversation is getting long, or the user wants to pause, switch threads, continue from a saved checkpoint, or reduce context rot. Prefer this skill when the project already uses AGENTS.md and durable state files such as SESSION.md, TODO.md, DECISIONS.md, and DEBUG_LOG.md.
metadata:
  short-description: Save and resume Codex work across sessions
---

This skill standardizes cross-session handoff for Codex by storing durable project state in files instead of relying on old chat history.

Use this skill in two modes:

- `create`: save the current session into a project handoff
- `resume`: load and validate a previous handoff before continuing

Store handoffs in the project root at `.codex/handoffs/`.

## Operating System Notes

- Prefer platform-neutral paths such as `--root .` and `.codex/handoffs/<file>.md`.
- When you show commands to the user and the OS is unclear, give both:
  - a macOS/Linux example that uses `python3`
  - a Windows PowerShell example that uses `python`
- Do not hardcode shell-specific constructs such as `$(pwd)` unless you already know the user is on a POSIX shell.

## Create Workflow

### Step 1: Load durable context

Before writing a handoff, read the project's durable context in this order when the files exist:

1. `AGENTS.md`
2. `state/SESSION.md`
3. `state/TODO.md`
4. `state/DECISIONS.md`
5. `state/DEBUG_LOG.md`

If the project does not use this structure, fall back to the files that actually contain current task state.

### Step 2: Generate scaffold

Run:

```text
macOS/Linux:
python3 ./scripts/create_handoff.py --root . --title "<task-slug>"

Windows PowerShell:
python .\scripts\create_handoff.py --root . --title "<task-slug>"
```

Optional:

- `--next-command "..."` to pre-fill the first next action
- `--output path/to/file.md` to override the default destination
  - absolute paths stay absolute
  - relative paths are resolved from the project root

The script creates:

- `.codex/handoffs/YYYY-MM-DD-HHMMSS-<slug>.md`

It pre-fills:

- project root
- git branch and HEAD commit when available
- recent commits
- modified files
- detected state files
- a structured template

### Step 3: Complete the handoff

Fill every placeholder section with concrete facts from the current session:

- original goal
- current state
- completed work
- validated items and how they were verified
- items that are still unverified
- remaining work
- decisions made
- blockers or open questions
- critical files
- next command

Do not leave vague text such as "continue debugging" or "pick up where we left off". The next command must be directly executable.

### Step 4: Return a copyable resume prompt

After the handoff file is complete, give the user a short prompt they can paste into a fresh Codex conversation. Prefer this shape:

```text
先读 AGENTS.md、state/SESSION.md、state/TODO.md、state/DECISIONS.md、state/DEBUG_LOG.md，以及 .codex/handoffs/<file>.md。
然后继续处理：<task>.
第一步先执行：<next command>.
```

## Resume Workflow

### Step 1: Find handoffs

Run:

```text
macOS/Linux:
python3 ./scripts/list_handoffs.py --root .

Windows PowerShell:
python .\scripts\list_handoffs.py --root .
```

If the user named a specific handoff file, use that directly.

### Step 2: Check staleness

Run:

```text
macOS/Linux:
python3 ./scripts/check_staleness.py .codex/handoffs/<file>.md

Windows PowerShell:
python .\scripts\check_staleness.py .codex\handoffs\<file>.md
```

Interpretation:

- `FRESH`: resume normally
- `SLIGHTLY_STALE`: review git changes first
- `STALE`: re-check assumptions before changing code
- `VERY_STALE`: prefer creating a fresh handoff after re-baselining

If the project is not a git repository, the staleness check falls back to handoff metadata and file existence instead of branch history.

### Step 3: Reload the durable context

Read:

1. the handoff file
2. `AGENTS.md`
3. referenced `state/*.md` files
4. any critical files listed in the handoff

Then begin with the handoff's `Next Command`.

## Quality Rules

- Prefer project facts over memory from the old chat.
- Prefer handoff documents over raw transcript dumps.
- Make the handoff explicitly distinguish completed work, validated work, unvalidated work, and the next command.
- Never write secrets, tokens, cookies, or private credentials into handoffs.
- Keep handoffs concise but executable.
- If state files are stale, update them before finalizing the handoff.
- If the task split changed, create a new handoff instead of mutating an old one beyond recognition.
- Keep `SKILL.md`, `agents/openai.yaml`, and `README.md` aligned when you update public-facing behavior or examples.

## Resources

- Template guidance: `references/handoff-template.md`
- Create script: `scripts/create_handoff.py`
- List script: `scripts/list_handoffs.py`
- Staleness check: `scripts/check_staleness.py`
