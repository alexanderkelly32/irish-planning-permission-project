# Prospective shadow ledger

## Purpose

`prospective_shadow_ledger.csv` registers frozen Model v3 predictions for
residential applications received after the model's evaluated 2025 holdout
(currently everything received on or after 2026-01-01). It is a prospective
monitor: predictions are recorded now, and outcomes are read out separately
once they appear in the national planning dataset.

## Rules

- The ledger is **append-only**. A case key is registered once; rerunning
  `build_prospective_shadow_ledger.py` adds only new cases and never modifies
  existing registrations.
- Each row records the model version, timestamp, predicted risk, risk band,
  ranking score and the exact submission-time input snapshot.
- Outcomes must **not** be written into the ledger. When decisions arrive,
  record them in a separate outcomes file keyed by `case_key` and join them at
  readout time so the ledger history stays immutable.
- Readouts are monitoring diagnostics only. They must not be used to tune,
  promote or replace any model without a full validation protocol.

## Commands

From the project root in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .vendor).Path
python 05_policy/scripts/build_prospective_shadow_ledger.py
```

`prospective_shadow_ledger_summary.json` records each run's registration
counts, authority mix, risk-band mix and the current outcome readout.

## Current state

- 301 registered post-2025 residential submissions; 0 known outcomes.
- Frozen model artifact sha256:
  `06a2ca077e291d9eba42d8633381be1d5608be180a8836e658d061c8a529469b`
  (verified identical to the 2026-09-01 baseline registry).
