# Timing Accuracy Brief — facts on milestone-date prediction

Date: 2026-09-30. Contents: measured accuracies, data inventory, model
experiments and their measured outcomes, variance decompositions, and the
current state of known additional data sources.

---

## 1. What is being predicted

Residential schemes (10+ units, national, grant-years 2016–2022 pool of
1,113 schemes unless stated). Targets: decision date, commencement date,
completion (CCC) date, first-sale date, sale price. Prediction time:
immediately before submission for decision/FI/appeal; at grant date for the
downstream legs (the models are conditioned on grant).

## 2. Measured accuracy (temporal holdouts, out-of-sample)

| Milestone | Predictor | Protocol | MAE | Hit rates |
|---|---|---|---|---|
| Decision date | GBM quantiles + monotone CDF | train received <2024, holdout >=2024, n=433 | 63.9d | pinball-p50 32.0 (constant 43.3); horizon AUC P(>6m) 0.755 (0.688–0.815) |
| Grant -> commencement | rolling 24-month median | train grant <2020, holdout >=2020, n=494 | 366d (95% CI 338–397) | ±90d: 15.5% · ±180d: 34% · ±365d: 65% |
| Grant -> commencement (naive strata) | authority-year strata | same holdout, n=494 | 512d (98% CI 450–577) | — |
| Commencement -> CCC | constant median (483d) | n=1,180 events | 241d | ±90d: 32% · ±180d: 57% · ±365d: 86% |
| Grant -> first sale | GBM median | train grant <2021, holdout >=2021, n=101 | 473d (95% CI 422–527) | ±180d: 19% · ±365d: 38% |
| CCC -> first sale (conditional) | conditional distribution | n=2,021 CCC events | median 34d | ±180d: 60% · ±365d: 74% |
| Price vs same-county contemporaneous median | benchmark percentile | n=582 priced schemes | median deviation €65k (26.9%), mean €442k, p80 €153k | — |

Interval calibration (smooth CDF, bin-free quantile coverage):
commencement 80% interval mean width 1,135d, empirical coverage 83.2%
(GBM smooth: 1,155d @ 74.6%); sale 80% interval 1,485d @ 83.5%.

## 3. Data inventory (current state)

| Source | Rows/coverage | Fields used for timing |
|---|---|---|
| NPAD register | 491,760; GE10 3,585; grant dates 53%, decision 3,189 | decision/grant dates, FI, appeal; ApplicantForename/Surname/Address present but empty in all layers |
| BCMS (national building control) | 249,127 events; 83.8% of mature pool linked (confirmed) | commencement date, proposed end date, CCC date + type (full/partial/some-buildings), phase number (86.7%), total phases (86.7%), S11, units |
| PPR | 807,724 transactions; 763 pool schemes linked (55.1%) | sale dates, prices |
| ePlanning pages | 1,595 scraped (1,595 attempted, 0 failed) | applicant names: 1,590 rows, 1,020 entities; 765/1,113 pool schemes (68.7%) covered; 213 with a prior track record |
| CRO companies snapshot | 825,177 companies | 994/1,590 applicants (62.5%) matched to company numbers; status, dissolved date, NACE, address available |
| 4Dublin pipeline | 25,345 records; 2,366 latest-quarter Dublin records | completion corroboration for 268 Dublin schemes (12,878 units); JR evidence; FI/appeal flags |
| Constraint layers | NIAH/WWTP/traffic points, Natura polygons, flood per-scheme | proximity features |
| TimesFM-2.5 forecasts | 83 county series, 12-month horizon | county PPR volume/price and BCMS commencements |
| Event ledger | 17,330 events, 1,813 developments | planning/FI/appeal/commencement/CCC/sale as dated events |
| In-flight downloads | SHCSR PDFs, TED awards, BER Fingal, excavations probe | not yet parsed |

## 4. Model experiments — measured outcomes

Same temporal-holdout protocol throughout. Numbers are point estimates with
95% or 98% CIs as stated; n refers to holdout rows.

**Refusal (frozen v4, read-only):** AUC 0.792 (n=35,713, 2024–25); 2025 slice
AUC 0.793 (0.778–0.807); calibration mean absolute error 0.9pp across decile
bins (max 5.5pp); GE10 AUC 0.782.

**FI:** v1 (pain pool) AUC 0.688 (0.626–0.746, n=363), AP 0.840. v2 (full
GE10 register, GBM, n=1,731 holdout): AUC 0.691 (0.668–0.716); by year 2021
0.721, 2022 0.733, 2023 0.683, 2024 0.719, 2025 0.578.

**Appeal:** v1 AUC 0.659 (0.621–0.698, n=1,729). v2 (added prior appeal
rates, density, site, covid, GBM; tuned on 2019–2020): AUC 0.657
(0.626–0.687). Authority dummies degrade AUC (measured, not used).

**Commencement timing:**
- 19-quantile GBM smooth CDF: coverage calibration mean abs dev 1.5pp, max
  8.0pp; time-dependent AUC 0.52@365d, 0.50@730d (≈0.5 throughout).
- + constraint features (flood/NIAH/Natura/WWTP/traffic + prior activation
  rates): td-AUC 0.56@365d, 0.52@730d; coverage dev 1.8pp.
