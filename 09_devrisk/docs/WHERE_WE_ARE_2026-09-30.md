# Where We Are — full project review

Date: 2026-09-30. Companion to `PREDICTION_ACCURACY_FULL.md` (accuracy
detail) and `TIMING_ACCURACY_BRIEF.md` (timing detail). This file is the
overall state: objectives, current accuracy, data assets, architecture,
measured experiments, and open items.

---

## 1. Objective

Ireland-first development-risk engine: predict, at submission and through
the development lifecycle, the concrete events of a residential scheme
(refusal, FI, appeal, JR, decision/commencement/completion/sale timing,
refusal reasons, grant conditions, price vs peers) with absolute measures
(days, euros, probabilities), not composites. Frozen v4-full refusal model
is read-only. Research baselines only — nothing calibrated beyond the FI
card and timing strata card.

## 2. Current accuracy (all targets)

### 2.1 Timeline chain (multi-state Monte Carlo, holdout grant >= 2020)

| Milestone | MAE days | 80% interval coverage | Notes |
|---|---|---|---|
| Decision | 84 (GBM direct: 64) | 70% | best leg |
| Commencement | 386 (rolling-24m: 366; developer-shrunk: 312 on matched subset) | 64% | |
| First CCC | 641 | 41% | |
| Final CCC | 975 | 41% | |
| First sale | 1,487 | 26% | phase-level attribution needed |

### 2.2 Classifiers and evidence

| Target | Measure | Value | n |
|---|---|---|---|
| Refusal (frozen v4) | AUC / calibration | 0.792 (2024-25); 2025 slice 0.793 (0.778-0.807); decile mean abs error 0.9pp | 35,713 / 15,221 |
| FI v2 | AUC | 0.691 (0.668-0.716); 2025 0.578 (drift, not label maturity) | 1,731 |
| Appeal combined | AUC | 0.659 (0.621-0.698) | 1,729 |
| Appeal third-party | AUC | 0.647 (0.615-0.679) | prevalence 16.2% |
| Appeal applicant | AUC | 0.623 (0.566-0.675) | prevalence 6.7% |
| Refusal-reason transfer | top-1 / top-3 | 19.6% / 55.4% (baseline 25%) | 56 |
| Condition families | prevalence CIs | 11 families, 2.7%-9.2% (98% CI) | 338 |
| JR (Dublin) | rates | LRD 8.0%, SHD 5.0%, standard 0% | 2,366 |
| Price vs peers | median abs deviation | EUR 65k (26.9%); p80 EUR 153k | 582 |
| Macro (TimesFM-2.5) | county 12-mo MAE | volume 29.5 (vs 34.8), price EUR 19.2k (vs 28.4k), commencements 11.5 (vs 22.2) | 26-31 series |

### 2.3 Completion sub-targets (new this session)

| Target | n | Median | dynAUC |
|---|---|---|---|
| Commencement -> first CCC | 1,507 (1,106 events) | 550d KM | 0.48@12m, 0.64@48m |
| Commencement -> 25% certified | 219 events | 554d | 0.50@36m |
| Commencement -> 50% certified | 125 events | 591d | 0.51@48m |
| Commencement -> final CCC | 1,106 events | 804d KM | 0.60@36m |

### 2.4 Harness findings

- Commencement MAE, developer seen vs unseen: 334d vs 390d (constant train median)
- Unit-weighted commencement MAE: 440d (unweighted ~365d)
- Developer-group shrunk estimates: activation MAE 312d (vs global 327d); sale SPV-raw 831d (vs global 864d)
- Out-of-sample temporal holdouts throughout; authority breakdown and calibration-by-horizon in `silver/eval_harness_v1.json`

## 3. Data assets

| Asset | State | Coverage |
|---|---|---|
| NPAD register | ingested | 491,760; GE10 3,585; grant dates 53%; applicant names redacted in all layers |
| BCMS (full 99 fields) | ingested | 249,127 events; 83.8% mature pool linked; phase_number 86.7%, planned_duration 99.8%, ccc_type 40.8% |
| PPR | ingested | 807,724; 763 pool schemes (55.1%); 27,599 verified rows |
| Applicant index (ePlanning) | complete | 1,595 pages; 1,590 names; 1,020 entities; 68.7% pool coverage |
| CRO companies | ingested | 825,177; 62.5% applicant match; 475 developer groups |
| 4Dublin pipeline | ingested | Dublin completion corroboration (268 schemes, 12,878 units); JR; FI/appeal flags |
| Constraint layers + flood | ingested | full coverage on 1,113 pool schemes |
| Event ledger | built | 17,330 events, 1,813 developments; no downstream consumer yet |
| TimesFM forecasts | built | 83 county series |
| Applicant features v3 | run | 12m commencement td-AUC 0.582 (vs 0.56 without); no other lift |
| Completion targets | built | `silver/completion_targets.csv` (1,507 schemes) |
| Multi-state engine v1 | built | `silver/multistate_engine_v1.json` |
| Survival machinery | fixed | `devrisk/models/survival.py`: KM + IPCW dynamic AUC + integrated Brier |

