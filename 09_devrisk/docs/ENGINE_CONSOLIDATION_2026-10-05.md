# State Engine - Consolidation Snapshot (2026-10-05)

The landmark search is closed per protocol (both remaining held-data
candidates failed: enforcement blocked, TIC n=4). This is what the
engine consists of and how its parts were validated.

## Production surface (all validated)

1. **Frozen v4-full refusal model** - AUC 0.792/0.793, calibrated +-0.9pp.
   Untouched throughout.
2. **Canonical state machine** (silver/state_machine/): 15 states x 1,095
   schemes, observed/inferred never conflated, sources + confidence per
   state, current_state + next_possible_states per scheme.
3. **Transition tables** (transitions.json): empirical per-pair
   distributions (n, median, IQR, 3/6/12m probabilities) with grant-
   consistency guards. The product estimator for timing.
4. **Progress landmarks 25/50/75%** (construction_progress/): observed
   states from unit-counted CCC events; 80% width collapses 1,441d -> 613d
   by 75%; first useful at 25%.
5. **Conformal calibration** (calibration/): expansion factor calibrated on
   the previous era restores near-nominal out-of-time interval coverage
   (the production fix for under-coverage; judged on coverage not MAE).
6. **Quarantine + clean views** (dq/): rules R1-R10, 3,932 rows, clean
   labels exclude blocked + pending; invariants tested.
7. **Shadow deployment** (shadow/): 1,276 write-once frozen predictions
   from 2026-10-01; scoring = MAE/coverage/horizon hits as outcomes land.
8. **Product reports** (state_machine/reports/): status / next / calibrated
   timing / evidence / change log / confidence / unknowns; states
   explicitly when the engine cannot distinguish.
9. **Generic external-landmark adapter**: drop-in CSV ingest with linkage,
   sanity, before/after distributions, uncertainty reduction; predictive
   test gated at n>=100.

## Known defects queued for production hardening

1. Interval under-coverage: conformal expansion fixes it per-era; needs
   per-pair calibration + suppression of backwards-moving medians (replay
   anomalies: 10 median-backwards, 8 interval-widens).
2. Phase-aware denominators: all 31 replay linkage failures were phase
   ambiguity; never mix phase and scheme CCCs.
3. Progress GBM: provisional only (rolling origin +19/+21/+13/-3%) -
   empirical tables remain the product until recent-era re-check.
4. Naive expanding quantiles + windowed KM falsified (censoring bias /
   dormant-tail inflation) - do not reintroduce.

## Falsified/blocked ledger (41-42 experiments in registry)

10 keep / 5 provisional / 21 falsified / 7 blocked. Landmark search:
SPV incorporation (falsified), amendment activity (falsified), daft
launch (blocked - data source), enforcement (blocked - harvest junk),
TIC (provisional - n=4). Compliance activity (flat - dropped as live
predictor). Economic-state hazard (flat). Macro/static market variables
(flat). Day-zero commencement timing: public-data information ceiling
documented.

## What remains genuinely valuable to run next (in order)

1. Re-run progress rolling origin once 2024-25 completions mature
   (decides whether the GBM is ever promoted).
2. Per-pair conformal calibration + anomaly suppression in the product
   report generator (small, high-value hardening).
3. Phase-aware denominators for cumulative % certified.
4. Live monitoring: firstPublishDate (daft) and BCMS notice filings as
   forward-only sensors - no historical claims.
