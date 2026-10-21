# Initial Development Risk Report

## Product and output brief

**Status:** Working specification  
**Prepared:** 27 September 2026  
**Market:** Irish residential development, initially schemes of 10+ units  
**Primary reader:** Development lender underwriting/credit professional  
**Secondary reader:** Developer, investment or land/acquisitions professional  

---

## 1. Purpose

Build an analyst-reviewed report that assembles the known facts about a proposed or existing residential development, applies calibrated statistical models, identifies material unknowns and shows the historical evidence behind the estimates.

The report should allow an experienced professional to reach a better-informed decision more quickly. It should not attempt to make the investment, lending, planning, legal or design decision for them.

The product promise is:

> All relevant facts, all supportable probabilities, all material unknowns and the strongest comparable evidence—assembled in one place while the professional retains judgment.

The report is valuable only where it does at least one of the following:

- removes manual research;
- surfaces a material fact or dependency that might otherwise be missed;
- quantifies an uncertainty currently handled by intuition;
- shows how long a milestone is likely to take;
- identifies which missing information creates the greatest forecast uncertainty;
- makes alternative scheme configurations directly comparable;
- prevents false confidence by identifying weak evidence or unsupported extrapolation.

---

## 2. Product boundary

This brief concerns the **initial report produced at one defined analysis date**. The founder/analyst receives the scheme information, validates the inputs, runs the models, reviews the generated evidence and issues the report.

### Included

- scheme identity and application-family verification;
- structured factual evidence;
- planning grant/refusal probability;
- likely refusal reasons conditional on refusal;
- likely condition families conditional on grant;
- planning-friction probabilities;
- predicted permission timing;
- predicted activation, completion and eligible exit timing only where the respective models have passed validation gates;
- evidence-backed risk register;
- longitudinal comparable schemes;
- material unknowns;
- next-best evidence ranked by forecast uncertainty;
- scenario comparison/frontier;
- scheme-specific cost-pressure evidence;
- evidence, confidence, calibration and methodology appendices.

### Excluded from this version

- monitoring after the report date;
- automatic alerts;
- sequential re-scoring as later events occur;
- parsing actual conditions after a future grant;
- condition-discharge tracking;
- portfolio dashboards;
- automated lender covenants or conditions precedent;
- assigning tasks to planners, engineers, solicitors or borrowers;
- recommending `lend`, `buy`, `walk away`, `approve` or `reject`;
- risk-adjusted land valuation, maximum bid or loan pricing;
- project-specific cost-overrun prediction;
- replacing planning, engineering, valuation or legal advice.

The architecture may preserve the ability to add later snapshots, but none of those later products is required for this initial-report build.

---

## 3. Operating workflow

The first commercial version is a managed analytical service, not unrestricted self-service software.

1. Customer supplies a scheme description and available documents.
2. Analyst creates or confirms the scheme record.
3. System identifies related applications, documents and public evidence.
4. Analyst resolves material identity/input conflicts.
5. Models generate forecasts and scenario results.
6. System produces a draft report and source appendix.
7. Analyst reviews the evidence, removes unsupported statements and records overrides.
8. Final report is issued with a fixed `as_of` date, model versions and source snapshot.

No report should be issued automatically while material scheme-identity conflicts remain unresolved.

---

## 4. Output language

Every material statement must be visibly classified as one of four types:

| Classification | Definition | Example |
|---|---|---|
| **Observed fact** | Directly supported by a source document/register | “The proposal comprises 184 units.” |
| **Model estimate** | A validated prediction with event/horizon/calibration context | “Estimated ultimate refusal probability: 18%.” |
| **Analytical inference** | Reasoned interpretation, not directly observed or statistically validated | “The description suggests reliance on off-site road works.” |
| **Unknown** | Material information the system could not establish | “Confirmed wastewater capacity was not found.” |

Rules:

- Missing evidence must not silently become `no` or `absent`.
- A predicted condition must never be presented as an imposed condition.
- Association must not be described as causation.
- The report must identify when a result is driven mainly by a local-authority/location prior rather than detailed scheme evidence.
- The report must abstain where the scheme is outside the model’s supported range or evidence is inadequate.

---

## 5. Required customer inputs

Minimum viable inputs:

- site address/location;
- scheme description;
- proposed unit count;
- houses/apartments/mixed;
- current planning stage;
- known planning reference, if any;
- site area where known;
- available application/design documents.

Desirable inputs:

- unit mix and tenure;
- floor area and density;
- height/storeys;
- phase structure;
- access arrangement;
- parking;
- demolition/basement information;
- planning history;
- known infrastructure position;
- alternative scenarios the client wishes to test.

