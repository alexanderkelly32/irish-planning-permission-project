# Irish Residential Development Risk Engine

## Coding-agent build brief

**Status:** Working technical specification, revision 2  
**Prepared:** 27 September 2026  
**Primary market:** Irish residential development, initially schemes of 10+ units  
**Purpose:** Extend an existing, calibrated planning-outcome model into a time-safe, auditable development execution-risk engine.

---

## 1. Executive summary

The existing system estimates the probability that an Irish residential planning application will be refused. It is deliberately interpretable and calibrated rather than architecturally fashionable. On the stated 2024–25 holdout, the large-scheme model produced a mean predicted refusal rate of 18.1% against an observed 19.0%, with populated probability bands landing within approximately ±2 percentage points of their midpoints. That is already useful, but it answers only the first question in a much longer development process.

The proposed system should answer a broader and more commercially meaningful set of questions:

1. Will the application be granted or refused?
2. Even if granted, how much planning friction is likely before a usable permission exists?
3. How long is the scheme likely to take to commence?
4. Once commenced, how long is it likely to take to complete and, for build-to-sell schemes, convert into sales?
5. What observable features create abnormal cost pressure or execution risk?

The system must **not** pretend that public data can reveal actual budget overruns where it cannot. Public sources can support defensible estimates of planning friction, activation time, delivery time, sales timing and cost exposure. A true “probability of finishing over budget” model requires verified budget and outturn data, which is not assumed to be available in the first version.

The product is not intended to become a generic planning search portal or a substitute planning consultancy. Its differentiator is a time-safe quantitative risk opinion, supported by source evidence and explicit uncertainty. The core output should remain one coherent underwriting report rather than a catalogue of loosely connected products.

This brief gives a coding agent enough structure to begin the data platform and a pilot model. The recommended first milestone is a rigorously audited cohort of **100 granted residential schemes of 10+ units**, followed by a 500-scheme expansion if linkage quality is acceptable. Do not begin with a national scrape of every document.

---

## Amendment A (2026-09-27): the primary product aim

**The primary aim of this engine is a single predictive model: "how painful will
this development be to actually develop?"** — a calibrated, submission-time
probability that a scheme will exhibit severe observable development pain
(planning friction, slow activation, slow delivery), supported by component
evidence and explicit uncertainty. The multi-section underwriting report of
§3.3 is the *presentation* of that model, not an alternative to it.

Consequences for sequencing, effective immediately:

1. **The composite pain label is built before document extraction.** Section 3.3's
   instruction not to collapse outcomes into one score was a guard against a
   premature, unexplained score. It is retained: components stay visible and
   the composite rule is published. But a composite is now the target from the
   start, not a late-stage afterthought.
2. **Structured data first.** The repository already holds the NPAD-derived
   register (FI request/received dates ≈70% coverage on the pilot pool, appeal
   dates ≈9%, decision dates ≈100%) and the BCMS commencements/completions
   snapshot. A provisional `pain_v1` label is built from these before any
   document OCR: appeal submitted, slow planning decision, slow activation,
   slow completion — all observable components, rule published in
   `09_devrisk/configs/rules/pain_v1.yaml`.
3. **Document extraction remains an enrichment, not a precondition.** FI
   topics, condition counts, JR evidence and cost-exposure indicators upgrade
   later model versions (`pain_v2+`); they do not gate `pain_v1`.
4. **Modelling cadence.** Baselines and a regularised submission-time pain
   model are fitted on the structured-label cohort with temporal
   train/validation/holdout splits as soon as labels exist. Calibration and
   component-level honesty rules of §§15-16 are unchanged.
5. **The 100-scheme audited cohort still exists for identity/linkage audit
   (Gate 2)**, but the pain model's first training cohort may be the full
   structured-label pool (~1,100 mature granted schemes) with conservative
   confirmed-link rules; ambiguous links are never silently treated as truth.
6. **The single "headache score" prohibition of §21 stays**: user-facing
   outputs name the event, horizon, snapshot, evidence and uncertainty — the
   product is one coherent model, not a scoreboard of disconnected modules.

All invariants of §2.3 (frozen planning model, calibration, no future
information, scheme grouping, provenance, abstention) remain binding.

---

## 2. Existing model: assumptions and invariants

### 2.1 What already exists

The current planning model reportedly includes:

- structured scheme inputs such as unit count, site area and location;
- textual features, including TF–IDF representations of scheme descriptions;
- local authority, local-area and recent refusal histories;
- development-plan or objective features;
- comparable-application features;
- an interpretable linear/logistic modelling layer;
- isotonic calibration and time-safe evaluation;
- a PDF-style output showing a calibrated refusal probability and contributing factors.

The exact implementation must be inspected in the existing repository before integration. This brief does not authorise silently rewriting, retraining or replacing the frozen model.

### 2.2 Performance supplied by the product owner

Treat these as claims to be reproduced from saved predictions and evaluation code, not as constants to paste into marketing output:

- All residential schemes, 2024–25 holdout: 35,426 applications in bands with at least 30 observations; 98% of applications were in bands where the observed outcome landed within ±2 percentage points of the probability-band midpoint.
- Large schemes, 10+ units, 2024–25 holdout: 464 rows; mean predicted refusal 18.1% versus mean observed refusal 19.0%, a −0.9 percentage-point bias.
- Every large-scheme bin with at least 44 cases was within ±2.1 percentage points of its midpoint.
- A thin 40–50% bin missed by approximately 12 percentage points but contained only 23 cases, with sampling uncertainty of roughly 10 percentage points.
- Recalibration experiments using isotonic and Platt scaling on a smaller 2023 window reportedly worsened Brier score, so the frozen calibrator was retained.

### 2.3 Non-negotiable invariants

1. **Preserve the existing frozen planning model.** Integrate through a versioned prediction interface.
2. **Every probability exposed to a user must be calibrated.** A “light” report may contain less analysis, but it must never contain a knowingly uncalibrated score.
3. **No future information may leak into a historical prediction.** Every feature must have an `available_at` timestamp and be reproducible as of the prediction date.
4. **Group related applications by underlying scheme/site.** Amendments, phases and resubmissions must not appear on both sides of a train/test split.
5. **Preserve provenance.** Every derived field and label must be traceable to a source file, row, URL or document page.
6. **Abstain when identity or evidence is weak.** Ambiguous scheme links must not be forced into training data.
7. **Simple models are first-class.** Complexity is acceptable only where it improves time-safe validation, calibration or useful ranking.

---

## 3. Product thesis

### 3.1 Plain-language promise

> Given what was knowable at the relevant decision date, estimate whether a proposed or recently permitted Irish residential development will encounter planning friction, how long it may take to activate and deliver, and which evidence-based factors are driving the risk.

### 3.2 Intended users

The primary version-one reader is a **development lender's credit committee or underwriting team**. This fixes the report's decision context: whether to proceed, what further diligence to commission, which risks require conditions or contingencies, and what timetable to underwrite. A developer land/acquisitions team is the secondary reader.

Potential users therefore include:

- development lenders and credit committees;
- developers screening acquisitions or prioritising pipeline sites;
- investment managers underwriting residential development;
- architects or planning teams who want an independent quantitative second opinion.

The engine should complement, not impersonate, an experienced planning consultant. A planning consultant may explain policy, strategy and design judgment. The engine should contribute a consistent empirical prior, historical context, milestone timing and an auditable record of what the data says.

### 3.3 One product, several model components

The user does not want a large suite of separate products. Architect the system as one report with modular internal estimates:

1. Planning outcome
2. Planning friction
3. Activation time
4. Completion/delivery time
5. Exit/sales timing, where applicable
6. Cost-exposure indicators

The interface can reveal only the sections supported by sufficient evidence. Internally, each outcome needs its own model, label and evaluation. Do not collapse everything into a single arbitrary “headache score” during the research stage.

### 3.4 What makes it materially different from a planning-data subscription

A planning-data platform generally helps a user find applications, documents and comparable cases. This engine must add:

- a calibrated, project-specific probability or time distribution;
- a prediction date and strictly time-safe feature set;
- explicit separation of site-specific evidence from broad local priors;
- confidence/coverage warnings where descriptions or documents are thin;
- milestone forecasts rather than merely lists of precedents;
- structured risk drivers tied to source evidence;
- retrospective portfolio testing against a lender’s known history, without requiring their data for general model training.

If the system only aggregates comparable applications and adds a percentage, it has not earned a large price differential. The build must concentrate on the parts that search portals do not naturally provide: calibrated inference, longitudinal scheme identity, friction labels, survival analysis and evidence quality.

---

## 4. Scope and non-goals

### 4.1 Version-one scope

- Republic of Ireland.
- Residential schemes with at least 10 proposed units.
- Initial grant dates chosen so that adequate follow-up exists. Do **not** use 2017–2019 as an unqualified cohort: many schemes' activation and delivery windows overlap COVID-19 construction restrictions and later supply disruption. The pilot may draw from these years, but it must encode pandemic exposure and include pre/post-pandemic sensitivity cohorts.
- Planning, commencement, completion and build-to-sell transaction milestones.
- Public and lawfully accessible sources.
- Local-first data stack suitable for a solo founder.
- An auditable model and example underwriting report.
- A lender-oriented mock report designed before model development, then revised from user feedback.

### 4.2 Explicit non-goals

- Replacing a statutory planning opinion or legal due diligence.
- Predicting exact construction cost or exact profit.
- Treating a higher eventual selling price as proof of cost overrun.
- Downloading and OCRing every planning PDF nationally before proving linkage.
- Scraping websites in breach of access conditions, robots directives or practical rate limits.
- Creating public reputational rankings of named developers, planners, architects or contractors.
- Using a lender’s confidential portfolio data to train a shared model without explicit contractual permission.
- Treating absence from incomplete court or document sources as proof that no event occurred.
- Producing causal claims from observational correlations.
- Inferring individual-unit sell-through for build-to-rent, PRS, forward-funded, AHB, state-acquired or retained-unit schemes where those sales are not observable in PPR.

---

## 5. Outcome definitions

The most important early engineering task is to make labels precise. A model is only as meaningful as the event it predicts.

### 5.1 Planning outcome

Retain the current binary or multi-state planning outcome definition, but document:

- whether the prediction concerns the local-authority decision, the final decision after appeal, or both;
- treatment of withdrawn, invalid and incomplete applications;
- treatment of split decisions;
- treatment of permissions later quashed or superseded;
- the date at which the prediction is made.

Recommended user-facing output:

- probability of ultimate refusal;
- probability of local-authority refusal, if separately modelled;
- calibration band and model version.

### 5.2 Planning friction

Planning friction is not synonymous with refusal. Define individual observable components first:

| Component | Illustrative label | Notes |
|---|---|---|
| Further information | `fi_requested` | One or more formal FI requests before decision |
| Clarification | `clarification_requested` | Clarification of FI or equivalent follow-up |
| Third-party appeal | `third_party_appeal` | Confirm from appeal record where possible |
| First-party appeal | `first_party_appeal` | Applicant appeal against refusal/conditions |
| Judicial review evidence | `judicial_review_observed` | Positive evidence only; absence is not a clean negative |
| Material redesign | `material_redesign` | Rule-based thresholds, e.g. meaningful unit or massing change |
| Unit reduction | `unit_reduction_pct` | Continuous and thresholded versions |
| Extensive conditions | `condition_count` | Count plus typed high-impact conditions |
| Pre-commencement dependencies | `precommencement_dependency_count` | Water, roads, phasing, archaeology, etc. |
| Extension of duration | `extension_of_duration` | Subsequent permission extending original duration |
| Amendment chain | `material_amendment_count` | Material follow-on applications linked to base scheme |
| Decision duration | `decision_days` | From valid application to relevant decision milestone |

Only after validating the components should the team define a composite `friction_any` or graded `friction_level`. If a composite is used, keep the component labels visible and publish its exact rule.

A possible first rule is:

- **Low:** no FI, no appeal, no material redesign, limited ordinary conditions.
- **Moderate:** FI or appeal or meaningful conditions, but no observed severe event.
- **High:** multiple rounds, material redesign/unit reduction, judicial-review evidence, quashing, or repeated amendment/extension behaviour.

This is provisional and must be tested for inter-rater reliability on the manually audited cohort.

#### Judicial review as a separate research target

Judicial review should not be buried inside a generic friction composite. It can dominate the timing and value of a permission, but the public labels are incomplete. Treat it as follows:

1. Build a verified positive-event table from court lists, judgments, scheme documents and manual research.
2. Record `jr_observed`, filing/date/status/outcome where known, and `jr_coverage_quality`.
3. Never turn a failed public search into `jr_absent`; use `unknown` unless a sufficiently complete reference source supports a negative.
4. Do not publish a calibrated JR probability until a defined cohort has credible positive **and negative** labels.
5. Before supervised modelling is defensible, report only observable JR-vulnerability indicators—such as appeal intensity, environmental sensitivity, prior controversy or unresolved legal dependencies—with their evidence. Do not imply that these are validated causal predictors.

No prevalence figure should enter the product or training assumptions unless it is reproduced for the exact target cohort from a citable denominator.

### 5.3 Activation

Maintain distinct definitions:

1. **Administrative commencement:** a valid commencement notice observed in BCMS/NBCO data and linked to the scheme.
2. **Substantive activation:** commencement notice plus later evidence consistent with real physical progression, such as completion notices, phased notices, sales or another verified source.
3. **No observed activation:** no linked event by the censor date. This is not automatically permanent non-activation.

Primary duration:

`days_from_final_grant_to_first_valid_commencement_notice`

Candidate binary horizons:

- commencement within 12 months;
- commencement within 18 months;
- commencement within 24 months;
- commencement within 36 months.

The model should ultimately return a survival curve or selected milestone probabilities rather than only a binary answer.

#### Operationalising substantive activation

For version one, define evidence tiers instead of pretending that public records reveal physical progress perfectly:

- **A — administrative only:** a commencement notice is linked, with no corroborating later event yet observed.
- **B — corroborated progress:** commencement plus a later phase notice, completion event, high-confidence first sales, or another authoritative dated construction signal.
- **C — completion evidence:** linked completion record or a sufficiently complete set of completed/sold units.
- **Unresolved:** scheme/event identity or follow-up is inadequate.

Research flags should include `years_since_notice_without_corroboration`, but this is not automatically “paper commencement.” Aerial imagery may be manually tested on a small audit sample if licensing, historical dates and interpretation quality permit. Do not make it a core dependency until its accuracy and cost are measured.

### 5.4 Completion and delivery

Possible milestones:

- first commencement notice;
- later phase commencement notices;
- first completion certificate/notice;
- estimated substantial completion;
- final observed completion event.

Durations may be measured from final grant or first commencement. Unit counts in commencement/completion data may not map cleanly to planning phases, so retain link confidence and coverage ratios.

### 5.5 Exit and sales

Property Price Register data can support a build-to-sell exit timeline where addresses can be linked reliably.

Candidate labels:

- date of first linked arm’s-length residential sale;
- date on which linked sales reach 25%, 50% and 90% of expected sellable units;
- transaction count within 12/24/36 months of first sale;
- median and distribution of observed prices;
- price relative to contemporaneous, geographically and physically comparable new-build transactions.

Important caveats:

- deed-transfer date is not market-launch date;
- the register lacks floor area and bedroom count;
- new-property prices are recorded excluding VAT;
- bulk and multi-unit transactions can be inconsistent;
- rental, social or retained units may never appear as individual sales;
- apparent unsold units may reflect linkage failure rather than economic delay.

Therefore every sales label needs an `eligibility` field and a coverage denominator. Do not generate sell-through labels for schemes that are evidently build-to-rent, social-only, retained or otherwise not individually sold.

The exit market and buyer mix can change materially across vintages. Train and evaluate sales timing only within a defensible exit type, initially ordinary build-to-sell. Include grant/sale vintage and market regime, test temporal stability, and withhold the module where tenure inference is uncertain. The sales module may remain research-only after planning and activation have shipped.