- Censoring-aware discrete-time hazard (full pool, unlinked censored,
  n=523/572): td-AUC ≈0.0–0.01 at all horizons; Brier 0.41–0.53 vs KM
  0.13–0.26.
- Rolling strata interval engine: width 1,135d, coverage 83.2% (vs GBM
  1,155d @ 74.6%).
- Era recalibration: rolling-24m median MAE 366.5d; authority-shrunk 360.8d;
  oracle 364.4d; naive pre-2020 median 380.1d (n=494).

**Sale timing:**
- 19-quantile GBM smooth CDF: td-AUC 0.46–0.68 across horizons (n=97);
  coverage dev 10.6pp; + constraints: no change.
- Market-context features (county price level, 12m volume, momentum):
  pinball p50 236.1 vs strata 209.7 — no gain.
- Applicant prior-median time-to-sale: r = −0.15 (n=109).
- Applicant estate-name bridge: 241 candidate schemes → 561 rows, 11 new
  schemes with sales.
- AHB/BTR exclusion: 80% width 3,053d vs 3,035d (no change).
- Sale-from-commencement anchor: median 501d, 80% width 1,598d (n=280).
- CCC→sale: median 34d (n=2,021 events); ±180d 60%, ±365d 74%.

**Build duration (commencement→CCC):** median 483d, constant-median MAE
241d; ±90d 32%, ±180d 57%, ±365d 86%. Developer-declared proposed-end date:
correlation with actual 0.0 (n=1,168); MAE using declared 307d.

**Refusal-reason transfer:** top-3 agreement 55.4% (n=56) vs 25.0% baseline.

**Decision timing:** GBM pinball-p50 32.0 (constant 43.3, strata 39.7);
smooth CDF coverage calibration mean |dev| 5.5pp; horizon AUC 0.755 (>6m),
0.718 (>12m).

**Falsified or no-gain experiments (full list):** multi-task shared trunk;
FI-score stacking; forward congestion for decision timing; overlap=2 PPR
band (classifier CV AUC 0.992 → 0 candidates above p=0.5); spatial
auto-confirm ≤150m (1% precision on audit); townland matching; description
"known as" names (6 schemes); 4Dublin road-level candidates (0/153 accepted
on audit); declared build duration (r=0.0); AHB exclusion; constraint
features for sale; market context for sale; authority dummies for appeal.

## 5. Variance decomposition (where the error sits)

Commencement 80% interval widths by stratum (n≥20): South Dublin CC 381d,
Meath 909d, Wicklow 969d, Waterford 1,129d, Kerry 1,392d, Tipperary 1,412d,
Kilkenny 1,539d. By era: 2022+ 814d, 2020–21 1,166–1,546d, pre-2020 1,432d.
Finest interactions (era×authority×band×type): tightest measured 712d
(2022+, 10–29 units, apartments); widest 1,546d (2020–21, 10–29, other).
Applicant prior medians: activation r = −0.09 (n=194), sale r = −0.15
(n=109). Declared build duration r = 0.0 (n=1,168).

## 6. Known data sources — current access state

| Source | What it would provide | Access state |
|---|---|---|
| SEAI BER bulk (unit-level) | final/provisional BER dates per dwelling → completion waves | national bulk not on data.gov.ie; requires SEAI research-tool access; Fingal open layer downloaded (parsing pending) |
| ECAD/GeoDirectory | address points + Created Date → unit/phase observations | commercial licence (~€500–2k/yr), not purchased; pipeline scaffold built and unit-tested |
| Part V scheme-level records | agreement/conveyance dates, units, values | aggregate published; scheme-level requires FOI per authority (not requested) |
| HSA AF1/AF2 | notified start/duration, client, PSDP/PSCS | mandatory filings, not publicly searchable; FOI not requested |
| ESB Networks NC1 | energisation dates (official completion basis) | held by ESB/CSO, not published; not requested |
| Uisce Éireann connection records | connection agreement/live dates | per-file or FOI; not requested |
| Development contributions, bonds | payment/lodgement/release dates | held per authority; not requested |
| CRO Gazette (weekly) | strike-offs, liquidations, receiverships | published; not yet ingested |
| Social Housing Construction Status Reports | design/tender/on-site/complete stages per scheme | PDFs downloading; parsing pending |
| TED/eTenders | contract awards, values, delivery dates | API query running; parsing pending |
| Excavations.ie | site-entry dates, clients | probe running |
| Road-opening licences (MapRoad) | works windows, contractors, reinstatement | Fingal open; national requires per-authority collection or FOI |
| Courts (national JR) | filing/judgment dates | no bulk open source identified; Dublin-only evidence via 4Dublin |

## 7. Open items (state, not assessment)

1. SEAI research-tool access not yet registered → no national BER bulk.
2. ECAD licence not purchased → no address-point observations.
3. FOI requests for Part V / HSA / ESB / Uisce / contributions not drafted or submitted.
4. CRO Gazette not ingested.
5. SHCSR/TED/BER-Fingal/excavations parses pending (downloads in flight).
6. Event ledger built; no downstream consumer exists yet.
7. Applicant-entity features: GBM v3 test on commencement/sale holdouts queued.
8. JR national coverage: Dublin-only.
