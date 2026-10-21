# ENGINE v1 — Freeze Manifest (2026-10-05)

This manifest freezes the state-estimation engine at v1. Nothing below
changes without an explicit research-reopening trigger.

## Supported production claims

1. **Refusal risk (pre-grant):** frozen model v4-full. Holdout 2024-2025,
   n=35,713: AUC 0.792 (95% CI 0.784-0.798), AP 0.409, calibrated Brier
   0.090, calibration within +-0.9pp. Top decile refused 63.8% (GE10).
2. **Decision timing (submission -> decision):** GBM quantile, MAE ~
   months scale, P(>12m) AUC 0.718 (n=433, holdout >=2024).
3. **Appeal likelihood:** AUC 0.657-0.659 temporal holdouts.
4. **FI likelihood:** AUC 0.688-0.733 across years.
5. **State machine (observed states only):** 15 states, 1,095 schemes;
   current state, entered date, days-in-state, sources, confidence,
   observed-vs-inferred flags. States never inferred from absence without
   a flag.
6. **Transition timing (state-conditioned):** empirical transition
   distributions per pair (median/IQR/50-80-90% intervals/3-6-12m
   probabilities) computed on completed transitions within a 5-year
   recency window. NO day-level precision claims.
7. **Progress landmarks 25/50/75%:** observed from unit-counted CCC
   events on phase-resolved schemes only (BCMS CN_Units_for_phase within
   30% of register units). 80% remaining-time width: 1,317d at
   commencement -> 984d at 25% -> 733d at 50% -> 556d at 75%.
8. **Post-commencement stages:** commenced->first CCC median 498d;
   first->final CCC 292.5d; notice filed -> commenced median 14d (90%
   within 3m).
9. **Calibration guarantees:** per-transition conformal recalibration,
   calibrated on the preceding era, applied out-of-era. Coverage targets
   out-of-era: 50% interval >= 40%, 80% >= 75%, 90% >= 85%. Transitions
   failing the target are safety-widened or marked not-ship. No
   transition ships with materially optimistic coverage.

## Provisional outputs (NOT production claims)

- **Pre-commencement-condition likelihood** (conditions_precomm_v0,
  logistic, train grant<2022): test AUC 0.714 (n=72, single split).
  Frozen into the SHADOW log only (319 predictions, 2026-10-01).
  Promotion trigger: a second temporal/rolling-origin validation
  confirming AUC ~0.71.
- **Financial-condition likelihood:** AUC 0.658 (same corpus) - shadow
  only.
- **Progress GBM (elapsed+progress):** rolling origin +19.4/+21.1/+12.6/
  -3.1% vs elapsed-band median; fails the latest period. NOT promoted;
  empirical tables are the product. Re-check when 2024-25 completions
  mature.
- **TIC events:** n=4 - distributional only.
- **FSC/DAC landmarks:** first-submit gives no uncertainty collapse.

## Blocked / falsified registry

Machine-readable: silver/experiment_registry.json (46 experiments:
10 keep / 6 provisional / 22 falsified / 8 blocked). Highlights:
- Day-zero commencement timing: public-data information ceiling
  (economic-state hazard flat; compliance activity flat; condition
  burden flat; SPV/amendment landmarks falsified; observability audit
  empty).
- Data sources blocked: BER (no geo), CRO FS (metadata only), CRO
  charges (paid), daft historical listings (no sold route), enforcement
  harvest (junk), SHCSR, iDocs phase drawings (image-only title blocks).
- Estimators falsified: naive expanding quantiles (censoring bias),
  windowed KM (dormant-tail inflation), recency-weighted empirical.

## Model / data versions

- refusal: 05_policy/current/model_v4/national_residential_v4_full.joblib
  (frozen 22 Sep 2026)
- state machine: silver/state_machine/states.csv + transitions.json +
  uncertainty_reduction.json (2026-10-05, phase-clean pct states)
- progress: silver/construction_progress/* (phase-clean variant used by
  the state machine)
- calibration: silver/calibration/per_transition_calibration.json
- quarantine: silver/dq/ (rules R1-R11; clean view 491 schemes)
- shadow: silver/shadow/shadow_predictions.csv (1,595 frozen
  predictions; append-only, write-once)
- corpus: condition_corpus.csv (319 schemes); golden replay artifacts
  silver/replay/

## Known limitations

1. grant -> commencement remains the wide regime (median ~433d, 80%
   width ~1,340d); the private go/no-go decision is not publicly
   observable.
2. Interval coverage in raw replay remains 37/63/73% (50/80/90) - the
   conformal layer corrects this at query time; raw tables are NOT
   exposed without calibration.
3. Phase-aware progress excludes schemes without reliable BCMS phase
   units (~42% of progress cohort); R11 warn rows are surfaced, never
   silently repaired.
4. Condition-corpus bias: pre-2020 grants parse poorly; corpus
   concentrates 2020+.
5. Offaly/Galway City/Mayo iDocs portal flows remain unscripted
   (different checkbox forms).

## Reopening triggers (research)

1. Progress GBM: after >= 200 additional 2024-25 completions mature -
   rerun rolling origin.
2. Conditions predictor: any new temporal split with n_test >= 100.
3. FOI/ESB/Uisce/ECAD: ingest via the generic landmark adapter
   (B-test value even if C fails); reopen only on data arrival.
4. daft sold-search or archive route appearing.
5. A new public dataset that reveals STATE CHANGE (mechanism written
   before extraction - ranked registry in
   silver/landmarks/alternative_landmark_registry.json).
