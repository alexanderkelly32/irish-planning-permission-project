# Prediction accuracy — all targets (facts)

Date: 2026-09-30 (sections 33-50 appended 2026-10-03 to 2026-10-06:
readiness/iDocs, economic-state, state engine, quarantine/shadow, progress,
replay, calibration, moonshot programme S1-S5, product measurement spec,
zero-day stats, confirmatory pass, demo report). Every target the engine
predicts or has measured evidence for, with protocol, holdout n, and
interval where computed. No assessment language. Timing detail in
`TIMING_ACCURACY_BRIEF.md`; this file is the complete list.

Purpose: this document is the objective evidence base for the product. The
aim of the whole engine is to report statistically backed, objective
evidence of what is happening in Irish residential development, to give
insight to developers and lenders (and other market participants). It
reports measurements only - what was tested, the numbers that came out,
and whether each signal survived its gate. Nothing here is opinion or
editorial: every claim carries its holdout, sample size and interval;
negative and null results are reported with the same weight as positive
ones, because a null result is itself evidence.

Conventions: temporal holdouts (train on earlier received/grant dates,
evaluate on later). Bootstrap percentile CIs, 2,000 resamples, 98% unless
stated. Prevalence = share of positive class in the holdout.

---

## 1. Refusal probability (frozen model v4-full)

- Model: national residential, submission-time features, pre-2024 training.
- Holdout: 2024–2025, n=35,713: AUC 0.792 (95% CI 0.784–0.798), AP 0.409,
  Brier 0.090, calibrated.
- 2025 slice, n=15,221: AUC 0.793 (0.778–0.807), AP 0.413 (0.383–0.444),
  Brier 0.085 (0.080–0.089).
- Calibration (decile bins, 2025): mean absolute error 0.9pp, max 5.5pp
  (top decile: predicted 0.408 vs observed 0.353).
- GE10 (10+ units) focus: n=464, AUC 0.782; riskiest decile refused at
  63.8%, safest at 0%. Risk bands: low ≤3.8%, medium 3.8–11.4%, high >11.4%.
- Model is frozen (read-only); never retrained.

## 2. FI likelihood (further information requested)

- v1 (pain pool; train received <2020, C-tuned + isotonic on 2020, holdout
  ≥2021): n=363, prevalence 0.73, AUC 0.688 (0.606–0.761), AP 0.840
  (0.774–0.895), Brier 0.184.
- v2 (full GE10 register, GBM d3 chosen on 2020 validation AUC 0.754, same
  split): n=1,731, AUC 0.691 (0.668–0.716). By year: 2021 0.721 (n≈340),
  2022 0.733, 2023 0.683, 2024 0.719, 2025 0.578.
- Label source: register FIRequestDate/FIRecDate + 4Dublin pipeline
  FI_Request fills (+4 positives). Prediction time: immediately before
  submission.

## 3. Appeal likelihood

- v1 (full GE10 register, logistic, structured + description TF-IDF, train
  received <2021, holdout ≥2021, no authority dummies): n=1,729, prevalence
  0.229 (0.206–0.253), AUC 0.659 (0.621–0.698), AP 0.347 (0.297–0.406).
- v2 (added time-safe prior appeal rates, density, site, covid, GBM; tuned
  on 2019–2020): n=1,729, AUC 0.657 (0.626–0.687), AP 0.342.
- Authority dummies measured to degrade AUC (excluded).
- Label source: register AppealSubmittedDate + 4Dublin Appeal_Submitted
  (+13 positives).

## 4. Decision timing (submission → decision)

- GBM quantile model (train received <2024, holdout ≥2024): n=433, MAE
  63.9d (constant 86.7d, strata 80.2d); pinball P50 32.0 (constant 43.3,
  strata 39.7); pinball P20 15.1, P80 21.5.
- Horizon classifiers (same holdout): P(>6m) AUC 0.755 (0.688–0.815),
  prevalence 0.349; P(>12m) AUC 0.718 (0.475–0.919), prevalence 0.023.
- Smooth conditional CDF (19-quantile GBMs, monotone): bin-free quantile
  coverage mean |dev| 5.5pp, max 9.8pp; P(>6m) calibration-in-large +0.13pp,
  Brier 0.184 (vs constant 0.227); P(>12m) −0.74pp.

## 5. Commencement timing (grant → commencement, schemes that commence)

- Strata MAE: 512d (98% CI 450–577, n=494); constant 526d (463–592).
- Rolling-24m median recalibration (time-safe at each grant date): MAE
  366.5d; authority-shrunk rolling: 360.8d; oracle test-median: 364.4d;
  naive pre-2020 median: 380.1d (n=494).
- Median-prediction MAE (GBM smooth v2): 366d (95% CI 338–397, n=496);
  median absolute error 266d. Hit rates vs predicted median: ±90d 15.5%,
  ±180d 34%, ±365d 65%.
- Smooth CDF intervals (n=496): 50% interval width 627d, coverage 48%;
  80% width 1,135d, coverage 83.2% (strata engine) / 1,155d @ 74.6% (GBM);
  90% width 1,574d, coverage 82.9%.
- Discrimination (time-dependent AUC of P(commence ≤ t)): 0.56@365d,
  0.52@730d, ≈0.5 beyond (v2 with constraint features; v1 without: ≈0.50–0.52).
- Censoring-aware discrete hazard (full pool, unlinked censored, n=523/572):
  td-AUC 0.0–0.01; Brier 0.41–0.53 vs KM 0.13–0.26.
- Activation survival baseline: c-index 0.48; horizon AUC 0.58 (BCMS-linked).
- Coverage: 958/1,113 pool schemes have commencement labels (86.1%).

## 6. Build duration (commencement → CCC)

- n=1,180 events: median 483d; constant-median MAE 241d; ±90d 31.6%,
  ±180d 56.7%, ±365d 85.8%.
- Developer-declared proposed-end duration: correlation with actual 0.0
  (n=1,168); MAE using declared 307d.
- Completion coverage: 815/1,113 pool schemes with a CCC date (73.2%).

## 7. Sale timing (grant → first sale, schemes with confirmed sales)

- Strata MAE: 419d (98% CI 337–507, n=97); constant 447d (381–513).
- Median-prediction MAE (GBM smooth v2): 473d (95% CI 422–527, n=101);
  hit rates: ±180d 19%, ±365d 38%.
- Smooth CDF intervals (n=101): 50% width 819d @ 42.6%; 80% width 1,415d @
  74.3%; 90% width 1,626d @ 87.1%.
- Discrimination: td-AUC ≈0.5 at all horizons (v1: 0.46–0.68 across
  horizons on n=97; v2 with constraints: 0.36–0.59). Market-context GBM
  pinball p50 236.1 vs strata 209.7 (no gain). Applicant prior-median
  time-to-sale r = −0.15 (n=109).
- Binned horizon classifier P(>2yr): AUC 0.672 (0.553–0.781, n=97).
- Coverage: 582/1,113 pool schemes (52.3%) with confirmed sales; verified
  rows 27,599.

## 8. First sale after CCC (conditional)

- n=2,021 CCC events: median 34d; ±180d 60%, ±365d 74%.
- From commencement (not CCC): median 501d, 80% width 1,598d (n=280).
- Declared-duration terciles (post-CCC): median 257d / 95d / 39d (n=59/56/58).

## 9. Price vs peers

- n=582 priced schemes: scheme median price median €303,965; vs same-county
  contemporaneous 12-month benchmark median, absolute deviation median
  €65,187 (26.9%), mean €442,224, p80 €152,520. Below-market-25pct flag on
  37 schemes.

## 10. Refusal reason transfer (theme of matched refused precedents)

- Cohort: refused GE10 holdout 2024–2025, n=88 refused, 56 evaluable.
  Top-1 agreement 19.6%, top-2 39.3%, top-3 55.4% (98% CI 42.1–68.5% on the
  n=81 protocol), baseline (most-common-tag) 25.0%.
- Label pool: 1,380 refused cases tagged (78%); llm_new display source 166
  rows.

## 11. Grant-condition family prevalence (conditional on grant)