For each customer input, preserve:

- raw supplied value;
- normalized value used by the model;
- source/customer attribution;
- confidence;
- analyst correction history.

---

## 6. Canonical report outputs

The following are modules, not fixed pages. The report should be as short or long as the evidence requires.

### 6.1 Scheme identity and analysis snapshot

Confirm exactly what is being analysed:

- canonical scheme/site name;
- known aliases/marketing names;
- address, townland, coordinates and local authority;
- base planning application and related known references;
- master scheme/phase relationship;
- proposed/current/granted units, with dates;
- scheme type and tenure where known;
- applicant/developer names as observed;
- current lifecycle stage;
- analysis `as_of` date;
- scheme-identity confidence;
- unresolved identity or phase conflicts;
- source-coverage summary.

The customer must be able to correct this section before final issue.

### 6.2 Structured facts pack

Expose the facts used in the analysis.

#### Scheme and design

- units and mix;
- site area, density and floor area;
- height/storeys and blocks;
- houses/apartments/mixed;
- tenure;
- parking;
- access arrangement;
- demolition, basement and phasing.

#### Planning history

- relevant application references;
- validation, decision and appeal dates;
- historical decisions;
- FI, clarification, observations and appeals;
- amendments/extensions;
- proposed/revised/granted unit changes;
- relevant plan objectives/policies;
- known decision reasons and conditions from historical linked cases.

#### Infrastructure, physical and environmental

- road/access information;
- drainage, water and wastewater;
- utility and off-site infrastructure dependencies;
- flood evidence;
- ecology and archaeology;
- protected structures/conservation;
- contamination/ground/excavation;
- enabling works and phasing.

#### Statistical context

- local-authority historical outcomes;
- recent local/spatial outcomes;
- comparable-application history;
- comparable count and similarity quality;
- commencement/delivery history where modelled;
- relevant market/cost context.

Each fact should carry its source, date, evidence location, extraction method, confidence and conflicts.

### 6.3 Analytical summary

Provide a compact snapshot of the validated outputs available for this scheme.

| Output | Required presentation |
|---|---|
| Ultimate planning outcome | Calibrated grant/refusal probability and band |
| Refusal detail | Likely reason families conditional on refusal |
| Grant detail | Likely condition families conditional on grant |
| Planning friction | Component probabilities and named exposures |
| Final/usable permission | P20/P50/P80 timing or fixed-horizon probabilities |
| Administrative commencement | Fixed-horizon probabilities if validated |
| Substantive activation | Only if its evidence/model gates pass |
| Completion | Only if model/linkage gates pass |
| Eligible exit | Only for defensible build-to-sell cases |
| Cost pressure | Evidence-backed exposure categories |
| Evidence quality | Coverage, identity confidence and principal unknowns |

End with three neutral statements:

1. strongest observed or modelled risk signal;
2. material unknown creating the greatest uncertainty;
3. forecast most affected by that unknown.

Do not provide a single overall “headache” score or a commercial recommendation.

### 6.4 Where did this number come from?

Immediately after the analytical summary, explain how each headline estimate was formed. This should be one of the report's distinctive features: a scheme-specific interrogation of the actual model, rather than generic explanatory text.

The explanation must begin with a structured model-output payload. AI may interpret and synthesize that payload, but it must not invent drivers, causal stories or planning opinions that are absent from the model and evidence.

#### Required structured explanation

For each headline probability or milestone forecast, expose:

- relevant baseline/cohort rate;
- raw model score before calibration;
- calibrated probability;
- strongest probability-raising feature groups;
- strongest probability-lowering feature groups;
- direction and magnitude on the model's native scale;
- one-at-a-time counterfactual probability movement where statistically valid;
- actual subject-scheme feature value;
- comparison with the relevant training/peer distribution;
- source evidence for the feature;
- whether the driver is scheme-specific, local-authority/location context, text-derived, comparable-derived or macro/contextual;
- missingness/coverage that caused the model to rely on a broad prior;
- interactions/non-linear transformations where present;
- model/version/snapshot used.

Suggested table:

| Driver | Direction | Relative strength | Subject value | Peer context | Evidence | Driver type |
|---|---|---:|---|---|---|---|
| Close-comparable refusal rate | Raises | High | 35% across supported peers | Above cohort median | Comparable table | Scheme-specific history |
| Recent authority refusal rate | Raises | Moderate | Recorded value | Above period baseline | Time-safe authority history | Contextual prior |
| Scheme scale | Lowers | Moderate | 184 units | Larger than cohort median | Application description | Structured scheme feature |
| Description coverage | Warning | — | Thin | Below cohort median | Source description | Evidence quality |