### 5.6 Cost exposure

Call the public-data output **cost exposure** or **cost pressure**, not cost overrun.

Candidate scheme-specific indicators:

- basement or underground parking;
- demolition burden;
- rock excavation or difficult ground;
- contamination or remediation;
- flood mitigation and pumping;
- abnormal drainage, water or wastewater requirements;
- grid or utility dependency;
- major access, junction or road works;
- protected structure or conservation constraints;
- archaeology;
- major off-site infrastructure;
- extensive pre-commencement conditions;
- complex phasing;
- material redesign and unit reduction;
- prolonged delay during high construction-cost inflation or adverse funding conditions.

Macro series such as tender-price, materials-price and interest-rate indices should provide contemporaneous context and interaction variables. They do not show that a specific project exceeded budget.

A genuine overrun model is a later, permissioned workstream requiring verified initial budget, revisions, final outturn and a consistent accounting definition.

---

## 6. Prediction times and feature snapshots

The same scheme can be scored at different decision points. Build snapshots explicitly:

| Snapshot | Cut-off | Permitted information | Main use |
|---|---|---|---|
| `submission` | Application valid date | Initial application, site, plans, historical environment | Acquisition/screening and planning outcome |
| `pre_decision` | Immediately before decision | Events/documents available by cut-off only | Research; avoid presenting as original submission risk |
| `final_grant` | Final effective grant date | Decision, conditions, FI, appeal history known by then | Activation and delivery underwriting |
| `commencement` | First valid commencement | All prior events | Completion and exit timing |

Every feature row must contain:

- `scheme_id`;
- `snapshot_type`;
- `snapshot_at`;
- `feature_version`;
- source availability timestamps;
- model eligibility flags.

Never mix submission-time and post-decision variables in a model described as predicting risk at submission.

---

## 7. Official and primary data sources

The following list is a starting inventory. The coding agent must inspect current schemas, licences, update timestamps and access conditions before production ingestion.

### 7.1 National Planning Applications Dataset (NPAD)

**Purpose:** national planning-application backbone, geography, authority, dates, descriptions and outcomes.  
**Official catalogue:** https://data.gov.ie/dataset/national-planning-applications  
**Reported cadence:** weekly national spatial/tabular publication.  
**Use:** cohort creation, planning application identity, geospatial features and outcome history.  
**Caveats:** field quality and historical coverage may differ by authority; descriptions may be thin; later amendments and older strategic routes may require separate handling.

### 7.2 Local-authority planning systems and document portals

**Purpose:** reports, FI requests, applicant responses, observations, conditions, drawings and linked amendment histories.  
**Use:** planning-friction labels and cost-exposure extraction.  
**Implementation:** build authority-specific connectors behind a common interface; store source URLs and access dates.  
**Caveats:** heterogeneous portals, unstable URLs, scanned PDFs, missing documents and access limits.

Do not create 31 connectors immediately. Start with two to four authorities represented in the pilot, favouring document availability and meaningful scheme counts.

### 7.3 Building Control Management System / National Building Control Office data

**Purpose:** commencement and completion events.  
**Official dataset:** https://data.gov.ie/en_GB/dataset/bcnccc  
**Direct CSV resource observed during research:** https://data.nbco.gov.ie/dataset/2704a333-874d-46f5-b3bc-3673766bf816/resource/0774e781-7af8-46da-b623-872e74cf541e/download/buildingscnscccs.csv  
**Methodology:** https://www.gov.ie/en/department-of-housing-local-government-and-heritage/publications/residential-commencement-notices-background-and-methodology/  
**Coverage stated by source:** all 31 building-control authorities from 2014 onward.  
**Use:** administrative commencement, completion milestones and survival labels.  
**Caveat:** a commencement notice is a formal notice of intent, generally lodged shortly before intended works; it is not by itself proof of meaningful physical progress.

### 7.4 Residential Property Price Register

**Official site:** https://propertypriceregister.ie/  
**Purpose:** residential transaction date, price and address from 1 January 2010 onward.  
**Use:** first sale, sell-through proxies, exit values and market comparables.  
**Caveats from the official site:** no floor area or room count; new-build prices exclude VAT; bulk apartment sales can be inconsistent; dates are deed-transfer dates; errors may exist.

The official interface offers an “Download All Records” function, but the commercial pipeline must still record the applicable reuse/licensing position and obtain advice before redistributing raw transaction data. Prefer derived scheme features and cited transaction examples over republishing a bulk substitute for the register.

### 7.5 Courts Service

**Judgments:** https://www2.courts.ie/Judgments  
**Planning and Environment List:** https://www2.courts.ie/content/planning-environment-list  
**Legal Diary:** https://legaldiary.courts.ie/  
**Purpose:** positive evidence of judicial-review or related court proceedings.  
**Caveat:** judgments are not a complete registry of every filing, settlement or withdrawal. Use positive hits as evidence; do not treat non-matches as definitive negatives.

The Planning and Development Act 2024 is being commenced in phases, and An Coimisiún Pleanála was established in June 2025. Model monitoring must treat legislative and institutional change as a possible regime shift rather than assuming a stationary planning process. Official commencement material: https://www.gov.ie/en/department-of-housing-local-government-and-heritage/publications/planning-and-development-act-2024/

### 7.6 Residential Zoned Land Tax maps

**Catalogue example:** https://data.gov.ie/en_GB/dataset/residential-zoned-land-tax-final-map-for-2026  
**Purpose:** serviced/zoned-land context and spatial features.  
**Use:** optional post-pilot feature source.  
**Caveat:** the map is not a direct readiness or capacity guarantee; historical map versions must align with prediction dates.

### 7.7 Market and construction context

Potential primary sources include:

- CSO building and construction material price indices;
- CSO Cost of Building Homes Hub;
- Society of Chartered Surveyors Ireland Tender Price Index;
- official/authoritative interest-rate series, including Euribor or appropriate euro funding benchmarks;
- CSO new-dwelling completion series for macro context.

Use only series whose historical vintages and definitions can be documented. These are context variables, not project-level cost labels.

### 7.8 Optional later sources

- An Bord Pleanála application and appeal data;
- EPA flood/environmental data where authoritative and spatially usable;
- OPW flood maps already used or available to the existing model;
- Uisce Éireann planning/submission evidence where lawfully available;
- company filings for project entities, used cautiously and only when temporally available;
- geospatial road, transit and services data;
- public procurement/contract-award information for relevant public schemes.

---

## 8. Local-first technical architecture

### 8.1 Recommended stack

For the pilot:

- Python 3.12 or the repository’s existing supported version;
- DuckDB for analytical queries;
- Parquet for durable tabular storage;
- Polars or pandas for transformations, selected consistently;
- GeoParquet plus GeoPandas/Shapely for spatial work;
- Pydantic or JSON Schema for extracted-document contracts;
- scikit-learn plus a survival-analysis library such as `lifelines`, `sksurv` or XGBoost AFT where justified;
- MLflow is optional; simple versioned JSON/YAML manifests may be more proportionate initially;
- `pytest`, `ruff` and static typing where practical.

Do not introduce cloud infrastructure merely because the eventual corpus might be large. A metadata-first, targeted-document pilot should fit on a capable workstation. Design storage interfaces so raw files can later move to object storage without changing model code.

### 8.2 Suggested repository layout

```text
development-risk/
├── pyproject.toml
├── README.md
├── configs/
│   ├── sources.yaml
│   ├── cohorts/
│   ├── models/
│   └── authorities/
├── src/devrisk/
│   ├── cli.py
│   ├── settings.py
│   ├── provenance.py
│   ├── ingestion/
│   │   ├── npad.py
│   │   ├── bcms.py
│   │   ├── ppr.py
│   │   ├── courts.py
│   │   ├── macro.py
│   │   └── council_docs/
│   ├── normalization/
│   ├── entity_resolution/
│   ├── extraction/
│   ├── labels/
│   ├── features/
│   ├── models/
│   ├── evaluation/
│   └── reporting/
├── data/
│   ├── raw/
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   └── manifests/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── leakage/
├── notebooks/
└── docs/
```