- Corpus n=338 labelled planner reports. Prevalence (98% CI): roads/access/
  transport 9.2% (5.9–13.5); drainage/wastewater/water 9.2% (5.9–13.5);
  construction/environmental management 5.0% (2.7–8.5); archaeology/ecology/
  conservation 7.1% (4.2–11.0); flood mitigation 6.8% (4.0–10.7);
  landscaping/open space 8.0% (4.9–12.1); design/material changes 7.4%
  (4.5–11.4); Part V/bonds/contributions 4.4% (2.2–7.8); phasing/occupancy/
  tenure 5.3% (2.9–8.9); precommencement submissions 2.7% (1.0–5.5);
  preoccupation/certification/infrastructure 3.0% (1.2–5.9).

## 12. Judicial review (Dublin evidence)

- 4Dublin pipeline, latest quarter per reference, n=2,366: overall 0.9%.
  By app type: LRD 8.0% (n=100), SHD 5.0% (n=281), Standard 0% (n=551),
  SDZ 0% (n=67), DZ 0% (n=58), LA/State 0% (n=52), unclassified 0% (n=1,257).
  By authority: Dublin City 1.3% (n=1,184), SDCC 0.9% (n=465), Fingal 0.4%
  (n=717).
- No national courts bulk source ingested; no JR model exists.

## 13. Macro market forecasts (TimesFM-2.5, county level, 12-month horizon)

Backtest (pooled MAE over 26–31 county series):
- PPR county monthly volume: 29.5 (persistence 49.6, seasonal 34.8); beats
  seasonal in 23/26 counties.
- PPR county monthly median price: €19,229 (persistence €23,148, seasonal
  €28,391); beats seasonal in 24/26.
- BCMS county monthly commencements: 11.5 (persistence 12.5, seasonal 22.2);
  beats seasonal in 30/31.

## 14. Linkage coverage (label availability, not predictions)

- BCMS: 1,676 confirmed-linked schemes; 83.8% of mature pool.
- PPR sales: 763/1,113 pool schemes (55.1%); 27,599 verified rows.
- Applicant identity: 765/1,113 (68.7%) named; 1,020 entities; 62.5%
  CRO-matched; 213 with prior track record.
- ePlanning links: 89.8% of GE10; BCMS planning references: 66.4%
  eplanning-link coverage on register.

## 15. Targets with no fitted model

- JR dates (national): evidence §12 only.
- Units completed / under construction: Dublin corroboration only (268
  schemes, 12,878 units via 4Dublin).
- Part V timing, HSA notifications, ESB energisation, Uisce connections,
  road openings, archaeology dates: not ingested (access states in
  `TIMING_ACCURACY_BRIEF.md` §6).
- Completion-timing model beyond constant/declared (both measured, §6):
  none fitted.

## 16. Multi-state engine (2026-09-30)

- Survival audit: earlier td-AUC 0.00-0.01 was an evaluation bug (per-scheme
  incidence grid length varied with observation length, inverting rankings).
  Fixed-grid + IPCW dynamic AUC now used. Intercept-only baseline returns
  ~0.5 (0.493-0.516); synthetic-data check passes (correct sign 0.709).
- Completion models (commencement -> CCC, n=1,507 schemes, 2,038 phases,
  corrected evaluation, time-only hazard): first-CCC KM median 550d (events
  1,106), dynAUC 0.48@12m -> 0.64@48m; 25% certified median 554d (n=219);
  50% certified median 591d (n=125); final CCC KM median 804d, dynAUC
  0.48@12m -> 0.60@36m.
- Monte Carlo timeline chain (train grant <2020, holdout >=2020):
  decision MAE 84d (coverage 80% interval 69.6%); commencement MAE 386d
  (64%); first CCC MAE 641d (41%); final CCC MAE 975d (41%); first sale MAE
  1,487d (26%). Errors accumulate per leg.
- Route split: private_sale / rental / social / forward_funded from
  description + AHB flags; route-specific sale transitions fitted.
- Developer groups: 475 groups (shared CRO registered address + name-prefix
  clustering). Shrunk group estimates (K=5): activation MAE global 327d,
  SPV-raw 312d, group 317d, shrunk 312d (n=251); sale MAE global 864d,
  SPV-raw 831d, group 887d, shrunk 874d (n=127).
- Appeals split: third-party appeals prevalence 16.2%, AUC 0.647
  (0.615-0.679); applicant appeals 6.7%, AUC 0.623 (0.566-0.675). Combined
  v1 remains 0.659.
- FI label maturity: FI rate stable 0.61-0.63 by received year 2017-2025
  (2024-25 decision-dated rows 0.69). The v2 2025 AUC drop is not label
  immaturity.
- Product-style harness: commencement MAE by developer familiarity - seen
  334d vs unseen 390d (constant train median, n~250 each); unit-weighted
  MAE 440d (unweighted ~365d); calibration by horizon (train vs test
  occurrence dev pp recorded); confidence-sliced MAE by predicted-speed
  quartile recorded.
- Data-quality finding: scheme-level CCC-to-sale is negative-skewed (sales
  frequently precede the scheme's first recorded CCC; median -670d without
  clipping) - phase-level sale attribution is required for that leg.

## 17. Open items (end-of-session state)

- Tranche-2 pulls blocked on endpoints (BER Fingal ArcGIS 403, TED API 400
  query syntax, gov.ie search JS-rendered, excavations timeouts) - retry
  with browser-grade requests or alternate endpoints next session.
