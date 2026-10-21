# Full Project Brief — current state, facts only

Date: 2026-10-01. Every model's actual inputs, every accuracy number with
protocol, every experiment outcome (worked and failed), every data asset
state. No assessment language.

---

## 0. Glossary

- **CCC** — Certificate of Compliance on Completion: the building-control
  certification that construction complies with the granted permission
  and building regulations. Filed to the Building Control Management
  System (BCMS) per phase/building; types recorded include full, partial
  and completion-of-some-buildings. We use its date as the completion
  milestone (engine c/e target) and as the anchor for the tightest sale
  claim (post-CCC first-sale median 34 days).
- **BCMS** — national Building Control Management System (2014+): holds
  commencement notices (CN) and CCCs, including phase number, units per
  phase, proposed end date, FSC/DAC references.
- **PPR** — Property Price Register (2010+): sale price and date per
  property, address as filed.
- **FI** — Further Information request (statutory, pre-decision).
- **JR** — Judicial review (post-decision court challenge).
- **SHD / LRD / SDZ** — Strategic Housing Development / Large-scale
  Residential Development / Strategic Development Zone (fast-track
  decision classes).
- **AHB / BTR** — Approved Housing Body (social) / Build-to-Rent.
- **Part V** — social/affordable housing obligation under Part V of the
  Planning and Development Act.
- **FSC / DAC** — Fire Safety Certificate / Disability Access Certificate.

---

## 1. Model-by-model: inputs actually used, and measured accuracy

### 1.1 Refusal likelihood (frozen v4-full, read-only)

Inputs: submission-time features — authority, description text
(TF-IDF), units, site area, coordinates, submission year; derived:
history features, flood proximity, development-plan context. Post-
submission fields (FI, refusal reasons, decisions, appeals) are NOT
inputs.

Accuracy: 2024–25 holdout n=35,713 AUC 0.792 (95% CI 0.784–0.798), AP
0.409, Brier 0.090, calibrated; 2025 slice AUC 0.793 (0.778–0.807),
decile calibration mean abs error 0.9pp (max 5.5pp, top decile predicted
0.408 vs observed 0.353). GE10 subset AUC 0.782 (n=464); riskiest decile
refused 63.8%, safest 0%. Bands: low <=3.8%, medium 3.8–11.4%,
high >11.4%. Frozen 22 Sep 2026; never retrained.

### 1.2 Time to decision

Inputs: **authority congestion features** (rolling counts of earlier
applications and their durations at the same authority — ~80% feature
importance), scheme size (log units), vintage (received year/month),
description TF-IDF, authority dummies.

Models: 19-quantile GBMs + monotone interpolation (smooth CDF).
Accuracy: train received <2024, holdout >=2024, n=433: MAE 63.9d
(constant 86.7d, strata 80.2d); pinball P50 32.0 (constant 43.3, strata
39.7); pinball P20 15.1, P80 21.5. Horizon: P(>6m) AUC 0.755
(0.688–0.815), prevalence 0.349; P(>12m) AUC 0.718 (0.475–0.919),
prevalence 0.023. Smooth-CDF coverage calibration mean |dev| 5.5pp,
max 9.8pp; P(>6m) calibration-in-large +0.13pp.

Attempted and measured: forward-looking congestion feature — no gain
(falsified); multi-task shared trunk — no benefit; FI-score stacking —
no benefit.

### 1.3 FI likelihood (further information requested)

Inputs (v2): description TF-IDF (dominant — structured-only ablation
AUC 0.474 -> +text 0.691), log units, log site area, missingness flags,
density, received year/month, covid era, house/apartment flags,
time-safe authority prior FI rate, 5km-local prior FI rate, applicant
features. GBM depth 3 chosen on 2020 validation (AUC 0.754).

Accuracy: v1 (pain pool) n=363 AUC 0.688 (0.606–0.761), AP 0.840. v2
(full GE10 register) n=1,731 AUC 0.691 (0.668–0.716). By year: 2021
0.721, 2022 0.733, 2023 0.683, 2024 0.719, 2025 0.578. Label maturity
checked: FI rate by received year stable 0.61–0.63 through 2025 (2025
drop is drift, not missing labels).

### 1.4 Appeal likelihood