#### Narrative synthesis

The AI-generated explanation should answer:

1. What moved the estimate upward?
2. What moved it downward?
3. Which drivers were genuinely scheme-specific?
4. Which parts came from broad location/authority priors?
5. Which comparable outcomes materially influenced the result?
6. Did sparse or conflicting evidence cause the model to fall back on priors?
7. Which apparently important facts had little model effect?
8. What should the reader be careful not to infer from the explanation?

The prose should be tailored to the scheme and may vary in structure according to what is genuinely important. It should not be randomly different when the same report is regenerated: the evidence, driver ranking and substantive explanation must remain reproducible for the same input/model version.

#### Linear-model and calibration requirements

Because the current model is linear/logistic and then calibrated:

- retain exact feature contributions on the model's native score/log-odds scale;
- group thousands of sparse/text features into interpretable themes without losing the underlying feature list;
- preserve access to individual coefficients/features for audit;
- do not claim that calibrated probability-point differences add linearly;
- clearly label any “probability without this feature/group” calculation as a one-at-a-time counterfactual sensitivity;
- do not sum counterfactual probability movements as though independent;
- retain both the raw score explanation and final calibration mapping.

For isotonic calibration in particular, the calibrated result may change discontinuously and individual features do not possess a unique additive contribution in calibrated probability points. The report should therefore rank exact native-scale contributions and use probability deltas only as carefully labelled sensitivities.

#### Text-feature explanation

For TF–IDF or other text-derived contributions:

- show the exact source phrase/span where possible;
- identify the underlying tokens/features that affected the model;
- group related tokens into an intelligible topic only when the grouping is traceable;
- distinguish a meaningful planning theme from an incidental lexical correlation;
- suppress unstable single-token stories;
- allow the reader to inspect the ungrouped model features in the appendix.

#### AI grounding contract

The explanation generator receives only:

- structured contributions;
- subject feature values;
- calibration output;
- source-backed fact objects;
- comparable records;
- approved model/feature definitions;
- evidence-quality flags.

It returns a schema containing driver claims, source references, model references, cautions and narrative. Every sentence that states a factual driver must map to at least one structured contribution and evidence reference. Unsupported claims fail validation and are removed or sent for analyst review.

The analyst must be able to open the underlying contribution record from every driver shown in the report.

#### Interpretation warning

A model driver is not automatically a real-world cause. Correlated features can share or substitute for signal, and a coefficient can reflect historical patterns rather than a mechanism. Use language such as “raised the model estimate” rather than “caused the planning risk.”

### 6.5 Planning outcome forecast

Required fields:

- probability of ultimate refusal;
- local-authority decision probability, if separately validated;
- calibration band;
- relevant cohort base rate;
- risk percentile among supported peers;
- strongest upward/downward model contributions;
- degree of scheme-specific versus location-prior reliance;
- description/document coverage;
- comparable support;
- out-of-distribution warning;
- model/data version.

Display model contributions as explanations of the estimate, not proof of causality.

### 6.6 Likely refusal reasons

Conditional output:

`P(reason_family | ultimate_refusal, current_information)`

Possible reason families:

- access/traffic safety;
- density/overdevelopment;
- design/visual impact;
- residential amenity;
- policy/zoning conflict;
- wastewater/drainage;
- flood risk;
- ecology/environment;
- heritage/conservation;
- insufficient information/technical evidence;
- other validated categories.

For each family show:

- conditional probability/band;
- source features;
- comparable frequency;
- example supporting peer cases;
- evidence/model coverage;
- overlap warning because decisions can contain multiple reasons.

### 6.7 Likely grant conditions

Conditional output:

`P(condition_family | ultimate_grant, current_information)`

Possible families:

- roads/access/transport;
- drainage, wastewater and water;
- construction/environmental management;
- archaeology/ecology/conservation;
- flood mitigation;
- landscaping/open space/public realm;
- design/material changes;
- Part V, bonds and contributions;
- phasing/occupancy/tenure;
- pre-commencement submissions;
- pre-occupation certification/infrastructure.

For each family show:

- probability if granted;
- supporting evidence/features;
- frequency among close granted peers;
- routine/programme-sensitive classification only where empirically supportable;
- likely timing class where statistically supportable;
- uncertainty and coverage.

Additional possible outputs:

- predicted condition-count range;
- probability of one or more material pre-commencement condition families;
- probability of a condition involving third-party infrastructure confirmation.

Do not generate exact legal wording or present the conditions as already imposed.