The `data/` directories should normally be gitignored. Small synthetic or legally redistributable fixtures may be committed for tests.

### 8.3 Data layers

- **Raw:** immutable source files, responses and PDFs as received.
- **Bronze:** parsed source-shaped records with minimal normalization.
- **Silver:** canonical applications, schemes, events, transactions and entities.
- **Gold:** feature snapshots, labels, model matrices and report-ready outputs.

Each transformation must record:

- input file hashes;
- source URL and retrieval timestamp;
- transformation code/version;
- row counts and rejection counts;
- schema version;
- output hash or partition identifier.

### 8.4 Document-storage strategy

Do not download the entire national document corpus.

1. Ingest application metadata first.
2. Create the pilot cohort.
3. Resolve applications into schemes.
4. Fetch only documents needed for selected schemes and labels.
5. Attempt native text extraction first.
6. OCR only pages or files with inadequate native text.
7. Cache the extracted text and never repeat OCR for an unchanged file hash.
8. Submit only necessary text segments to an LLM, if used.

Before implementing an authority connector, record its portal terms, robots behaviour, technical rate limits and permitted reuse. A technically accessible portal is not automatically suitable for automated commercial ingestion. Pilot-authority selection should consider legal/access feasibility as well as scheme density.

Use content-addressed storage such as:

```text
data/raw/documents/sha256/ab/cd/<full_hash>.pdf
```

The document table should preserve the original filename, URL, authority, application reference, MIME type, hash, retrieval date and access outcome.

---

## 9. Canonical data model

Names may change to fit the existing codebase, but the concepts should not be collapsed.

### 9.1 `scheme`

One underlying development or coherent phase.

Key fields:

- `scheme_id` UUID;
- `canonical_name`;
- `parent_scheme_id` nullable;
- `phase_label` nullable;
- `scheme_type` houses/apartments/mixed/other;
- `tenure_or_exit_type` build_to_sell/build_to_rent/social/mixed/unknown;
- `expected_units`;
- `latitude`, `longitude`, geometry;
- normalized address components;
- local authority;
- `created_at`, `updated_at`;
- identity status and manual-review status.

### 9.2 `planning_application`

One formal application record.

- `application_id` internal UUID;
- authority and source application reference;
- application route/type;
- valid/submission/decision/final-grant dates;
- raw and normalized description;
- proposed and granted units where available;
- decision/outcome fields;
- geometry and address;
- applicant/developer raw strings;
- source row identifier and provenance.

### 9.3 `scheme_application_link`

Many-to-many link allowing amendments, phases and resubmissions.

- `scheme_id`;
- `application_id`;
- relation type: base, phase, amendment, extension, substitute, appeal, enabling works, uncertain;
- match method;
- match score;
- confidence band;
- evidence JSON;
- reviewer and review timestamp.

### 9.4 `planning_event`

- application/scheme IDs;
- event type;
- event date or date interval;
- structured values, such as units before/after;
- evidence document/page/span;
- extraction method and confidence;
- `available_at`.

### 9.5 `document`

- document ID;
- source application ID;
- source URL;
- authority document type/raw label;
- retrieval status/date;
- file hash, media type and byte count;
- native-text/OCR status;
- page count;
- access/licence notes.

### 9.6 `document_extraction`

- document ID;
- extraction schema version;
- parser/prompt/model version;
- extracted JSON;
- evidence spans with page numbers;
- field-level confidence;
- validation errors;
- reviewer disposition.

### 9.7 `bcms_event`

- source record ID;
- event type: commencement, seven-day notice, completion or source-specific type;
- received/valid/intended dates where available;
- address and authority;
- dwelling/unit counts;
- raw project description;
- normalized geometry if geocoded;
- source snapshot and provenance.

### 9.8 `scheme_bcms_link`

- scheme and BCMS IDs;
- candidate score and features;
- relation/phase;
- confidence band;
- evidence;
- manual decision.

### 9.9 `ppr_transaction`

- source transaction ID or deterministic hash;
- sale/deed date;
- raw and normalized address;
- price as recorded;
- not-full-market-price flag;
- VAT/new-property indicator where available;
- property description;
- geocode and confidence;
- source snapshot.

### 9.10 `scheme_ppr_link`

- scheme and transaction IDs;
- candidate score and features;
- match confidence;
- likely phase/unit/building;
- exclusion reason, including bulk/ambiguous/outside window;
- reviewer decision.

### 9.11 `entity` and `scheme_party`

For later team-history features:

- canonical entity ID/name/type;
- aliases and company identifiers where lawful;
- scheme role: applicant, developer, planner, architect, contractor, funder;
- effective dates;
- source/evidence;
- entity-resolution confidence.

Do not expose reputational scores until entity resolution and time-safe histories have been audited.

### 9.12 `market_context`

Date/geography-indexed macro data:

- index/series name;
- period;
- value, units and revision vintage;
- geography;
- source and release date;
- earliest `available_at`.

### 9.13 `label_snapshot`

- scheme ID;
- label name/value;
- origin milestone;
- observation window end;
- censoring status;
- eligibility;
- label confidence;
- label rule version;
- provenance bundle.

### 9.14 `feature_snapshot`

- scheme ID;
- snapshot type/date;
- feature-set version;
- feature values or partition pointer;
- availability audit result;
- data-quality and coverage indicators.

---

## 10. Scheme entity resolution

Scheme identity is the highest-risk engineering problem. A polished model trained on incorrectly linked schemes is worse than no model.

### 10.1 Why this matters

The earlier Activate portfolio exercise demonstrated the failure mode. A reference believed to represent Millerstown in Kilcock appeared to point to a different scheme in Capdoo, Clane. A high planning-risk score attached to the wrong project produces a persuasive but false story. Every portfolio backtest and training row therefore requires explicit identity evidence.

### 10.2 Candidate generation

Generate candidates using broad, cheap rules before scoring:

- exact or normalized application references found in documents or source text;
- spatial buffers around application coordinates;
- normalized address/estate/townland tokens;
- Eircode where present;
- developer/applicant/entity matches;
- unit-count tolerance;
- temporal compatibility;
- known appeal/amendment/base-application references;
- planning descriptions embedded in BCMS records;
- estate/building names in PPR addresses.

Avoid relying on any one weak field.

### 10.3 Match features

Candidate scores should expose features rather than bury them:

- exact reference match;
- distance in metres;
- address-token similarity;
- uncommon place-name agreement;
- developer/entity agreement;
- unit-count absolute and proportional difference;
- scheme-type compatibility;
- date order and plausible duration;
- linked planning reference in source text;
- phase-language compatibility;
- negative conflicts, such as different counties or impossible chronology.

Start with transparent rules or a weighted logistic model. Learn weights only after a labelled match set exists.

### 10.4 Confidence bands

- **Confirmed:** exact authoritative reference or manual evidence leaves little reasonable doubt.
- **Probable:** multiple independent fields agree and no material conflicts exist.
- **Ambiguous:** plausible candidates remain or evidence is thin.
- **Rejected:** material contradiction or clearly different scheme.

Only confirmed links should enter the first training set. Probable links may be used in sensitivity analysis, never silently mixed into the main result.

Do not pre-state an expected automatic linkage rate without evidence. The pilot must publish two separate measures:

- precision among links accepted as confirmed;
- coverage: the proportion of eligible schemes for which a confirmed link is achieved.

Manual review and unresolved cases are expected, particularly for SPVs, changed marketing names and multi-phase schemes. A high-precision system that abstains is preferable to a superficially complete system.

### 10.5 Scheme families and phases

Represent the difference between:

- master site;
- individual planning application;
- construction phase;
- amendment;
- extension of duration;
- replacement application;
- sales phase or marketing name.

A single `scheme_id` for an entire multi-year masterplan may be too coarse for delivery labels. Use parent/child schemes or explicit phases, with a documented aggregation rule.