Inputs: structured (log units, house/apartment flags, received
year/month) + description TF-IDF. No authority dummies (measured to
degrade AUC). v2 additions (prior appeal rates, density, site, covid,
GBM) were fitted and measured worse — not used.

Accuracy: combined v1 n=1,729 AUC 0.659 (0.621–0.698), AP 0.347,
prevalence 0.229. Split models: third-party appeals (post-grant)
prevalence 16.2%, AUC 0.647 (0.615–0.679); applicant appeals
(post-refusal) 6.7%, AUC 0.623 (0.566–0.675).

### 1.5 Time to commencement (grant -> first commencement)

Inputs, by variant:
- Deployable: **rolling 24-month median** of earlier grants (time-safe),
  optionally shrunk toward the authority median.
- Model variants: 19-quantile GBM with structured features (log units,
  log site, density, missingness, grant year/month, covid, house/
  apartment), description TF-IDF, constraint proximity features
  (flood hits, NIAH distance, Natura distance, WWTP distance, traffic
  counter distance), time-safe prior activation rates, applicant
  track-record features, developer-group shrunk medians.

Accuracy: strata MAE 512d (98% CI 450–577, n=494); rolling-24m MAE
366.5d; authority-shrunk 360.8d; oracle 364.4d; median-prediction MAE
366d (95% CI 338–397); hit rates vs predicted median: ±90d 15.5%,
±180d 34%, ±365d 65%. 80% interval (rolling strata engine) width
1,135d, coverage 83.2%. Discrimination: td-AUC 0.52@12m without
constraints, 0.56@12m with constraints, ~0.5 beyond. Developer effects:
seen developers MAE 334d vs unseen 390d (constant median); shrunk
group estimate 312d vs global 327d (n=251).

Attempted and measured: censoring-aware discrete-time hazard — KM wins
on Brier (both before and after the evaluation fix); applicant prior
medians r = −0.09 (n=194); constraint features only lift 12m.

### 1.6 Completion timing (commencement -> CCC)

Inputs (best available): none beyond a constant — the feature-augmented
models were falsified out-of-sample (below). Data: n=1,507 schemes,
2,038 notices; 1,106 events.

Accuracy: first-CCC KM median 550d; constant-median MAE 241d
(±90d 32%, ±180d 57%, ±365d 86%); 25% certified median 554d (n=219);
50% 591d (n=125); final CCC KM median 804d. Developer-declared
proposed-end duration: correlation 0.0, MAE 307d (worse than constant).

Attempted and measured: hazard models with morphology/developer/site
features showed in-sample dynAUC gains (12m 0.478->0.611) that did NOT
transfer out-of-sample (train commencement <2020, test >=2020: dynAUC
0.45–0.51 for all families, IBS 0.72–1.04) — era drift.

### 1.7 Time to first sale

Inputs (development-level ladder): morphology (log units, type, grant
year/month, covid), planning complexity (planning duration, FI,
appeal), developer family (applicant prior n, prior grant rate, prior
median time-to-sale, has-applicant; developer-group shrunk medians),
market context (county price level, 12m volume, price momentum),
site constraints, delivery route (private_sale/rental/social/
forward_funded). Elastic-net on log days was the best model.

Accuracy (train grant <2021, test >=2021, n=95–101): size-band median
MAE 431d; global median 441d; developer-shrunk 439d; elastic-net 425d
(95% CI 368–487); quantile GBM 462d; Weibull AFT 435d. Hit rates
(best model): ±100d 6.3–12.6%, ±180d ~20–27%, ±365d ~37–50%.
Family ablation (OOS MAE): morphology 506d -> +planning 472d ->
+developer 456d -> +market 471d -> +site 465d. Horizon (from grant,
censored dynAUC): 12m 0.69, 18m 0.64, 24m 0.57, 36m 0.66.
Conditional: post-CCC first sale median 34d (n=2,021 phase events;
±180d 60%, ±365d 74%); from commencement median 501d (n=280).

Attempted and measured: decomposed model (commencement->CCC->sale)
worse than direct (489d); AHB/BTR exclusion no width change; sale-from-
commencement anchor no narrowing; gating (expected-error models, two
versions) found no reliable subset; paired bootstrap full model vs
size-band baseline +33.4d (95% CI −19.6 to 84.8) — not significant.