### 6.8 Planning-friction forecast

Expose the components separately:

- FI probability and likely topic families;
- clarification probability;
- first-party appeal probability;
- third-party appeal probability;
- material redesign probability;
- expected unit-reduction range, if validated;
- likely condition burden;
- amendment/extension risk;
- judicial-review positive evidence or unknown coverage;
- expected time to local decision;
- expected time to final permission.

A low/moderate/high friction grouping may be added, but never replaces the components.

### 6.9 Milestone forecast

Potential milestones:

- local-authority decision;
- final/usable permission;
- administrative commencement;
- corroborated substantive activation;
- first/substantial completion;
- eligible first sale and sell-through milestones.

For every output state:

- event definition;
- clock origin: report date, submission, final grant or commencement;
- P20/P50/P80 date or duration;
- probability within relevant fixed horizons;
- conditional probability where appropriate;
- whole-path probability where appropriate;
- uncertainty interval;
- evidence/model maturity;
- censoring/follow-up status in the evaluation data.

Examples that must remain distinct:

- commencement within 24 months **conditional on grant**;
- final permission within 18 months **from submission**;
- substantive commencement within 36 months **from the report date**.

### 6.10 Evidence-backed risk register

This is a structured inventory, not a diligence plan.

| Field | Required content |
|---|---|
| Risk/dependency | Specific issue |
| Category | Planning, infrastructure, physical, programme, cost pressure, delivery or exit |
| Evidence class | Fact, estimate, inference or unknown |
| Current status | Present, predicted, possible, resolved or unknown |
| Likelihood | Probability/band only where validated |
| Relevant milestone | Forecast associated with the issue |
| Historical association | Rate/effect where statistically valid |
| Direct evidence | Source document/page/register event |
| Peer evidence | What happened in comparable schemes |
| Confidence/coverage | Source, extraction, linkage and model support |
| Missing information | Exact unresolved fact |
| Resolving evidence | Document/confirmation that would answer it, if identifiable |

Candidate categories:

- refusal reasons and policy conflict;
- likely grant-condition families;
- FI/clarification/appeal/JR evidence;
- roads/access/transport;
- drainage/wastewater/water/utilities;
- flood/ecology/archaeology/conservation;
- demolition/ground/contamination;
- density/design/unit loss;
- phasing/enabling works;
- commencement and delivery uncertainty;
- cost pressure;
- exit eligibility/uncertainty;
- evidence gaps.

The register must not assign a responsible professional, prescribe mitigation or guarantee a consequence if unresolved.

### 6.11 Longitudinal comparable schemes

Show approximately 10–20 peers, subject to evidence quality.

For each:

- planning reference, location and source links;
- match rationale;
- similarity score and comparable confidence;
- important similarities and differences;
- proposed/granted units and scheme type;
- planning outcome;
- FI/appeal/redesign;
- relevant conditions;
- time to final permission;
- administrative commencement;
- corroborated progress where available;
- completion/eligible exit evidence;
- time between milestones;
- scheme identity/link confidence.

The user should be able to reject a weak comparable. Selection must be reproducible and time-safe.

### 6.12 Material unknowns

List every material fact that could not be established.

For each:

- exact unknown;
- why it matters to a named forecast;
- affected report sections;
- whether it is absent, conflicting or inaccessible;
- document, confirmation or future event that could resolve it, if known;
- current uncertainty/coverage.

Unknowns are first-class outputs, not omissions to conceal.

### 6.13 Next-best evidence

Rank unknowns by their estimated contribution to forecast uncertainty.

For each:

- unknown variable/fact;
- forecast affected;
- current plausible forecast range;
- evidence that could resolve it;
- whether the evidence is public, customer-held or unavailable;
- estimated narrowing of uncertainty or scenario movement;
- confidence in the information-value estimate.

The output does not decide who should obtain the evidence or what commercial decision should follow.

### 6.14 Scenario frontier

Allow the analyst to rerun supportable alternatives cheaply.

Candidate variables:

- unit count;
- density;
- height/storeys;
- houses/apartments/mix;
- site coverage;
- tenure assumptions;
- access-related design/input;
- evidence-backed infrastructure state;
- other features genuinely represented in the trained model.

For every scenario show:

- exact changed inputs;
- all material unchanged assumptions;
- grant/refusal probability;
- likely refusal reasons;
- likely grant conditions;
- friction probabilities;
- P20/P50/P80 permission timing;
- later milestone changes where validated;
- difference from the base case;
- comparable/historical support;
- extrapolation warning;
- model version.