### 10.6 PPR-specific matching

PPR linkage will often be probabilistic. Use:

- normalized estate/building names and street patterns;
- geocoding with uncertainty;
- first-sale date constraints after plausible construction;
- concentration of new-property transactions;
- expected unit count and observed transaction count;
- developer marketing names where verified from public evidence;
- price-pattern and address-sequence consistency only as supporting evidence.

Measure precision using manually checked transactions. Report coverage separately. High precision with lower coverage is preferable to invented completeness.

---

## 11. Document extraction

### 11.1 Extraction hierarchy

1. Deterministic metadata and filename/document-type parsing.
2. Native PDF text extraction.
3. OCR for pages without useful native text.
4. Rule/regex/table extraction for exact references, dates, units and conditions.
5. LLM-assisted structured extraction for genuinely semantic fields.
6. Human audit for high-impact or low-confidence fields.

### 11.2 Structured contract

Every LLM extraction must validate against a schema and include evidence. Example:

```json
{
  "schema_version": "planning_friction_v1",
  "application_reference": "...",
  "events": [
    {
      "event_type": "further_information_request",
      "event_date": "YYYY-MM-DD",
      "summary": "...",
      "evidence": [
        {
          "document_id": "...",
          "page": 7,
          "quote": "short supporting span"
        }
      ],
      "confidence": 0.94
    }
  ],
  "risk_factors": [
    {
      "type": "wastewater_dependency",
      "status": "present",
      "severity": "material",
      "evidence": [],
      "confidence": 0.87
    }
  ]
}
```

Requirements:

- no unsupported free-text conclusions;
- evidence pages/spans for every material extracted field;
- `unknown` distinct from `absent`;
- prompts, model name and parameters versioned;
- retry/failure behaviour deterministic and logged;
- no training on unreviewed LLM labels until audit precision is known.

### 11.3 Candidate extracted fields

- FI/clarification topics and dates;
- objections and appeal events;
- proposed, revised and granted units;
- height/storey changes;
- access/road changes;
- condition count and condition categories;
- pre-commencement conditions;
- water/wastewater/electricity dependencies;
- flood mitigation;
- archaeology and protected structures;
- demolition, basement, excavation, contamination;
- off-site infrastructure;
- phasing and tenure mix;
- named related applications;
- extension/amendment grounds.

### 11.4 Audit design

For each extraction field, sample both predicted positives and predicted negatives. Measure:

- precision;
- recall where a sufficiently complete human reference exists;
- field agreement;
- date accuracy;
- unit/count accuracy;
- inter-rater agreement on subjective labels.

Do not report a generic “LLM accuracy”. Report field-specific results.

---

## 12. Cohort and pilot design

### 12.1 Stage A: 100-scheme golden cohort

Construct approximately 100 schemes with:

- final grants with enough follow-up to observe the required horizons, while explicitly stratifying pandemic exposure;
- 10+ residential units;
- a mix of houses, apartments and mixed schemes;
- several local authorities with accessible source documents;
- a spread of scheme sizes;
- confirmed application and scheme identity;
- enough elapsed time to observe activation and likely completion/sales.

Stratify intentionally. Do not take the first 100 rows returned by a query.

Suggested strata, adjusted for available data:

- 4–6 authorities;
- 25% 10–29 units;
- 25% 30–99 units;
- 25% 100–249 units;
- 25% 250+ units;
- meaningful representation of houses, apartments and mixed schemes.

This cohort is for pipeline validation and label design, not for claiming a nationally generalisable model.

#### COVID and exceptional-period design

Irish construction was materially restricted during 2020 and early 2021; official government notices record broad closure from 8 January 2021 and phased residential reopening from 12 April 2021, with remaining construction reopening from 4 May 2021. Sources:

- https://www.gov.ie/en/department-of-the-taoiseach/press-releases/additional-public-health-restrictions-please-stay-at-home/
- https://www.gov.ie/en/department-of-housing-local-government-and-heritage/press-releases/minister-obrien-welcomes-phased-reopening-of-construction/
- https://www.gov.ie/en/department-of-the-taoiseach/press-releases/new-public-health-measures-announced-the-path-ahead/

For each scheme, calculate exposure of its at-risk activation/delivery interval to defined restriction regimes. The modelling report must include:

1. a primary model with explicit calendar/regime effects;
2. sensitivity analysis excluding or censoring materially COVID-exposed intervals;
3. performance by pre-COVID, COVID-exposed and later cohorts;
4. a written assessment of whether coefficients and post-COVID predictions are stable.

Do not solve the problem by simply deleting every slow scheme affected by COVID; that creates selection bias. Exact interval treatment should be declared before model comparison.

### 12.2 Stage B: 500-scheme modelling cohort

Expand only after:

- confirmed-link precision is acceptable;
- commencement/completion coverage is quantified;
- PPR eligibility and match rates are understood;
- document extraction achieves field-level thresholds;
- ambiguous phase handling has a stable rule.

Five hundred schemes may still be small for highly flexible models, but it is adequate to compare transparent baselines and identify whether signal exists.

### 12.3 Stage C: national historical cohort

Scale nationally after source-specific failure modes are measured. At this point add:

- automated authority connectors;
- job queue and retry controls;
- object storage if needed;
- incremental source snapshots;
- review prioritisation based on model value and uncertainty.

---

## 13. Label-building protocol

### 13.1 Observation windows and censoring

For every time-to-event label, store:

- start milestone/date;
- event milestone/date;
- last observation date;
- event observed boolean;
- censor reason;
- eligibility;
- link confidence.

Never label a 2025 grant as “did not commence within 36 months” in 2026. Right-censor it.

### 13.2 Competing events

Activation can be precluded or altered by:

- lapse/expiry;
- replacement permission;
- judicial quashing;
- withdrawal;
- material sale or change of control, if known;
- phase restructuring.

At minimum, report these as censor/event reasons. Later, consider competing-risks survival models.

### 13.3 Friction-label rules

Create a versioned YAML/JSON rule file rather than scattering rules through notebooks. Example concepts:

```yaml
friction_v1:
  high_if_any:
    - judicial_review_observed
    - material_redesign
    - unit_reduction_pct_gte_20
  moderate_if_any:
    - fi_requested
    - first_party_appeal
    - third_party_appeal
    - high_impact_precommencement_condition
  low_if_none_of_above: true
```

The exact thresholds require human review. Always retain raw components so the composite can be changed without re-extraction.

### 13.4 PPR milestone rules

Before calculating sell-through:

1. Determine scheme eligibility.
2. Establish the expected individually saleable unit denominator.
3. Link high-confidence transactions.
4. Exclude or separately identify bulk/non-market transactions.
5. Calculate milestone dates with a coverage warning.

Do not equate `transaction_count / granted_units` with true sell-through where tenure mix or phase boundaries are unknown.

---

## 14. Feature engineering

### 14.1 Core submission-time features

Reuse or reproduce time-safely from the existing model:

- local authority and historical authority outcomes;
- recent local/spatial refusal rates;
- development-plan features;
- description TF–IDF or interpretable topic features;
- comparable-application outcomes and similarity quality;
- unit count and scheme type;
- site area and density where available;
- spatial/environmental context;
- access/road language;
- planning route and application type.

### 14.2 Final-grant features

- time spent in planning;
- FI/clarification count and topics;
- appeal history;
- proposed-to-granted unit changes;
- condition count and typed conditions;
- pre-commencement dependencies;
- final permission duration;
- remaining appeal/JR uncertainty observable at snapshot;
- current frozen refusal score, only if generated out-of-fold/time-safely for historical data.

### 14.3 Physical and execution-complexity features

- apartments/houses/mixed;
- building height and blocks;
- basement/underground parking;
- demolition;
- abnormal ground/remediation;
- protected structures;
- flood measures;
- major roads/junctions;
- utilities and off-site infrastructure;
- phasing;
- tenure mix;
- dependency graph count and severity.

### 14.4 Market-context features

Measured at the snapshot date:

- tender/material-cost index levels and recent change;
- funding-rate level and recent change;
- local new-build transaction volume;
- local price level/trend;
- broader completion/commencement cycle indicators.

Prefer changes and interactions that have an economic interpretation. Avoid dumping dozens of highly correlated macro series into a small dataset.

### 14.5 Team-history features: later phase only

If pursued, calculate factual, smoothed, time-safe histories such as:

- number of prior observed schemes;
- median time to commence on eligible prior schemes;
- proportion with FI/appeal among prior matched schemes;
- shrinkage toward the market mean for small samples;
- last-observed date and coverage.

Use neutral language such as “observed historical activation” rather than “good/bad developer”. Keep these internal until legal, ethical and statistical review is complete.

If team history is ever exposed:

- show the observed numerator, denominator, period and coverage;
- impose a minimum sample threshold and shrink small samples toward the cohort mean;
- avoid league tables, letter grades and unsupported character judgments;
- do not expose an entity contribution that allows a report reader to reverse-engineer a reputational ranking;
- obtain Irish legal review before release.

Irish law provides statutory defences including truth and honest opinion, but that does not remove the need for accurate identity resolution, contextual presentation and proportionate publication. Relevant starting point: Defamation Act 2009, sections 16 and 20, https://www.irishstatutebook.ie/eli/2009/act/31/enacted/en/html

### 14.6 Missingness and coverage features

Missing evidence is often informative but also source-dependent. Include explicit indicators:

- description length/quality;
- number of close comparables and mean similarity;
- document availability;
- native text/OCR quality;
- match confidence;
- source coverage by authority/year;
- unknown unit count or site area.

User-facing reports should say when a score is driven mostly by broad priors because scheme-specific evidence is thin.

---

## 15. Modelling plan

### 15.1 General principles

- Start with baselines.
- Optimise out-of-time performance and calibration, not training fit.
- Keep models outcome-specific.
- Prefer interpretable coefficients, monotonic transformations and auditable contributions where performance is competitive.
- Preserve uncertainty and abstention.
- Use the existing planning probability as one possible feature, never as an unquestioned truth.

### 15.2 Planning friction

Initial models:

1. authority/year/type/size logistic baseline;
2. regularised logistic regression with structured and text/topic features;
3. gradient-boosted comparison model;
4. optional ordinal model for low/moderate/high friction.

Evaluate each component separately before the composite. A model that predicts FI well but cannot predict judicial review should say so.

Metrics:

- Brier score;
- log loss;
- calibration-in-the-large and slope;
- expected calibration error with confidence intervals;
- ROC AUC and precision-recall AUC;
- sensitivity at commercially chosen thresholds;
- subgroup calibration.

### 15.3 Activation survival model

Baselines:

- overall Kaplan–Meier curve;
- Kaplan–Meier by year, authority and scheme type;
- median time of nearest comparable cohort;
- simple Cox proportional-hazards model.

Candidate models:

- regularised Cox model;
- discrete-time logistic hazard model;
- random survival forest;
- gradient-boosted survival or AFT model.

The discrete-time hazard model may provide the best balance of explainability, changing macro conditions and horizon-specific calibration. Do not select it in advance; compare.

Outputs:

- probability of administrative commencement by 12, 18, 24 and 36 months;
- expected/median time where estimable;
- full survival curve internally;
- confidence band/bootstrap uncertainty;
- principal drivers.

Metrics:

- concordance index;
- integrated Brier score;
- time-dependent AUC;
- calibration at each commercial horizon;
- observed-versus-predicted survival curves;
- net benefit/decision-curve analysis only if a real decision threshold is defined.

### 15.4 Completion and sales models

Use the same survival framework, with careful eligibility:

- commencement to first completion;
- commencement to substantial completion proxy;
- first sale and sales milestones for eligible schemes.

Multi-phase developments may need recurrent-event or phase-level models. Do not hide that complexity inside a scheme-level median.

### 15.5 Cost-exposure model

Version one should be an evidence-backed scoring model or vector of indicators, not a trained “overrun probability”.

Possible implementation:

- extract binary/ordinal cost drivers;
- quantify market-index movement over expected duration scenarios;
- show abnormal dependencies and condition burdens;
- benchmark against similar delivered schemes’ observed timing;
- avoid translating exposure directly into euro cost without defensible quantities and unit rates.

### 15.6 Existing planning score as a feature

For historical modelling, generate it using one of:

- stored genuinely out-of-time predictions;
- rolling-origin training and prediction;
- nested out-of-fold predictions where time order and site grouping are preserved.

Never feed in-sample planning probabilities into downstream models. Compare downstream performance with and without the score to prove incremental value.

---

## 16. Validation and leakage controls

### 16.1 Splitting

Use temporal splits, for example:

- earlier years: training;
- subsequent year: validation/calibration;
- latest sufficiently matured years: holdout.

Exact years depend on label maturity. Group by scheme, parent site and related applications so one phase does not inform another phase in the test set improperly.

### 16.2 Availability audit

Every feature needs:

- source event date;
- publication/release date where different;
- earliest safe availability date;
- snapshot cutoff comparison.

Create an automated test that fails a training build when `available_at > snapshot_at`.

### 16.3 Label-maturity audit

The holdout must have enough follow-up for the evaluated horizon. Survival methods allow right-censoring, but fixed-horizon calibration still requires appropriate handling such as inverse-probability-of-censoring weighting.

### 16.4 Subgroup evaluation

At minimum:

- local authority;
- application year;
- houses/apartments/mixed;
- size band;
- urban/rural context;
- description/document quality;
- match confidence;
- planning route.

Suppress unstable subgroup claims where samples are too small. Show intervals.

### 16.5 Portfolio backtests

When testing a prospective client’s historical schemes:

- freeze model and matching rules first;
- verify every scheme identity;
- state prediction dates;
- distinguish portfolio selection bias from general performance;
- never claim that zero observed refusals invalidates a calibrated expected count without an appropriate probability calculation;
- invite the client to compare predicted friction/timing with their private experience;
- do not retain confidential outcomes for shared training unless separately authorised.

### 16.6 Required baselines

No model advances unless it beats useful simple alternatives:

- overall base rate;
- authority/year/type/size rate;
- nearest-cohort median time;
- Kaplan–Meier cohort curve;
- existing planning score alone, where relevant.

“Beats” must include calibration and commercial usefulness, not AUC alone.

### 16.7 Regime change and exceptional shocks

Create explicit flags or time-varying covariates for material external regimes, initially:

- COVID construction-restriction periods;
- major planning-legislation/institution transitions;
- extreme construction-cost/funding regimes;
- material source-system changes.

For every major model, provide rolling-origin results and sensitivity analysis with exceptional periods included/excluded or modelled separately. Do not allow a historical shock to masquerade as a permanent site characteristic.

### 16.8 Production drift monitoring

Once predictions are used externally:

- monitor input missingness and feature-distribution drift monthly or quarterly;
- evaluate outcome calibration as soon as labels mature;
- maintain rolling, untouched temporal cohorts;
- review calibration quarterly where sample size permits, without automatically refitting to noise;
- define alert thresholds by feature and model during deployment;
- require a formal investigation for material calibration deterioration, source-schema changes or policy-regime changes;
- version and deprecate models rather than overwriting them;
- display model version, training cutoff and last validation date in every report;
- mark a model as `monitoring_due` if the scheduled review is missed, rather than inventing a universal stale-after-N-month rule before observing label cadence.

---

## 17. Evaluation gates

These are engineering/research gates, not promises of eventual model performance.

### Gate 1: ingestion reproducibility

- same source snapshot produces the same parsed result;
- row counts and hashes recorded;
- schema failures are surfaced, not silently coerced;
- source licences/access notes captured.

### Gate 2: identity quality

- manually audited precision of at least 95% for links labelled `confirmed` in the pilot;
- ambiguous links excluded from primary training;
- every portfolio scheme has a compact evidence record;
- false-link root causes documented.

### Gate 3: label quality