## 4. Architecture

- **Event ledger** (`devrisk/labels/event_ledger.py`): every development as
  dated events; schema development_id / phase_id / event_type / dates /
  source / reference / units / status / confidence / observed.
- **Multi-state model** (`devrisk/models/multistate.py`): 8 states
  (application -> decision -> final_permission -> pre_construction ->
  phase_commenced -> first_ccc -> units_completed -> delivered); per-
  transition occurrence strata + conditional duration quantiles + stall +
  Monte Carlo chaining; route-split sale leg (private_sale / rental /
  social / forward_funded).
- **Survival evaluation**: fixed-grid cumulative incidence, KM-IPCW dynamic
  AUC, integrated Brier — the previous td-AUC 0.00-0.01 numbers were an
  evaluation bug (interval grid length varied with observation length,
  inverting rankings); intercept-only now returns ~0.5.
- **Developer groups**: CRO registered-address + name-prefix union-find
  (475 groups); hierarchical shrinkage K=5 for SPV vs group estimates.
- Frozen v4 refusal via `devrisk/models/planning_adapter.py` (read-only).

## 5. Measured experiments (results only)

**Positive results:**
- Decision GBM + smooth CDF: MAE 63.9d; pinball-p50 32.0; coverage cal 5.5pp
- Era recalibration (rolling-24m / authority-shrunk) for commencement: 366/361d vs naive 380d
- Rolling strata interval engine: 1,135d @ 83.2% coverage (fixes GBM under-coverage 74.6%)
- Post-CCC sale: median 34d (phase-level events), 60% within +/-180d
- BCMS notice-name matching: +188 schemes; applicant bridge: +11 schemes; PACK_14: +30 schemes
- Developer identity: seen vs unseen 334 vs 390d; shrunk 312d
- Completion models: first-CCC dynAUC 0.64@48m (first fitted completion model)

**Null / negative results (each measured):**
- Quantile-GBM smooth CDFs: calibrated, no discrimination (td-AUC ~0.5)
- Censoring-aware hazard (after evaluation fix): units feature 0.557@12m only
- Developer-declared build duration: r = 0.0
- Applicant prior medians: r -0.09 activation / -0.15 sale
- Market context, constraints (sale), AHB exclusion, authority dummies (appeal): no gain
- Overlap=2 PPR band: dead (0 candidates > p=0.5); spatial <=150m auto-confirm: 1% precision
- 4Dublin road-level candidates: 0/153 accepted; townland matching: negative
- Multi-task trunk, FI stacking, forward congestion: no gain

## 6. Data-quality findings

- Scheme-level CCC-to-sale is negative-skewed (sales frequently precede the
  scheme's first recorded CCC; median -670d unclipped). Phase-level sale
  attribution is required for that leg.
- Register applicant names/addresses are redacted in every NPAD layer;
  ePlanning is the identity source.
- Register FI dates are statutory artefacts (unusable for time-to-FI).
- completion_units in BCMS too sparse to split full-scheme vs phase CCCs.

## 7. Open items

1. **Tranche-2 pulls blocked** (BER Fingal ArcGIS 403, TED API 400 query
   syntax, gov.ie search JS-rendered, excavations.ie timeout) — retry with
   browser-grade requests or alternate endpoints.
2. National BER bulk: SEAI research-tool access not registered (user action).
3. ECAD/GeoDirectory licence not purchased (user decision).
4. FOI campaign (Part V, HSA AF1/AF2, ESB NC1, Uisce connections,
   development contributions) not drafted/submitted.
5. Phase-level sale attribution (phase CCC -> that phase's sales) not built.
6. Event ledger has no downstream consumer yet (multi-state v1 uses label
   pools directly).
7. Post-permission event feed (FSC/DAC flags, BER clusters, Part V) not yet
   wired into transition models.
8. JR national coverage remains Dublin-only.
9. PACK_14/15 verdicts processed; no further packs pending.

## 8. Where the numbers point

Decision date is predicted to within ~2 months (MAE 64-84d). Commencement
to within ~1 year (366d rolling; 312-334d where the developer is known).
Completion and sale legs carry ~1.5-2-year honest intervals; the accurate
statements there are conditional (post-CCC sale: median 34d). The measured
ceiling of submission-time features is documented in the two companion
briefs; the remaining accuracy levers are observation-density (BER/ECAD/
FOI) and phase-level attribution.