Where useful, show a frontier such as units versus refusal probability versus P80 permission time. Do not describe sensitivity as proof that the change will cause the forecast movement.

### 6.15 Cost-pressure evidence

This module remains factual and scheme-specific.

Candidate exposures:

- basement/underground works;
- demolition;
- abnormal ground/excavation;
- contamination/remediation;
- flood measures/pumping;
- abnormal water/wastewater/drainage;
- utilities and off-site infrastructure;
- major roads/junction works;
- protected structures;
- archaeology/ecology;
- complex phasing/enabling works;
- redesign/unit-loss exposure;
- delay during adverse construction-cost, materials or funding regimes.

For each show:

- observed/predicted/unknown status;
- direct evidence;
- extraction confidence;
- relevant peer evidence;
- statistically valid timing association, if any;
- contemporaneous index context;
- missing information.

Do not convert this into an exact cost overrun or euro estimate without verified private budget/outturn data.

---

## 7. Evidence and methodology appendix

The report should include or link to:

- source-document index;
- short evidence extracts with page references;
- full comparable table;
- match and scheme-identity evidence;
- input feature summary;
- model name/version/training cutoff;
- prediction snapshot date;
- calibration and relevant holdout performance;
- subgroup/sample-size warnings;
- coverage/missingness;
- scenario support/extrapolation details;
- limitations and abstentions;
- analyst changes/overrides.

Every probability must state:

1. event;
2. horizon;
3. clock origin;
4. information snapshot;
5. estimate;
6. uncertainty/calibration context;
7. model version;
8. major coverage limitation.

---

## 8. Rendered deliverables

The same canonical output object should support:

- analyst-reviewed PDF/report of variable length;
- source-linked evidence table;
- scenario comparison table;
- CSV/JSON export;
- internal analyst QA view.

There is no fixed page count. Empty or unsupported modules should be omitted or marked unavailable rather than padded with generic prose.

---

## 9. Analyst QA before issue

Required checks:

- scheme/application/phase identity confirmed;
- customer inputs reconciled with public evidence;
- no future information leaked into snapshot features;
- facts, estimates, inferences and unknowns visibly distinguished;
- every material extracted fact has evidence;
- model outputs use the correct lifecycle snapshot;
- conditional probabilities are labelled as conditional;
- comparables are relevant and not cherry-picked;
- scenarios remain within support or show extrapolation warnings;
- no recommendation or professional conclusion is generated;
- unsupported activation/completion/exit modules are omitted;
- report/model/source versions are frozen.

Analyst overrides must record the original value, replacement, reason, evidence and reviewer.

---

## 10. Version-one priorities

### Must ship

1. Scheme identity and snapshot.
2. Structured facts pack.
3. Calibrated planning outcome.
4. “Where did this number come from?” model-driver explanation.
5. Likely refusal-reason families.
6. Likely grant-condition families.
7. Planning-friction components.
8. Permission-time forecast.
9. Evidence-backed risk register.
10. Longitudinal comparables.
11. Material unknowns and next-best evidence.
12. Scenario frontier.
13. Evidence/methodology appendix.

### Ship only if validated in time

- administrative commencement forecast;
- substantive activation forecast;
- completion forecast;
- eligible exit forecast;
- full cost-pressure modelling beyond extracted indicators.

### Explicitly deferred

- post-report monitoring and alerts;
- sequential state updates;
- actual future condition replacement/tracking;
- portfolio view;
- automated diligence instructions;
- financial/acquisition recommendations;
- self-service customer access to unrestricted scoring.

---

## 11. Acceptance criteria

The initial report product is ready for a friendly lender/developer pilot when:

- a scheme can be reproduced from saved inputs and source snapshots;
- identity and phase evidence are visible;
- the existing planning probability and calibration are reproduced correctly;
- every displayed model driver is traceable to an exact contribution, feature value and source-backed fact;
- the AI narrative is reproducible in substance and contains no unsupported causal explanation;
- refusal reasons and grant-condition outputs have audited labels and field-level validation;
- permission timing beats declared simple baselines and is calibrated at useful horizons;
- every risk-register row distinguishes fact, estimate, inference or unknown;
- comparable selection is reproducible;
- next-best evidence is tied to a named uncertainty, not generic advice;
- scenario changes are reproducible and support warnings work;
- unsupported modules abstain cleanly;
- an analyst can inspect and correct the draft before issue;
- a target professional can identify the evidence behind every important claim.

The final pilot question is not whether the report looks impressive. It is whether the reader can complete a real scheme review faster, discover something material they did not already know, or replace an unsupported assumption with a defensible probability or unknown.