- at least 20–30 schemes deeply hand-audited before scaling;
- extraction precision and recall reported per important field;
- inter-rater rules resolved for material redesign/friction;
- label eligibility and censoring tested.

### Gate 4: signal

- activation/friction model outperforms predeclared simple baselines on temporal validation;
- probability and horizon calibration are acceptable with uncertainty intervals;
- performance is not entirely dependent on one authority or year;
- ablation identifies where incremental signal comes from.

### Gate 5: useful report

- a knowledgeable reader can distinguish evidence from inference;
- probabilities state event, horizon, prediction date and uncertainty;
- thin evidence triggers a visible warning;
- every important driver links to a source or feature definition;
- no claim implies a planning, legal or cost certainty that the data cannot support.

If Gate 2 or Gate 3 fails, do not compensate by fitting a more complex model.

### Gate 6: pre-committed falsification and stop/go rules

Before the 100-scheme build, save a signed/versioned pilot decision document. Initial rules:

1. **Identity:** do not scale if confirmed links cannot sustain at least 95% audited precision after one remediation cycle. Report coverage separately; if fewer than 50% of eligible pilot schemes can be confirmed from lawful public sources, narrow the target segment or secure a better source before modelling.
2. **Labels:** stop the affected outcome if auditors cannot reproduce its label rule with acceptable agreement. For categorical high-impact labels, target Cohen's kappa of at least 0.70 or an agreed equivalent; raw agreement alone is insufficient where classes are imbalanced.
3. **Prediction:** do not advance an outcome model unless it improves a predeclared simple baseline on at least one proper scoring metric and does not materially worsen calibration. Do not precommit to an arbitrary AUC lift before event prevalence and censoring are known.
4. **Stability:** do not ship if apparent performance disappears when COVID-exposed observations, one dominant authority or probable links are removed.
5. **Buyer value:** before scale-up, two target readers—at least one lender/credit reader and one developer/investment reader—must review the mock and evidence-backed pilot reports. Continue only if the report changes or prioritises a real diligence action, not merely because it is described as interesting.

Record pass/fail without moving the thresholds after seeing results. Any exception requires a written reason and a new prospective test.

---

## 18. Ordered implementation plan

### Sprint 0 — Report contract, repository inspection and scaffolding

1. Draft a lender-credit mock report using clearly labelled placeholder data.
2. Show it to at least one friendly lender/credit reader and one developer/investment reader; record which decisions, evidence and peer comparisons they actually need.
3. Freeze the version-one report contract and primary outcome priorities before bulk data work.
4. Inspect the existing planning-model repository, data contracts and model artefacts.
5. Identify its prediction interface and time-safe feature-generation logic.
6. Record current tests, model version, calibrator and evaluation reproduction steps.
7. Create a separate `devrisk` package/module without altering frozen behaviour.
8. Add source, provenance and configuration schemas.
9. Add quality tooling and a small CI test suite.

**Deliverable:** tested mock report and decision log, architecture note, working CLI skeleton, unchanged existing-model test results.

### Sprint 1 — Source manifest and structured ingestion

1. Create `sources.yaml` with official URLs, licences, cadence and expected schemas.
2. Download versioned NPAD, BCMS and PPR snapshots.
3. Store raw hashes and retrieval metadata.
4. Parse each to bronze Parquet.
5. Add schema/row-count diagnostics and small fixtures.

**Deliverable:** reproducible ingestion and data-quality report. No modelling yet.

### Sprint 2 — Pilot cohort and canonical applications

1. Define 2017–2019, 10+ unit granted candidate cohort.
2. Deduplicate and normalise application references, addresses and geometry.
3. Stratify and select 100 pilot schemes.
4. Build initial scheme/application family relationships.
5. Export an audit workbook or review UI.

**Deliverable:** versioned 100-scheme cohort with selection rationale.

### Sprint 3 — BCMS linkage and activation labels

1. Implement candidate generation.
2. Build transparent scoring features.
3. Manually adjudicate initial candidates.
4. Set confirmed/probable/ambiguous thresholds from evidence.
5. Build censored time-to-commencement labels.
6. Calculate linkage coverage and error modes.

**Deliverable:** audited activation-label table and match-quality report.

### Sprint 4 — PPR linkage and exit labels

1. Determine scheme eligibility for individual sales.
2. Normalise/geocode PPR addresses.
3. Link candidate transactions conservatively.
4. Audit precision and quantify coverage.
5. Build first/25/50/90% sale milestones only where denominator is defensible.

**Deliverable:** eligible-scheme sales timeline with coverage warnings.

### Sprint 5 — Baseline survival models

1. Predeclare train/validation/holdout logic.
2. Fit Kaplan–Meier and simple cohort baselines.
3. Fit regularised Cox and/or discrete-time hazard model.
4. Evaluate calibration, discrimination and subgroup stability.
5. Produce survival plots and a model card.

**Deliverable:** evidence on whether public structured data has useful activation signal.

### Sprint 6 — Targeted planning-document pipeline

1. Implement connectors for two to four pilot authorities.
2. Fetch only selected document types for pilot schemes.
3. Extract text with OCR fallback.
4. Implement schema-constrained friction extraction.
5. Hand-audit field-level accuracy.
6. Build friction and cost-exposure components.

**Deliverable:** reviewed friction dataset; no national scrape.

### Sprint 7 — Incremental modelling and ablation

1. Fit friction component models.
2. Add final-grant friction/complexity features to activation models.
3. Compare against structured-only baselines.
4. Test existing planning score with/without.
5. Quantify incremental value of documents and macro context.

**Deliverable:** ablation report answering what actually improves prediction.

### Sprint 8 — Prototype underwriting report

Populate and refine the Sprint 0 report contract with real pilot evidence, containing:

- scheme identity and evidence confidence;
- planning refusal probability;
- friction probabilities/components;
- commencement survival milestones;
- completion/sales estimates where eligible;
- cost-exposure indicators;
- principal drivers;
- a required peer-evidence table of close historical schemes, their match quality, known milestones and outcomes;
- limitations and model/data versions.

**Deliverable:** one lender-oriented report, explicitly marked research/prototype.

### Sprint 9 — 500-scheme expansion decision

Proceed only if identity, label and signal gates pass. Otherwise fix the pipeline or narrow the claim.

---

## 19. Proposed CLI

The exact framework is flexible, but commands should be scriptable and idempotent.

```bash
devrisk sources validate
devrisk ingest npad --as-of 2026-09-27
devrisk ingest bcms --as-of 2026-09-27
devrisk ingest ppr --as-of 2026-09-27

devrisk cohort build --config configs/cohorts/pilot_100.yaml
devrisk schemes resolve-applications --cohort pilot_100
devrisk match bcms --cohort pilot_100
devrisk match ppr --cohort pilot_100

devrisk audit export --task bcms-links --cohort pilot_100
devrisk audit import --file reviewed_bcms_links.xlsx

devrisk documents fetch --cohort pilot_100 --authority DCC
devrisk documents extract --schema planning_friction_v1

devrisk labels build --label activation --cohort pilot_100
devrisk labels build --label friction --cohort pilot_100

devrisk train --model activation_24m --config configs/models/activation_v1.yaml
devrisk evaluate --run-id <run_id>
devrisk report scheme --scheme-id <uuid> --as-of <date>
```

Commands must refuse to overwrite immutable raw snapshots without an explicit new version.

---

## 20. Testing requirements

### 20.1 Unit tests

- application-reference normalization;
- Irish address normalization without destructive token loss;
- date parsing and ordering;
- unit-count extraction;
- match-feature calculations;
- censoring logic;
- milestone calculations;
- feature `available_at` enforcement;
- schema validation;
- deterministic hashes.

### 20.2 Integration tests

- ingest small fixed NPAD/BCMS/PPR fixtures;
- build a mini cohort;
- link known positive and negative examples;
- produce labels and train a trivial model;
- render a test report with provenance.

### 20.3 Leakage tests