### 1.8 Refusal reasons (theme transfer)

Inputs: precedent retrieval on refused GE10 comparables — wording
similarity + unit count + density + council + recency (5-year window,
strictly earlier, undecided excluded). No trained classifier feeds the
top-1/top-3 claims.

Accuracy: refused GE10 holdout 2024–25: n=88 refused, 56 evaluable.
Top-1 agreement 19.6%, top-2 39.3%, top-3 55.4% (98% CI 42.1–68.5%),
baseline (most-common theme) 25.0%. Label pool: 1,380 refused cases
tagged; llm_new display source 166 rows.

### 1.9 Grant conditions

Inputs: regex family classifier over planner-report text (n=338
labelled reports from the 5,308-PDF local corpus).

Accuracy: prevalence estimates only (98% CI): roads/access/transport
9.2% (5.9–13.5); drainage/wastewater/water 9.2% (5.9–13.5);
construction/environmental 5.0% (2.7–8.5); archaeology/ecology 7.1%
(4.2–11.0); flood mitigation 6.8% (4.0–10.7); landscaping 8.0%
(4.9–12.1); design/material 7.4% (4.5–11.4); Part V/bonds 4.4%
(2.2–7.8); phasing/tenure 5.3% (2.9–8.9); precommencement 2.7%
(1.0–5.5); preoccupation/certification 3.0% (1.2–5.9). No conditional
prediction model fitted.

### 1.10 Judicial review

Inputs: 4Dublin pipeline fields (JR reference, subject-to-live-JR,
conclusions), Dublin only; no national courts bulk exists.

Accuracy: priors (latest quarter per reference, n=2,366): overall 0.9%;
LRD 8.0% (n=100), SHD 5.0% (n=281), Standard 0% (n=551), SDZ/DZ/State
0%; Dublin City 1.3%, SDCC 0.9%, Fingal 0.4%. No date model fitted.

### 1.11 Price vs peers

Inputs: scheme median PPR price vs contemporaneous (12-month window)
same-county transaction benchmark; below-market flag at the 25th
percentile.

Accuracy (n=582 priced schemes): scheme median price median €303,965;
absolute deviation from benchmark: median €65,187 (26.9%), mean
€442,224, p80 €152,520; below-market flag on 37 schemes.

---

## 2. Data assets: state and what each feeds

| Asset | State | Feeds |
|---|---|---|
| NPAD register (491,760; GE10 3,585) | ingested | all planning dates; applicant names redacted in every layer |
| BCMS (249,127 events; full 99 fields) | ingested, silver v2 | commencement/CCC dates, phase fields, CCC types; 83.8% mature linked |
| PPR (807,724) | ingested | sale dates/prices; 763 confirmed schemes, 27,599 rows; 60,342 pending |
| ePlanning applicant index (1,595 pages) | pulled, integrated | developer names: 1,020 entities, 68.7% pool |
| CRO (825,177 companies) | pulled, integrated | 62.5% applicant match, 475 developer groups |
| MSFT building footprints | pulled, integrated | 646 site polygons; spatial cluster analysis |
| OSM addresses (per-estate) | pulled (1,071 inventories), integrated | sale-confirmation layer; 4,204 rows/112 schemes promoted |
| 4Dublin pipeline | ingested | Dublin completion corroboration, JR priors, FI/appeal flags |
| Constraint layers (flood/NIAH/Natura/WWTP/traffic) | ingested | timing model features (12m commencement lift only) |
| TimesFM-2.5 forecasts | built | county macro context only |
| AlphaEarth annual embeddings | pulled (5,814 site-years), tested, falsified | none (see §3) |
| Event ledger (17,330 events) | built | no downstream consumer (multi-state uses label pools) |
| SHCSR / excavations / TED / BER / ECAD / Part V / HSA / ESB / Uisce / road licences | not pulled or blocked | see §4 |

## 3. Experiment ledger — measured outcomes

**Worked (adopted):**
- Decision-timing GBM + smooth CDF (MAE 63.9d) — with authority
  congestion features.
- Era recalibration for commencement (rolling-24m/shrunk: 366/361d vs
  469d naive strata).
- Rolling strata interval engine: 1,135d @ 83.2% coverage vs GBM smooth
  1,155d @ 74.6% (the GBM was under-covering).