- National BER bulk: SEAI research-tool access not registered.
- Phase-level sale attribution (phase CCC -> that phase's sales) not built.
- Event ledger: no downstream consumer yet (multi-state engine v1 consumes
  label pools directly; ledger wiring pending).

## 18. Phase-level time-to-sale pipeline (2026-09-30, in progress)

Per the phase-level plan (central rule: no further grant-to-sale optimisation
until phase labels are trustworthy):

- **phase_master.csv**: 3,447 distinct phases (27,363 notices aggregated by
  development+phase-number+date), 2,321 private-sale routes; viable cohort
  (private-sale housing, 10-150 houses, commenced >1yr before censor): 807
  phases; 896 with 10-150 houses.
- **Phase PPR linking** (A/B/C confidence): 548 phases with candidates;
  A=4, B=1,231, C=22,481 rows. PACK_16 audit (294 rows: 4A/190B/100C)
  generated for human adjudication - target >=95% precision on confirmed.
- **Label-gate stats (provisional A+B)**: 21 negative commencement-to-sale
  attributions remain; train observed n=25 (commencement <2021), test n~40.
- **E0 baselines (provisional A+B, test)**: global median MAE 246d
  (+-100d 27.5%, +-180d 42.5%, +-365d 72.5%); developer-shrunk 253d;
  declared-duration 251d (+-365d 80% - phase-level declared duration tracks
  better than scheme-level where r=0); size-band 456d; county-band 426d;
  nearest-comparable 426d.
- E1 direct models skipped (train observed <30). E3 horizon AUC 0.36-0.51
  (no discrimination at current n). E4 gating pending fitted model.
- Blocking: small labelled cohort + pending PACK_16 audit; C-class links
  (22,481 rows) are the recall reservoir if audit shows acceptable
  precision for a loosened band.
- Customer programme schema: docs/customer_programme_schema.json
  (snapshot vs actuals, retrospective validation only).

## 19. Go/no-go gates (from the phase plan; current status)

| Gate | Criterion | Status |
|---|---|---|
| Label | >=95% audited phase-sale precision; no systematic negative CCC-to-sale | NOT MET (audit pending; 21 negative tfs rows) |
| Model | >=10% MAE over best segmented baseline | NOT TESTED (n < 30 train) |
| Product | overall commencement-to-sale MAE <200d, or <100d on identified high-confidence subset; ~80% interval coverage | NOT MET |

## 16. Multi-state engine (2026-09-30)

- Survival audit: earlier td-AUC 0.00-0.01 was an evaluation bug (per-scheme
  incidence grid length varied with observation length, inverting rankings).
  Fixed-grid + IPCW dynamic AUC now used. Intercept-only baseline returns
  ~0.5 (0.493-0.516); synthetic-data check passes (correct sign 0.709).
- Completion models (commencement -> CCC, n=1,507 schemes, 2,038 phases,
  corrected evaluation, time-only hazard): first-CCC KM median 550d (events
  1,106), dynAUC 0.48@12m -> 0.64@48m; 25% certified median 554d (n=219);
  50% certified median 591d (n=125); final CCC KM median 804d, dynAUC
  0.48@12m -> 0.60@36m.
- Monte Carlo timeline chain (train grant <2020, holdout >=2020):
  decision MAE 84d (coverage 80% interval 69.6%); commencement MAE 386d
  (64%); first CCC MAE 641d (41%); final CCC MAE 975d (41%); first sale MAE
  1,487d (26%). Errors accumulate per leg.
- Route split: private_sale / rental / social / forward_funded from
  description + AHB flags; route-specific sale transitions fitted.
- Developer groups: 475 groups (shared CRO registered address + name-prefix
  clustering). Shrunk group estimates (K=5): activation MAE global 327d,
  SPV-raw 312d, group 317d, shrunk 312d (n=251); sale MAE global 864d,
  SPV-raw 831d, group 887d, shrunk 874d (n=127).
- Appeals split: third-party appeals prevalence 16.2%, AUC 0.647
  (0.615-0.679); applicant appeals 6.7%, AUC 0.623 (0.566-0.675). Combined
  v1 remains 0.659.
- FI label maturity: FI rate stable 0.61-0.63 by received year 2017-2025
  (2024-25 decision-dated rows 0.69). The v2 2025 AUC drop is not label
  immaturity.
- Product-style harness: commencement MAE by developer familiarity - seen
  334d vs unseen 390d (constant train median, n~250 each); unit-weighted
  MAE 440d (unweighted ~365d); calibration by horizon (train vs test
  occurrence dev pp recorded); confidence-sliced MAE by predicted-speed
  quartile recorded.
- Data-quality finding: scheme-level CCC-to-sale is negative-skewed (sales
  frequently precede the scheme's first recorded CCC; median -670d without
  clipping) - phase-level sale attribution is required for that leg.

## 17. Open items (end-of-session state)

- Tranche-2 pulls blocked on endpoints (BER Fingal ArcGIS 403, TED API 400
  query syntax, gov.ie search JS-rendered, excavations timeouts) - retry
  with browser-grade requests or alternate endpoints next session.
- National BER bulk: SEAI research-tool access not registered.
- Phase-level sale attribution (phase CCC -> that phase's sales) not built.
- Event ledger: no downstream consumer yet (multi-state engine v1 consumes
  label pools directly; ledger wiring pending).

## 20. Development-level sale ladder (2026-09-30)

Sanctioned path after the phase-label gate failure: models on the 763
estate-level VERIFIED sales links (spot-checked), eligible routes only,
train grant <2021 (n=194), test >=2021 (n=95). Decisive table:

| Model | MAE | +-100d | +-180d | +-365d |
|---|---|---|---|---|
| Global median | 441 | 10.5% | 20.0% | 41.1% |
| Size-band median | 431 | 12.6% | 18.9% | 36.8% |
| Developer-shrunk | 439 | 7.4% | 20.0% | 42.1% |
| Rolling-24m median | 491 | 10.5% | 22.1% | 34.7% |
| Elastic-net (log) | 425 (95% CI 368-487) | 6.3% | 22.1% | 49.5% |
| Quantile GBM | 462 (404-525) | 12.6% | 27.4% | 42.1% |
| Weibull AFT | 435 | 8.4% | 16.8% | 44.2% |
| Decomposed (comm->CCC->sale, n=71) | 489 | 12.7% | 23.9% | 45.1% |
| High-confidence gate (top 30%) | 467 | - | - | - |

Horizon classifiers (from grant, censored dynAUC): 12m 0.69, 18m 0.64,
24m 0.57, 36m 0.66. Findings: best model improves 1.4% over best baseline
(model gate requires 10%); gating gives no subset benefit; decomposed is
worse than direct. The +-100d objective is not available at development
level from current data; the accurate claims remain the conditional
post-CCC leg (median 34d) and the 12m horizon (AUC 0.69).

## 21. Phase-pilot state (ECAD+phase-maps route)

- Shortlist: 16 multi-phase estates with sales + local PDFs; 9 shortlisted
  (7 authorities). Text probe: zero phasing evidence (drawings, not text).
- iDocsWeb document puller built; blocked: ASP.NET checkbox postback does
  not advance under 3 form variants; 3 of 9 estates expose no iDocsWeb URL
  (agile-applications councils). Parked (site_layouts_pull_state.json).
- Fallback recorded (pack17_processing.json): polygon-free phase inference
  via unit-address + date-burst clustering once ECAD (paid) or SEAI BER
  bulk (free registration, user leg) lands; validation against BCMS
  phase_units; FOI phasing schedules as user leg; development level is the
  sanctioned operating level meanwhile.

## 22. Push-through results (plan items 7-9, 2026-09-30)

- Completion models with features (n=1,559, 1,141 events). IN-SAMPLE:
  morphology lifts first-CCC dynAUC 12m 0.478->0.611, developer 0.656@36m,
  0.689@48m all-families; GBM in-sample MAE 211d vs Weibull 229d.
  TEMPORAL SPLIT (train commencement <2020, test >=2020, n=421/1,138):
  dynAUC 0.45-0.51 for every family and IBS 0.72-1.04 - the in-sample gain
  does NOT transfer (era drift; levels miscalibrated). FALSIFIED
  out-of-sample.
- Sale ladder v2 ablations (out-of-sample, train grant <2021, test >=2021,
  n=95): morphology 506d -> +planning 472d -> +developer 456d -> +market
  471d -> +site 465d (full 465d). Developer family is the only material
  gain. Paired bootstrap full vs size-band baseline: +33.4d (95% CI -19.6
  to 84.8) - no significant improvement over the baseline.
- Gating v2 with the plan's gating features (model disagreement, comparable
  density, developer familiarity, interval width): no subset benefit
  (top30% 473d vs full 465d).
- Meta-pattern across every timing leg to date: in-sample gains, out-of-
  sample nulls, era drift dominates. All remaining plan items are either
  done or blocked on the four external legs (SEAI BER, drawings, ECAD
  sample, FOI).

## 23. AlphaEarth (satellite embeddings) - real-data results (2026-10-01)

Earth Engine integrated (project planning-project-1, GOOGLE/SATELLITE_
EMBEDDING/V1/ANNUAL, bands A00-A63, 2017-2025). Extraction batched: 646
site polygons x 9 years = 5,814 rows (site band means, ring contrast,
per-pixel cosine change mean/median/p90, heterogeneity) in
raw/alphaearth/alphaearth_features.csv.

Three experiments, temporal split (train grant <2021, test >=2021):
- E1 pre-commencement (commencement within 365d): AUC 0.469, Brier 0.2629
  vs base 0.2616 (null). Within 730d: AUC 0.531, Brier equal (null).
- E2 monitoring (CCC within 365d of commencement): AUC 0.564 (n=128),
  Brier 0.2329 vs 0.2348 (marginal, below any decision threshold).
- E3 sale augmentation: MAE 836 vs 813 base (-2.8%, gate 10% FAILED).

Verdict: the FREE ANNUAL embeddings add no measurable signal to any of
the three experiments at current n. Consistent with the design note: 10 m
annual composites cannot date monthly milestones; small phases are
inseparable. The custom weekly/monthly embeddings (commercial preview)
remain untested. Sentinel control comparison moot while AE features are
null.

## 23b. AlphaEarth learned-sensor test (2026-10-01)

Per the learned-physical-state design: dispersion/interior-edge-buffer/
fraction-large-change features extracted per site-year (all 646 sites x
9 years); state labels (greenfield/site_works/active/substantially_built/
completed/stalled) from BCMS commencement+CCC; state classifier + state-
probability curves + satellite-inferred commencement labels + timeline
ablation (same model with/without AE).

Results:
- State classifier accuracy 0.562 vs majority baseline 0.656 (worse than
  "always greenfield"); build-state classes too rare in test era (empty
  probability curve).
- Satellite-inferred commencement: 0 of 137 BCMS-unlinked schemes cross
  the 0.1 large-change threshold (no clean annual signal).
- Ablation commencement: base MAE 349d -> +AE 357d (+-180d 34.1%->29.9%).
- Ablation sale: base 873d -> +AE 879d.

The requested ablation shows the free annual embeddings add NEGATIVE
information to the timeline model. The annual dataset is falsified for
this use under both raw-feature and learned-sensor designs. Custom-window
(weekly/monthly) embeddings remain the only untested AlphaEarth route.

## 24. Plan 2.10.26 implementation (2026-10-02)

Experiments E1-E5 from the plan (professional teams, site lineage, local
pipeline state, developer state, infrastructure readiness).

- E1 professional teams: 5,308 planner PDFs scanned -> 1,148 role-firm
  mentions across 636 PDFs (consultant_mentions.csv). Entity-resolved
  team features (consultant_team_features.csv): prior n, FI rate, appeal
  rate, median decision days.
- E2 site lineage: same-parcel (<=60m) application genealogy; 220/1,095
  pool schemes (20.1%) have prior same-parcel applications
  (site_lineage_features.csv): prior refusals/grants, size change,
  description similarity, days since last decision.
- E3 pipeline state: 1/3/5/10km time-safe features from BCMS+register
  (pipeline_state_features.csv, n=1,095): granted-not-commenced units,
  commenced units, CCCs 3/6/12m, progression ratio, same-type
  competitors, prior apps.
- E4 developer state (developer_state_features.csv, 264 with history):
  live uncommenced schemes, units granted/commenced/completed, authority
  count, recent grant->start/start->CCC medians, size trajectory, type
  familiarity, county expansion, SPV count, dev x authority/type/band
  shrunk medians.
- E5 infrastructure: FSC/DAC national dataset downloaded; Uisce capacity
  register page saved; SDCC road licences located. Integration pending.

Ablation results (2-feature base: log_units + apartment flag; GBM for
regression, logistic for FI; same temporal splits):
- Commencement: base 351d; +lineage 344; +pipeline 339; +devstate 344;
  +team 351.
- Sale: base 2,098d; +lineage 2,099; +pipeline 2,094; +devstate 2,106;
  +team 2,098 (all within noise).
- FI: base AUC 0.438; +lineage 0.484; **+pipeline 0.591**; +devstate
  0.382; +team 0.430.

Local pipeline state is the strongest new signal (+0.153 FI AUC on the
minimal base); team features are flat at current extraction quality
(1,148 regex mentions - extraction refinement is the next step before
concluding on E1).

## 24b. Full-model ablations (production models, 2026-10-02)

Plan families tested as incremental additions on the deployable models
(same protocols; TF-IDF text included where the production model uses
it).

- FI (production-style, with text; base 0.646): +pipeline 0.647,
  +lineage 0.642, +devstate 0.629, +team 0.645. The pipeline gain seen on
  the 2-feature base mostly disappears once description text is present.
- Commencement (production quantile GBM; base 384d): +devstate **360d
  (-24d)**, +pipeline **368d (-16d)**, +lineage **374d (-10d)**, +team
  378d (-6d). All three process/pipeline families survive on the
  production model; devstate is the single largest commencement gain
  measured to date.
- Sale (production ladder; base 425d): +lineage 451d, +pipeline 469d,
  +devstate 431d, +team 425d. Nothing survives - sale ceiling unchanged.
- Appeal (production-style, with text; base 0.660): +pipeline **0.675
  (+0.015)**, +devstate 0.665, +lineage 0.659, +team 0.659. Pipeline
  survives on appeal too.
- Decision timing (base 77d): lineage/team flat (77d).

Kept: pipeline (appeal +0.015, commencement -16d), devstate (commencement
-24d), lineage provisional (commencement -10d). Deprioritised: team
(flat everywhere), sale families (no effect). Next per plan order: E5
integration, local absorption for sale, geometry/construction method.

## 24c. Revised-order experiments (2026-10-02)

- Developer-state v2 (recency-weighted histories, live unit load,
  delivery velocity 12/24m, dev x authority/county/type interactions):
  commencement production model base 386d -> +devstate v2 **371d (-15d)**.
  Sale: 417d -> 413d (marginal).
- Local absorption (1/3/5km competing new-build units, CCC flow 12m,
  sales 12m, local median price; built from BCMS + townland-geocoded
  PPR): sale production ladder 417d -> +absorption 428d (worse).
  Falsified at v1 construction.
- Construction method/material (BCMS construction_method, MMC/masonry/
  concrete flags): completion hazard morphology vs +method - IDENTICAL
  dynAUC (0.495/0.530) and IBS. Method coverage is 10.2% of notices.
  Null at current coverage.
- Committed direction: devstate stays (commencement -15d); absorption
  and method need better coverage before re-testing; graph model not
  justified yet.

## 25. Label-quality phase (2026-10-02)

Per plan direction: feature brainstorming stopped; architecture locked
(MODEL_REGISTRY_LOCKED.md); labels attacked.

- Label hygiene fix #1: label builder now excludes verification_status=
  'pending' rows. Verified sales-linked 767 (was 811 incl. pending).
- Label hygiene fix #2 (the big one): build_exit_labels now requires
  first sale >= grant - 90d. Before: 44.3% of exit-label rows had
  NEGATIVE time-to-first-sale (worst -4,527d - older same-named estate
  phases polluting the human-workbook pulls). After: 22.5% within the
  90-day grace only; median tfs -271d -> 155d; 13 schemes lost all
  sales (genuinely pre-grant links, now excluded).
- Final clean temporal evaluation (train <2022, test 2022+ untouched):
  commencement MAE 433d (n=536, +-180d 16.6%, +-365d 37.5%); sale MAE
  386d (n=132) - was 2,125d BEFORE the label fix (-82%). Sale ladder
  retrained on fixed labels: size-band 353d, elastic-net 349d (n=154
  test) vs 413-425d before the fix.
- Conclusion: the sale bottleneck was label contamination, not model
  weakness. The 2022+ clean-eval sale MAE is now 386d and the ladder
  349-353d. Remaining negative rows are within the grace window by
  construction.

## 26. Label-hygiene suite + relabelled retests (2026-10-02)

Permanent suite: tests/test_label_hygiene.py - 8 hard invariants
(activation bounds w/ 180d grace, tfs bounds w/ 90d grace, sale-not-
before-commencement w/ 365d grace, completion non-negativity, final>=
first CCC, no duplicate verified rows, no pending-only linked schemes,
CCC-sale floor). Initial run found 5 violations, all fixed at source:
- activation < -180d treated as link error (pain.py);
- sale filter extended to commencement axis (economics.py);
- t_first_ccc clipped >= 0 (completion builder);
- pending-only schemes excluded from labels;
- 7 phased-scheme CCC-sale offenders exported (audit/ccc_sale_offenders.csv),
  pending phase-level reconstruction.
120 tests green.

Relabelled retests (corrected sale labels, train<2021/test>=2021):
base 339d; +market 350; +developer 339; +lineage 339; +pipeline 348;
+devstate 369; +team 339; +absorption 341. NO family survives on the
corrected sale target - the earlier 'developer helps sale' conclusion
(506->456d) was a label artefact. Developer state remains a commencement
feature only. Decomposed CCC-to-sale median 0d (n=136) - phased-scheme
residual confirmed.

PACK_23 (worst-residual audit: sale + commencement top-50 abs errors,
classification columns) generated for manual review.

## 27. End-to-end error budget (2026-10-02)

CCC-sale feature model (915 blocks, scheme-grouped split 644/271):
GBM 211d vs constant 228d (-7.5%), +-180d 70.5% vs 67.9% - borderline,
frozen as constant unless the GBM gain repeats on a second split.

Error budget (clean cohort, scheme-level, corrected labels):
- grant->commencement: IQR 511d = 54.9% of timeline variance
- commencement->first CCC: IQR 254d = 27.3%
- CCC->first sale: IQR 166d = 17.8%

Decomposed vs direct (sequential conditional medians, n=~300):
decomposed MAE 588d vs direct 564d; +-180d 23.0% vs 19.4%; +-365d 40.3%
vs 36.7%. Decomposition reopened on corrected labels: WORSE on MAE,
better on interval hit rates - mixed, not adopted.

Direction locked: grant->commencement (55%) and construction (27%)
dominate remaining uncertainty; CCC->sale is constrained. Optimisation
moves to the weakest legs; sale attribution drilling stops.

## 28. BER field audit + gate verdict (2026-10-02)

BERPublicsearch.txt (1.56GB, 252 columns) field audit:
- Geographic fields surviving anonymisation: CountyName (county or
  Dublin postal area) ONLY. SA_Code empty for 100% of sampled rows;
  no address, eircode or coordinates.
- DateOfAssessment present; TypeofRating = Existing/Final/Provisional;
  PurposeOfRating includes 'New dwelling for owner occupation'
  (76,347 rows in compact subset); full dwelling characteristics.
- MultiDwellingMPRN: 0.7% filled and collapses to a single value -
  unusable as a development key.

Gate test:
- MPRN cluster matching: 0 scheme matches.
- County-year wave corroboration of CCC dates: 0/1,106 schemes within
  180d (county waves are the earliest new build in the county-year, not
  per-scheme events - no geography makes individual corroboration
  impossible).

VERDICT: BER Public Search FAILS the completion-label gate. Dropped
for label purposes (kept as aggregate county-year context only). The
completion-observation route now depends on ECAD (addresses + dates)
and FOI (ESB energisation / Uisce connections).

## 29. Graph layer + B-tier knock tests (2026-10-02)

Entity graph data layer built: 3,552 nodes (apps 1,095, parcels 1,095,
SPVs 765, developers 540, consultants 32, authorities 25), 4,242 edges
(located_in, on_parcel, applied_for, belongs_to, same_developer_next,
has_prior_applications, advised, worked_with). graph_nodes.csv +
graph_edges.csv.

B-tier features + ablation (commencement, train<2022/test 2022+):
- Full B-tier pack: base 293d -> 258d (-35d).
- Subfamilies: +CRO 264d (-29d) WINNER; +land_cover 284d (-9d);
  +doc_complexity 299d (worse); +workload-by-type 305d (worse).
- FI: 0.431 -> 0.451 with the pack (modest).

Knock verdicts: CRO group-age/dissolution features survive for
commencement; document complexity and authority workload-by-type are
knocked down; land-cover marginal. Graph layer is data-only - its
interaction signal is already captured by devstate/CRO features, so an
explicit graph model remains unjustified.

## 30. CRO financial statements - schema audit + ablation (2026-10-02)

Open datasets (2022/2023/2024): 556,363 filing rows, 255,963 companies.
SCHEMA VERDICT: filing metadata only (file_name, company_num, submission
rec/eff/reg dates, accounts-to date). NO balance-sheet line items -
assets/cash/equity/turnover/leverage are NOT in the open data.

Join by CRO number (exact): 520/520 crosswalk companies matched,
920 schemes with filings. Time-safe features built from filing dates:
prior filing count, recency, accounts-to lag, 24-month dormancy.

Ablation (commencement, frozen protocol, n=685/142): base 293d ->
+FS 294d (+1d, CI overlapping). No incremental value.

VERDICT: DROP. Balance-sheet features unavailable in open data; the
filing-metadata features that are time-safe do not move commencement.
Event ledger: existing schema (development_id, phase_id, event_type,
dates, source, source_reference, units, status, confidence,
observed_or_inferred) accepts HSA/NBCO/ESB/Uisce/CSO/ECAD events
unchanged - no parallel architecture.

## 31. Todo-sprint (2026-10-02): graph, geometry, live model, pulls

- GRAPH MODEL (learned features: pagerank, degree, developer hub/siblings,
  consultant degree): commencement base 293d -> 278d (-15d, CI does not
  include base); FI 0.431 -> 0.525 (+0.094). JUSTIFIED - the plan's
  condition for a graph is met. graph_model_features.csv.
- Parcel geometry (area/perimeter/compactness/frontage/elongation from
  646 site polygons): commencement -3d. Knocked (static physical
  descriptors, as predicted).
- LIVE UPDATING MODEL: remaining-time snapshots at each landmark -
  at_grant width 1,611d -> after_commencement 1,074d -> after_first_CCC
  (event-level attributed) median 216d, width 976d. Uncertainty collapses
  per landmark; live_updating_snapshots.json.
- Background pulls relaunched: SHCSR PDFs (gov.ie), Uisce county capacity
  pages (first 10), excavations search page.

## 32. Backlog sprint #2 (2026-10-02)

- Flood-depth magnitudes (data in hand, 100% coverage): commencement
  -2d. Knocked (hit/distance flags already carried the signal).
- Uisce county capacity status (10 counties, 24.7% scheme coverage):
  commencement **-10d**. Kept provisionally; full 28-county parse
  running (uisce_county_status.csv).
- Archaeology events (SMR bulk 151,308 sites, site-polygon join, 35.3%
  coverage): -2d. Knocked (nearest-distance already captured it).
- Feature-snapshots table built from the event ledger (feature_snapshots
  .csv: 1,813 schemes x landmark dates) - the snapshot substrate.
- In flight (background): OSM road-class/junction + amenity context per
  estate, generalised-zoning MapServer probe, remaining Uisce counties.
- SHCSR: page fetched, 0 PDFs - link-pattern fix pending.

## 33. iDocs two-step unblock + condition-level parse (2026-10-03)

The "blocked" scanned-files viewer (iDocsWebDPSS) was never server-side
broken: it needs TWO steps - tick chkAgree AND press the second button
btnViewFiles ("View Files") on copyright.aspx. Flow: copyright.aspx ->
chkAgree -> btnViewFiles -> listFiles.aspx (Document Type | Comment |
# Files) -> ViewFiles.aspx?docid=X -> iframe ViewPdf.aspx?file=UUID.pdf
or ViewDPSSFile.aspx (djvu tiles: dpsserv.dll/docs/UUID.djvu/page=N;
zoom=50). Every ePlan council runs the same system on its own host
(discoverable from AppFileRefDetails pages); 18 councils iDocs-capable.

Condition-level parsing of the 5,308 local planner PDFs: only 7 contain
parseable FINAL condition blocks - the corpus is FI requests/screening
reports, not decision orders. The real condition texts live in the
iDocs scanned files.

Pulled in-session: ledgers + grant/CEO-order/schedule PDFs for 28/48
forensics schemes (Wicklow native text 36-52k chars; Waterford 163k;
Tipperary 46-68k; djvu tiles OCR'd). Condition parser handles native
text (Wicklow 'l.' for '1'), space-less OCR (Waterford '1.(a)X') and
page-footers. condition_forensics.csv + report.

FORENSICS RESULT (n=7 Wicklow matched pairs, clean native schedules):
condition burden does NOT separate fast/slow commencement residuals
(fast: 29 conditions / 11 pre-commencement / 6 financial; slow: 35 /
8 / 5.5). The 350-500d gap is not explained by what planners wrote.

Side win: ledger rows (bond/contribution correspondence, per-condition
approval letters) are a free compliance-event ledger (silver/idocs/).

## 34. Readiness clocks, date recovery, landmark gate (2026-10-04)

Validation cohort: 90 schemes (30/30/30 fast/mid/slow by commencement
tercile, 11 iDocs councils, grant 2020-2023, >=5 units); 72 pulled,
16 portal-errors (Offaly/Galway City/Mayo lack chkAgree), 2 killed.
Date recovery: 17.4% -> 85.4% of 2,727 docs dated (Date:/Dated:/RECD/
Sent labels, glued OCR '16thFebruary2022', L->1 O->0, month abbrevs,
email Sent headers). Audit sample: date_audit_sample.csv (unverified).

Retrospective clocks (n=70): grant->first activity fast 76 / mid 114 /
slow 677d; grant->first accepted 123/173/724d; last pre-comm clearance
-> commencement 35/30/45d. Slow schemes sit dormant ~2 years; the
post-clearance tail is NOT where slow differs.

LANDMARK GATE (user's rule, unchanged thresholds, n=70, observability
fixed): activity observed by t=30/60/90/180 does NOT improve forward
commencement. t180: accepted-by-180 median remaining 406d vs no-activity
383d; next-365 44.1% vs 44.4%. Flat/inverted - early letters come from
big slow schemes, small fast schemes start with no dated correspondence.
VERDICT: compliance activity DROPPED as a live predictor.

Day-zero grant->first-accepted model (train 36/test 21): base C-index
0.647; +time-safe developer mobilisation scores 0.583 (zero-filled
histories learn availability, not behaviour) - NOT established.

## 35. Economic-state hazard + builder audit (2026-10-05)

GRANT->COMMENCEMENT ECONOMIC STATE MODEL: monthly panel 696 schemes /
13,251 scheme-months (test 2023+, 3,145 rows); discrete-time logistic
hazard -> chained P(within 1/3/6/12m). Free macro series fetched
(silver/macro/): CSO HPM09 RPPI to 2026-07 (HPM01 stale 2019 - do not
reuse), WPM28 building-materials WPI 2015-2024 (WPM12/WPM23 stale),
PPR county new-dwelling price/volume/momentum 94% coverage.

Family ablations (standalone, temporal split): cal AUC h1 0.490/h12
0.490; econ 0.404/0.420 (worse); dev 0.492/0.490; pipe 0.502/0.456;
frozen smooth-CDF benchmark AUC 12m 0.512 (n=200). ALL AT CHANCE.
ECB/CentralBank DNS unreachable - finance family pending (not expected
to change the verdict; rates are shared, no cross-scheme info).

BCMS builder audit: open BCNCCC dataset has NO builder/assigned-
certifier fields (99 technical columns) - builder history NOT
recoverable. VERDICT: monthly start hazard not predictable from
economics/developer workload/local pipeline; dormancy is private.

## 36. Final observability audit + state-machine transitions (2026-10-05)

Audited 48-scheme fast/slow cohort for public traces of project-
specific readiness (ledgers + texts + register): landowner consent/
identity, demolition, phasing, utility refs, contractor names, tender,
forward-purchase/AHB, sales launch, amendment, FI, appeals. All flat or
noise; only FI request separates (fast 66.7% vs slow 87.5% - pre-grant
complexity, already known). Landowner name coverage 4%; landowner-vs-
applicant 0%. observability_audit.csv + report.
VERDICT: exact day-zero commencement timing has a genuine information
ceiling from public data - private decisions leave no pre-start trace.

State-machine transitions (data already held):
- BCMS notice filing -> site start: median 14d, IQR 13-16d, 99.4% <=
  28d, 99.8% <= 60d (n=248,947). Near-deterministic late transition.
- FSC first-submit landmark (n=91, thin): at t180, filed 42.9% commence
  next 180d vs 20.6% not-filed - directional, n_filed=7, provisional.
- Post-commencement stages (CCC->sale etc.) already have real
  event-level structure.

PRODUCT VERDICT (user-agreed): per-deal commencement timing is industry
knowledge for insiders (lenders sit inside the information wall) - not
a product advantage. Kill the commencement-timing product line; keep
the frozen model honest with wide timing intervals. Concentrate on the
pre-grant surface (refusal risk, decision timing, precedents/evidence,
conditions/FI) where the information advantage genuinely is.
state_machine_transitions.json; handoff updated; 120 tests green.

## 37. Canonical state machine + transition tables (2026-10-05)

Sprint pivot: development intelligence / state-estimation engine (user
brief: "given everything publicly observable at a date, what state is the
scheme in, what are the plausible next states, and what can we defensibly
say about their timing/probability").

Built: silver/state_machine/states.csv (9,098 state rows, 1,095 schemes),
current_state.csv (state, entered date, days_in_state, last event, source,
observed_or_inferred, confidence, next_possible_states). Observed states
from register/BCMS/CCC/PPR with grant-consistency guards (BCMS link table
contains stale 2014 commencement dates for 2022 grants - fixed; labels
activation used as corroborating commenced source). Dormant_granted is
inferred-from-absence and flagged as such; never conflated with observed.

Transition distributions (empirical, n / median / IQR / within 3-6-12m):
- final_grant -> notice_filed: n=430, median 360.5d (12m 50.9%)
- final_grant -> commenced: n=944, median 433.0d
- notice_filed -> commenced: n=531, median 14.0d (3m 90.2%)
- commenced -> first_ccc: n=880, median 498d
- first_ccc -> partial_ccc: n=858, median 297.5d
- partial_ccc -> final_ccc: n=676, median 0d (3m 91.9%)
- first_ccc -> final_ccc: n=760, median 292.5d
- commenced -> final_ccc: n=662, median 851d

Uncertainty reduction (first-class product metric, remaining-time width):
grant: median 406d, 80% width 1,340d -> notice filed: median 14d,
80% width 38d -> commenced: median 478d to first CCC, width 780d ->
first CCC: median 282d to final, width 1,296d -> final CCC: ~0d to sale.
The notice-filed landmark collapses the 80% interval from 1,340d to 38d.

Negative-result registry: silver/experiment_registry.json, 26 experiments
(5 keep, 2 provisional, 13 falsified, 6 blocked) with hypothesis, data,
prediction time, protocol, baseline, metric, result, CI, verdict, reason,
revisit conditions.

Product prototype: silver/state_machine/reports/report_*.md for two
Wicklow schemes - current status, what happens next, calibrated timing,
evidence, change log, confidence, unknowns (explicit when the engine
cannot distinguish). Governing rule: never imply day-level precision.

## 38. Label quarantine + shadow deployment (2026-10-05)

Quarantine layer: silver/dq/quarantine.csv (3,932 rows, rules R1-R10),
data_quality_report.json, labels_clean.csv (491 clean schemes after
excluding 494 blocked + 137 pending). Rules: impossible ordering (R1),
sale >365d pre-commencement (R2), pre-grant sale (R3), duplicate PPR
attribution (R4, 2,641 rows/65 schemes), same-name contamination (R5),
low-confidence BCMS links (R6), phase inconsistencies (R7), CCC
sequencing (R8), pending leakage (R9), impossible dates (R10). Blocking
rules exclude downstream; warn rules surface for review. Verified
coverage: activation 958, sales 746, completion 815. 6 new invariants
in tests/test_quarantine.py - clean view never contains blocked/pending.

Shadow deployment: devrisk/shadow.py append-only write-once log seeded
2026-10-01 with 820 frozen state-machine v1 predictions (next-transition
empirical distributions for every clean scheme-state pair). Outcomes fill
as events are observed; scoring = MAE/coverage/horizon hits. Write-once
enforced by prediction_id collision raise; tests/test_shadow.py (4 tests).
Suite: 130 tests green.

Interrogation of 1,340d -> 38d -> 780d uncertainty profile (user): the
notice filing resolves whether commencement is imminent; construction
opens a NEW uncertainty regime (480d to first CCC, 780d width). Implies
per-state models/covariates, not one master timeline - reflected in the
per-transition tables; the construction leg is the next research target
(progress-based completion states: % certified milestones).

## 39. Progress-based completion states (2026-10-05) - KEEP

Event-level CCC histories for 330 clean commenced schemes (6,861 events,
99.3% with unit counts; 4,079 same-day duplicate events flagged; 40 over-
certified, 122 under-certified final; 108 phase-ambiguous). Snapshots at
0%/first CCC/25/50/75% + after every CCC (7,191 rows).

KEY ABLATION (elapsed-only vs +progress, temporal split comm<2022 train /
>=2022 test, scheme-grouped, n=4,914/2,277):
- elapsed-band median (best simple baseline): MAE 182.3d
- GBM elapsed-only: 214.9d
- GBM elapsed+progress (cum_pct, n_ccc, velocity, units_remaining): 160.9d
  (-25.1% vs elapsed-only; -11.7% vs best baseline) -> PASSES the >=10% gate
- +scheme descriptors: 184.6d (worse) -> descriptors falsified
- quantile regression progress: 185.9d
- horizon AUC (within-12m-final, progress-model score): 0.738 (n=2,277)

Uncertainty reduction (80% remaining-time width): commenced 1,440.9d ->
25% 995.4d (-30.9%) -> 50% 817.2d (-43.3% cum; -17.9% vs prev) -> 75%
613.0d (-57.5%; -25.0% vs prev). Gates: 25% and 75% pass >=20%-vs-previous;
50% passes cumulatively. First useful landmark: 25%.

Survivorship decomposition: both effects real - state reached (median
remaining collapses) AND progress-rate (fast vs slow to reach: pct25 258
vs 376d; pct50 148 vs 229d; pct75 48 vs 80d; within-12m 62.6 vs 49.2% at
pct25).

INTEGRATED: pct25/pct50/pct75 added as observed states to the state
machine (states.csv, 9,904 rows), transition pairs added (commenced->
pct25, pct25->pct50, pct50->pct75, pct75->final_ccc etc.), shadow log
extended to 1,276 frozen predictions (write-once, append-only).

VERDICTS: (1) YES physical progress materially reduces uncertainty
(-57.5% width by 75%); (2) first useful at 25%; (3) YES % certified is
genuinely informative beyond elapsed time (+25.1% ablation); (4) ML beats
conditional empirical baselines on this split (160.9 vs 182.3, -11.7%,
passes gate; caveat single temporal split, n_test 83 schemes - needs
rolling-origin confirmation before production); (5) 25/50/75% enter the
engine as observed landmarks; (6) the pre-25% construction leg remains
wide (1,440d) - still the unpredictable regime.
Artifacts: silver/construction_progress/{events,snapshots,quality,
models}.json/.csv; registry updated (29 experiments).

## 40. Golden development replay (2026-10-05) - engine audit

30 stratified schemes (speed x type x size, ugly/sparse included, criteria
fixed pre-outcome), 660 snapshots, 922 predictions, 352 scored outcomes.
Time-safe: transition stats recomputed at every replay date from
transitions completed by then (5y source window); leakage assertions.

Interval calibration (nominal vs actual): 50% -> 37.2%, 80% -> 62.8%,
90% -> 73.0% - the product estimator UNDER-COVERS. MAE 306.6d.
Methodology findings: (1) naive expanding quantiles censoring-biased
(falsified); (2) windowed censoring-corrected KM inflates medians via
dormant-tail censored mass (falsified); (3) completed-only recent-window
quantiles under-cover - engine needs a censoring-corrected recency-window
estimator + calibration adjustment before production.
Information gain in replay: notice->commenced width -99.9%; commenced->
25% -88.2%; 25%->50% -63.9%. Failure taxonomy (99 misses >365d): 68
model/estimator + 31 linkage (31% non-model). Anomalies: 10 median-
moves-backwards, 8 interval-widens-no-regime, 0 inferred-as-strong.
VERDICTS: partially sensible (ordering + medians ok; intervals and
stability need work); notice + 25% are the top information events;
understate grant->commencement and n<20 estimates; progress model
survives replay; before production fix estimator calibration + suppress
backwards medians + keep quarantine upstream.
Artifacts: silver/replay/{golden_cohort,replay_snapshots,replay_
predictions,replay_outcomes,replay_anomalies,replay_information_gain,
replay_failure_taxonomy}.csv + dossiers/ + replay_report.md; registry 33
experiments.

## 41. Calibration, linkage dissection, rolling origin (2026-10-05)

CALIBRATION SPRINT (user priority 1; judged on out-of-time coverage):
n=887 time-safe replay outcomes across 4 eras.
- V0 completed-only empirical quantiles UNDER-COVER every era: 50%
  interval hits 26.9-38.1% (nominal 50); 80% -> 51.2-68.5%; 90% ->
  59.4-78.2%. FALSIFIED as production estimator (censoring bias).
- V2 recency-weighted: no better (falsified). V3 capped-KM: degenerate
  0% (falsified).
- V1 conformal quantile expansion (calibrated on previous era, applied
  out-of-era): cov50 42.9-56.9, cov80 48.6-92.0, cov90 92.0-100 -
  near-nominal and transfers eras. KEEP: conformal recalibration is the
  production fix route (silver/calibration/).
LINKAGE DISSECTION (user priority 2): all 31 replay linkage failures
attribute to PHASE structure ambiguity (100%). Fix = phase-aware
denominators for cumulative % certified; never mix phase and scheme
CCCs. (Duplicate-PPR queue is the largest quarantine volume but did not
drive replay misses - quarantine already blocked those.)
PROGRESS ROLLING ORIGIN (user priority 3): progress-GBM MAE gain vs
elapsed-band median by period: 2020-21 +19.4%, 2021-22 +21.1%, 2022-23
+12.6%, 2023-24 -3.1%. Gain erodes and FAILS the latest period.
VERDICT: empirical progress-conditioned tables remain the product; the
ML edge is provisional pending recent-era re-evaluation when more
completions mature. Registry now 39 experiments (10 keep / 4
provisional / 19 falsified / 6 blocked).

## 42. Harden/freeze sprint + ENGINE v1 freeze (2026-10-05)

1. PER-TRANSITION CONFORMAL CALIBRATION (silver/calibration/per_transition
   _calibration.json): each production transition calibrated separately,
   rolling out-of-era. Most pairs ship (worst out-of-era coverage at or
   above nominal); safety-widened: final_grant->notice_filed 90,
   final_grant->commenced 90, notice_filed->commenced 50/80,
   commenced->pct25 90, first_ccc->final_ccc 80/90. No transition ships
   with materially optimistic coverage.
2. PHASE-AWARE DENOMINATORS: BCMS CN_Units_for_phase (per scheme-phase
   median, duplicate notices deduped) replaces scheme denominators;
   192/330 progress schemes phase-resolved; R11 warn rows surface
   unresolved structures. 25/50/75% info-gain SURVIVES phase cleaning:
   widths 1,317d -> 984 -> 733 -> 556 (median 857 -> 300 -> 200 -> 49).
3. ANOMALY SUPPRESSION: backwards-moving medians suppressed ONLY when no
   new event occurred between snapshots (state-change forecast moves are
   legitimate); contradictions flagged, never silently repaired. Replay
   anomalies 18 -> 9 (all interval-widens, flagged).
4. CONDITIONS PREDICTOR: conditions_precomm_v0 frozen to shadow (319
   predictions, provisional flag, NOT in product reports); promotion
   trigger = second validation confirming AUC ~0.71.
5. FREEZE MANIFEST: docs/ENGINE_V1_FREEZE.md (production claims,
   provisional outputs, blocked/falsified registry, versions,
   calibration guarantees, limitations, reopening triggers).
Registry 46 experiments; 130 tests green.

## 43. Moonshot Sprint 1 - optionality surface, frontier, fragility, greeks (2026-10-05)

Frozen-model perturbation harness (100 schemes x 6 unit multipliers x 2
mix + 8 description rewrites):
- OPTIONALITY SURFACE (units): median refusal p IDENTICAL (0.2607) at
  0.5x-2.0x units; marginal risk 0.0pp; gradient p50 0.013pp/10 units.
  Comparable-bucket smoothing -> no units-axis cliff edges. FALSIFIED.
- OPTIONALITY SURFACE (description): reduced-density wording -1.86pp
  median (79% of schemes improve); amenity-space wording +1.58pp (model
  artifact); change-of-use bimodal (-7.3/+4.5pp). Effects 1-4pp - no
  commercial cliff-edge product. PROVISIONAL.
- EFFICIENT FRONTIER: flat in units - "105-118 units efficient" headline
  does not exist in this model. FALSIFIED.
- FRAGILITY: degenerate over units (98/100 robust); real fragility axis
  is description-sensitivity. FALSIFIED as specified.
- GREEKS: derivatives ~0 (units) / 1-2pp (description), stable but
  uninformative. FALSIFIED as standalone output.
Verdict: frozen model is calibrated-but-smooth; cannot generate
optionality products. silver/sprint1/*.

## 44. Moonshot Sprint 2 - refusal->grant mutation + rescue plan (2026-10-05)

- MUTATION ENGINE (11,102 same-site refused->later pairs, KD-tree 150m,
  chronological, jaccard revisions vs replacements, temporal holdout
  <2021/>=2021): conversion deltas - units_reduced 18.9% vs 9.5%;
  second-description length ratio 1.12 vs 1.83 (trimming helps);
  keeping route helps (type_change 17.2 vs 22.9); ADDING new technical
  language anti-associated (access 2.0 vs 8.4%; drainage 2.3 vs 9.5%);
  theme-specific reversals (design-refused: access_added 15.4 vs 11.4).
  Conversion logistic AUC 0.958 (caveat: refile/era effects -
  univariate deltas are the defensible core). KEEP.
- MINIMUM-CHANGE RESCUE (recs frozen <2021, evaluated >=2021): grant
  rate by recommendations matched 0/1/2/3/4 -> 0.0/1.7/5.6/18.7/24.9%
  (monotone, ~15x spread); R2 keep-route / R3 trim / R4 no-new-technical
  all differentiate. KEEP (correlational wording).
silver/sprint2/*. The non-obvious finding: "adding technical language
after refusal is statistically useless; trimming and reducing is what
historically converts."

## 45. Moonshot Sprint 3 - hidden planning structure (2026-10-05)

Substrate: 9,095 site clusters / 27,209 apps; expanding-window
observable-difficulty GBM (frozen model substituted for scale -
recorded deviation).
- E1 LATENT SITE DIFFICULTY: time-safe shrunk site effects +0.005 AUC
  on known-site holdout (leaky version +0.063). Site effect identifiable
  (orthogonal to observables, r=0.016) but does NOT transfer ->
  FALSIFIED. "Difficult site / well-adapted proposal" language
  unsupported.
- E2 DEVELOPER ALPHA: BLOCKED (0 overlap developer-linked apps x
  site-cluster frame).
- E3 COUNCIL REGIME: Kildare -13..-36pp from 2021Q3, Wicklow -20..-39pp
  from 2022Q3 (more permissive than expected), Fingal +5..+15pp;
  quarter autocorr 0.333; unexplained by partial policy table.
  PROVISIONAL (descriptive).
- E4 PRECEDENT HALF-LIFE: taus 0.5-10y all AUC 0.913-0.916 vs equal
  0.906 - NO meaningful decay. FALSIFIED (learned age-weighting
  unjustified; old precedents stay informative).
- E5 REVEALED-VS-WRITTEN POLICY: deferred (feasibility note; policy
  table seeded).

## 46. Moonshot Sprint 4 - paths, tail risk, condition burden, clean outcome (2026-10-05)

- E1 PLANNING PATHS (274,586/107,619; 6 paths): joint multinomial
  log-loss 1.1106 vs stratified baseline 1.1731 -> path framing adds
  calibration beyond components. KEEP.
- E2 TAIL RISK: >6m-decision flag prevalence 11.1%, AUC 0.680 vs
  refusal-only 0.517 (+0.163) -> KEEP. >12m prevalence 0.4%; 18/24m
  tails empty in data (decisions resolve fast).
- E3 CONDITION BURDEN: pre-commencement rolling-origin AUC
  0.747/0.765/0.714 (3 cutoffs) -> PROMOTED from provisional. Financial
  0.688/0.633/0.658 -> stays provisional.
- E4 CLEAN OUTCOME (grant & no FI & no appeal & <=12m): prevalence
  0.551 vs grant 0.882; only 62.4% of grants clean; corr(clean_pred,
  grant_pred) 0.355; AUC 0.64, Brier 0.2317 -> KEEP. "82% permission
  but 34% clean" statements supported and distinct from refusal.
silver/sprint4/*.

## 47. Moonshot Sprint 5 - supply, option calculator, novelty, fingerprint (2026-10-05)

- E1 DELIVERABLE SUPPLY (80 catchments x 4 radii x 4 horizons): state-
  conditional aggregation beats county conversion baseline +9.4..+43.6%
  MAE (grows with horizon), beats nominal -45..-56%. KEEP - aggregation
  rescues individual timing weakness; no individual date claims.
- E2 OPTION CALCULATOR: assumption-labelled EV grid; option dominates
  unconditional; unconditional EV negative at low p_grant -> planning
  inputs change acquisition decisions. KEEP as calculator infrastructure
  only.
- E3 NOVELTY: corr(novelty, abs_residual) -0.002; low-novelty apps have
  HIGHER residuals (0.272 vs 0.122); route-to-familiarity -0.82pp on
  7.6% -> FALSIFIED (precedent-count display remains).
- E4 FINGERPRINT + INTEGRATION BACKTEST (25 apps): refusal-flag
  correctness 88%; mean abs residual 0.205; no unified latent score
  (site/team components falsified/blocked) -> KEEP as presentation layer.
PROGRAMME TOTAL: 63 experiments (19 keep / 8 provisional / 27 falsified /
9 blocked).

## 48. Product phase - measurement spec + bound tables (2026-10-05)

- Right bound per component (docs/PRODUCT_REPORT_SPEC.md +
  silver/report/bounds/report_bounds.json):
  refusal/clean/tail/paths -> LOCAL CALIBRATION BANDS (predicted-band ->
  observed rate + Wilson 95% CI); pre-commencement -> rolling-origin AUC
  range + Wilson on family prevalence; rescue -> Wilson per match count
  (3 matched 18.7% [16.2,21.5]; 4 matched 24.9% [22.8,27.1]); supply ->
  Monte Carlo intervals + coverage; option -> sensitivity grid;
  fingerprint -> weakest component's bound, no aggregate score.
- Display rules: no point probability without band; rare events
  collapsed; correlational wording mandatory; support counts everywhere;
  explicit "cannot say" lines.
- Next: 11-section report generator; blind historical case studies
  (30-50 schemes); customer interviews (four questions).

## 49. Zero-day stats - six new report components (2026-10-06)

All from held data, submission-time, no new models
(silver/report/zero_day/*):
1. REFERENCE-CLASS KNN RATE: nearest 15 same-authority neighbours by
   size/type; raw rate + Wilson CI as a second independent voice next to
   the model. Divergence flag (>15pp): flagged 19% of 35,136 test apps.
2. TWO-DIMENSIONAL CALIBRATION BANDS (predicted x auth-group x type,
   n>=15, fallback 1D): sd of cell deltas 16.3pp; Dublin apartments in
   low deciles +21-23pp above decile; max cell delta 73.5pp.
3. ULTIMATE-SUCCESS PROBABILITY: P(grant) + P(refused)*P(resubmit)*
   P(convert|matched rescue) with beta-propagated intervals; gains to
   +6pp at 35% refusal risk.
4. ABANDONMENT BASE RATE: 41.0% [40.5, 41.5] of refused apps never
   resubmitted within 4 years (n=40,172, matched cohort; the earlier
   29.2% came from a different population - corrected).
5. DRAFTING-ASSOCIATION TABLE (zero-day framing of sprint-2 deltas):
   trimmed description 91.5% vs 66.9%; kept route 82.8%; no new technical
   language anti-associated.
6. STATIC AUTHORITY/TYPE BASELINES: fixed rates + Wilson CI vs national;
   ranked cells.

## 50. Confirmatory pass + demo report (2026-10-06)

CONFIRMATORY PASS (silver/report/confirmatory/*) - the discipline
applied before anything ships:
- DIVERGENCE FLAG: AUC headline does NOT replicate (0.637 vs 0.657 on
  re-run; direction inconsistent across fresh eras). Residual-inflation
  direction DOES survive every era (flagged mean error +10-25%).
  DOWNGRADED: "higher expected error where the voices disagree", not
  "model unreliable". Generalization replicates as error-inflation:
  clean-path model-vs-nn Brier 0.151 vs 0.117 flagged/unflagged;
  refusal-vs-static residual 0.452 vs 0.194.
- 2D CELLS: stable at n>=15 through n>=50 (73.5pp max delta unchanged).
  Not small-n artifacts.
- COMPOUND POPULATIONS: mismatched (41.0% vs 29.2% abandonment across
  cohorts) - re-derived on the matched cohort; assumption stated.
- MUTATION FRESH ERA (2019-20): description-trim survives (1.03 vs
  1.53); units-reduction FLIPS sign -> demoted.
- RESCUE PLAN FRESH ERA: 0/1.2/4.5/17.4/21.0% vs original 0/1.7/5.6/
  18.7/24.9% - monotone shape survives. Strongest confirmed result.
DEMO REPORT (silver/report/demo/report_SD17A_0397.md): full 18-section
bounded underwriting report for a real 85-unit SDCC scheme frozen at
submission (2018-04-18), models trained strictly pre-submission, every
number carrying its band/CI/support. Key lines: refusal 27.9% (band
15.3% [14.3,16.4]); reference-class 26.7% [10.9,52.0]; FI 64.6% (band
47.5%); appeal 41.6% (band 15.8% - the band exposes the miscalibration);
clean 13.6% (band 40.7%); 6m tail 0.3%; ultimate success 82.9%
[75.4,88.9] at 4 rescue matches; supply 3km 24m: 2,935 nominal ->
1,475 expected [1,044-1,957 80%]. Dossier vs actuals: granted in 22
days, FI occurred (predicted), no appeal (over-predicted - flagged by
the band). Bands are not decoration: they surface where point estimates
are soft. Next: blind 30-50 case-study batch.