- reject feature records published after snapshot date;
- ensure related scheme/application groups remain in one split;
- ensure downstream planning-score feature is out-of-fold/time-safe;
- ensure label dates do not enter feature text or extraction payloads;
- scan feature names/source columns for obvious outcome proxies.

### 20.4 Data invariants

- final grant cannot precede submission;
- commencement usually cannot precede permission without explicit exceptional status;
- PPR sale used for exit cannot predate plausible development chronology;
- probabilities lie in [0,1];
- each label has observation window and eligibility;
- confirmed links have evidence.

Warnings rather than automatic deletion may be appropriate for genuine exceptional cases.

---

## 21. Reporting contract

Every user-facing prediction should state:

1. **Event:** what exactly is being predicted.
2. **Horizon:** by when.
3. **Snapshot:** information date.
4. **Estimate:** calibrated probability or time distribution.
5. **Uncertainty:** interval or evidence-quality statement.
6. **Drivers:** scheme-specific and contextual contributions.
7. **Evidence quality:** match confidence, document coverage and comparable quality.
8. **Limitations:** what is unknown and what the model does not claim.
9. **Versions:** data snapshot, feature set and model.
10. **Peer evidence:** a transparent table of the closest eligible historical schemes and their observed planning, activation, completion and exit milestones, with match quality and missingness.

Peer evidence is not decorative. It allows a credit reader to challenge scheme identity, recognise known cases and understand whether the model rests on relevant history. Comparables must be selected by a documented, time-safe method; the system must not cherry-pick persuasive examples after observing the target result.

Example language:

> As of final grant on 14 June 2019, the model estimates a 63% probability of an administrative commencement notice within 24 months. The estimate is driven upward by the scheme’s unit scale and local activation history, and downward by extensive pre-commencement infrastructure dependencies. Scheme-to-BCMS identity confidence is high in the training evidence, but this prediction does not guarantee physical works or budget performance.

Avoid:

> This project has a 37% chance of being a headache.

---

## 22. Security, legal and ethical controls

- Respect source terms, licences, robots directives and reasonable rate limits.
- Preserve source attribution and access dates.
- Store only personal information necessary for legitimate project-level analysis.
- Avoid public individual-level rankings and defamatory language.
- Treat court information as sensitive contextual evidence and verify identity carefully.
- Do not infer criminality, misconduct or incompetence from delay or refusal.
- Do not use confidential lender data outside the agreed purpose.
- Support a no-retention portfolio-validation workflow where inputs and outputs can be deleted or remain client-isolated.
- Document model limitations prominently; the tool is decision support, not a statutory, legal or investment guarantee.
- Establish a process for correcting false scheme/entity links.
- Complete a source-by-source commercial-use and automated-access review before scaling collection. For PPR, distinguish official bulk-download availability from permission to redistribute raw data. For council portals, assess each authority rather than assuming common terms.

Before commercial deployment, obtain professional advice on data licensing, GDPR/legitimate interest, liability language and professional-services boundaries.

---

## 23. Compute and cost controls

The first pilot should not require a large distributed system.

### 23.1 Controls

- query metadata before downloading documents;
- deduplicate by hash;
- native text before OCR;
- page-level OCR where possible;
- batch and cache geocoding;
- cache LLM extractions keyed by document hash, schema and prompt version;
- use cheap deterministic extraction for simple fields;
- maintain an extraction budget per scheme;
- prioritise documents with expected label value;
- keep Parquet partitions by source snapshot/year/authority;
- profile storage and compute after 20 schemes before scaling.

### 23.2 LLM use

LLMs are a data-cleaning/extraction component, not the statistical proof.

- Never send documents blindly when a regex or table parser suffices.
- Store structured outputs and evidence, not just summaries.
- Review sensitive/low-confidence results.
- Keep the modelling dataset independent of a single proprietary LLM response format.
- Record model version and cost.

---

## 24. Decisions the coding agent may make

The coding agent may choose:

- DuckDB query structure and package boundaries;
- pandas versus Polars, if consistent with the existing repository;
- a documented geocoder and caching method;
- specific Python survival library;
- CLI framework;
- testing and logging libraries;
- file partitioning conventions.

The coding agent must not independently decide to:

- replace the existing planning model;
- broaden scope below 10 units for the pilot;
- treat ambiguous scheme links as truth;
- call PPR price differences “cost overruns”;
- train on confidential client outcomes;
- begin a nationwide PDF/OCR scrape;
- publish named team rankings;
- combine all outcomes into an unexplained score.

---

## 25. Open research questions

These should be logged rather than casually resolved in code:

1. Which date constitutes “final effective grant” across appeal and judicial-review cases?
2. Can BCMS completion data reliably identify scheme-level completion for multi-phase projects?
3. What fraction of granted 10+ unit schemes can be linked to BCMS at confirmed precision?
4. What PPR transaction coverage is achievable for build-to-sell schemes?
5. Can tenure/exit type be inferred reliably enough to determine PPR eligibility?
6. Which planning documents are consistently available across pilot authorities?
7. Can material redesign be labelled reproducibly from unit, height, site-layout and description changes?
8. Does planning friction improve activation prediction after controlling for year, type, scale and authority?
9. Does the existing refusal probability add signal to activation/delivery outcomes?
10. Are team-history features stable after shrinkage and coverage controls, or mostly identity/source artefacts?
11. Which outputs change an actual credit or acquisition decision?
12. What minimum evidence quality should cause the model to abstain?
13. Which councils have sufficiently stable, lawfully accessible documents for the pipeline, and which should be excluded from the pilot?
14. How should COVID and other exceptional regimes be represented without either erasing them or treating them as permanent?
15. Can substantive activation be corroborated at useful coverage beyond the administrative notice?

---

## 26. Immediate instructions for the coding agent

Begin with investigation and a thin vertical slice, not bulk collection.

1. Read the existing repository, README, model card, evaluation code and decisions log.
2. Produce the placeholder lender-credit report and obtain two structured reader reviews.
3. Reproduce the current frozen planning-model evaluation before modifying anything.
4. Create a source manifest for NPAD, BCMS and PPR, recording schema/licence/access observations.
5. Ingest small current snapshots into raw and bronze layers with hashes and tests.
6. Query the count and distribution of mature granted residential schemes of 10+ units, including COVID-exposure strata.
7. Propose the stratified 100-scheme cohort and export it for review.
8. Select 10 schemes for an end-to-end spike:
   - confirm application identity;
   - link BCMS candidates;
   - link PPR candidates if eligible;
   - retrieve only the planning documents necessary to identify friction;
   - produce a provenance-rich timeline.
9. Report linkage precision, coverage, missingness, storage used and compute cost.
10. Save the pre-committed stop/go rules.
11. Stop for review before scaling to 100 schemes.

The first useful output is not a machine-learning model. It is ten scheme timelines whose identities, events and evidence can be trusted. The first model should be fitted only after that foundation survives audit.

---

## 27. Definition of done for the first hand-off

The initial coding hand-off is complete when the repository contains:

- a documented, non-invasive integration with the frozen planning model;
- a reproducible source manifest and ingest pipeline for NPAD, BCMS and PPR;
- raw/bronze/silver data conventions with provenance;
- a canonical scheme/application/event schema;
- an audited ten-scheme vertical slice;
- a proposed and reviewable 100-scheme cohort;
- entity-resolution candidates and confidence states;
- activation labels with censoring;
- tests for schema, chronology and leakage;
- a written data-quality and feasibility report;
- no unjustified claim about cost overruns, physical commencement or complete court coverage.

After review, the next definition of done is a 100-scheme golden set and honest baseline survival analysis. Only then should the project expand its document corpus or model complexity.

---

## 28. Final product principle

The valuable object is not a fancy PDF generated in 30 seconds. It is the accumulated system behind it: verified longitudinal scheme identities, time-safe historical evidence, calibrated models, clear limitations and a result that can be tested against a lender’s own memory and records.

The model can remain statistically simple. In fact, simplicity is an advantage when the output must survive questioning. The defensibility must come from data integrity, longitudinal linkage, calibration, auditability and the discipline to say “insufficient evidence” when appropriate.
