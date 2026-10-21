# Handoff Template

Use this structure for project handoffs.

```markdown
# Handoff: <title>

## Metadata
- Generated At:
- Project Root:
- Git Branch:
- Head Commit:

## Original Goal

## Current State

## Completed This Session

## Validated
- Command:
- Result:

## Not Yet Validated
- Assumption:
- Risk:

## Remaining Work
- [ ] Item

## Decisions Made
- Decision:
- Reason:

## Blockers / Open Questions

## Critical Files
- /absolute/path/or/project/path

## Context To Load
- AGENTS.md
- state/SESSION.md
- state/TODO.md
- state/DECISIONS.md
- state/DEBUG_LOG.md

## Next Command
```text
<command>
```
```

Minimum bar:

- The `Validated` section must include at least one command or file evidence reference.
- The `Not Yet Validated` section should capture open assumptions or risks that still need checking.
- The `Next Command` must be directly executable.
- `Critical Files` should only include files the next session actually needs.