- Post-CCC first-sale conditional: median 34d, 60% within ±180d.
- BCMS notice-name estate matching: +188 schemes.
- Human audit-pack loop: PACK_1/14/16/17/18/19/20; classifier
  retrains raised pull precision 17.5% -> 60% band (CV AUC 0.86–0.97).
- Developer identity: seen vs unseen commencement 334 vs 390d; shrunk
  group estimate 312d vs 327 global; sale ablation 506->456d.
- OSM+chronology confirmation layer (running).
- Scrapling stealth fetches: unblocked gov.ie (470KB), excavations
  (348KB), eircode (PDFs).

**Falsified (measured, not adopted):**
- Multi-task shared trunk (torch): no benefit over single-task.
- FI-score stacking into other models: no benefit.
- Forward congestion feature for decision timing: no gain.
- Authority dummies in appeal model: degrade AUC.
- Market-context features for sale (county price level/volume/momentum):
  GBM pinball p50 236.1 vs strata 209.7.
- Constraint features for sale: no change; for commencement only 12m lift.
- Applicant prior medians: r −0.09 activation (n=194), −0.15 sale (n=109).
- Developer-declared build duration (BCMS proposed end date): r = 0.0;
  MAE 307d vs constant 241d.
- AHB/BTR exclusion from sale cohort: width 3,035d vs 3,053d.
- Sale-from-commencement re-anchoring: 1,598d width (n=280).
- Decomposed sale model: 489d vs 425d direct.
- 19-quantile GBM smooth CDFs for commencement/sale: calibrated but
  td-AUC ~0.5 (no discrimination).
- Censoring-aware discrete hazard: KM wins Brier (twice).
- Completion models with morphology/developer/site features: in-sample
  gains (0.48->0.61 @12m) did not transfer OOS (era drift).
- Confidence gating (2 versions, incl. plan-specified features): no
  reliable subset.
- AlphaEarth annual embeddings: E1/E2/E3 null or negative; state
  classifier 0.562 vs 0.656 majority; ablation commencement 349->357d,
  sale 873->879d. Falsified under raw and learned-sensor designs.
- Overlap=2 PPR band: classifier CV AUC 0.992 -> 0 candidates above
  p=0.5 (band confirmed dead).
- Spatial auto-confirm <=150m: 1% precision on audit -> demoted.
- Townland matching: negative.
- Description "known as" estate names: 6 schemes.
- 4Dublin road-level candidates: 0/153 accepted.
- Phase-level PPR attribution: structural — PPR addresses carry estate +
  house number; BCMS publishes phase number and units but no per-phase
  address ranges. Two audit packs (PACK_16/17) confirmed precision 6.3%
  and 0.2%.
- Phase polygons from the local 5,724-PDF corpus: no maps (drawing pages
  are forms/stamps; ARM decisions 0 drawing pages).
- iDocsWeb document postback: server-side ASP.NET state rejects it even
  in a real Chrome browser.
- Planned-duration terciles (post-CCC sale): non-monotone (257/95/39d).
- BER Fingal ArcGIS CSV endpoint: HTTP 500 server-side.
- TED API v3 query variants: HTTP 400 on three syntaxes.
- Geofabrik + BBBike + OSM-FR Ireland extracts: redirect loops /
  no-region / 404 (resolved via per-estate Overpass instead).

**Bug found and fixed:**
- Survival evaluation (per-scheme incidence grid varied with observation
  length, inverting rankings; td-AUC 0.006 -> intercept-only 0.515 after
  fixed-grid IPCW). Synthetic-data check passes; data integrity checks
  (duplicates, negative times, censoring windows) all clean.

## 4. Open items (state only)

- PACK_21 (OSM+chronology band, 112 schemes) awaiting user verdicts.
- Sale-label pending rows: 60,342; chronology filter passes 27,986;
  classifier p>=0.95 band 438 rows/43 schemes.
- User legs: SEAI BER registration; ECAD sample/licence; 5 FOI letters;
  9-estate drawing browser pull; AlphaEarth custom-window approval.
- Queued builds: SHCSR harvester (gov.ie unblocked); excavations parser
  (unblocked); label rebuild + sale-ladder retrain after PACK_21.
- TED retry with documented query syntax; BER Fingal via ArcGIS API.
