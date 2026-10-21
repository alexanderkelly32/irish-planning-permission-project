# Planning Intelligence — Pre-Submission Review: Product & Accuracy Brief

*Last updated 2026-09-24. Intended for a deep-dive reader (incumbent analysis, due diligence, product review). Everything below is measurable on the frozen holdout; nothing is extrapolated.*

---

## 1. What this is

A submission-time planning-risk product for Irish residential development. Input: seven fields (planning authority, free-text description, units, site area, floor area, ITM coordinates, submission year). Output: a refusal-probability score with evidence, a defensible brief (risk register, unknowns, next actions), a PDF report, and a portfolio with monitoring. Prediction time is defined as **immediately before submission** — the model consumes nothing that did not exist at that moment.

Positioning: a planner's augmentation, not a replacement. Every number ships with its confidence interval, its evidence source, and — where the data does not exist — an explicit "unverified" row instead of a guess.

The product runs as a Streamlit app: `06_copilot/scripts/model_v4_playground.py` ("Pre-Submission Review").

---

## 2. Product surface

### 2.1 The review (8 tabs)

| Tab | What it does |
|---|---|
| **Brief** | The working document: strengths, risk register (issue/evidence/severity/confidence/mitigation/owner/status), next actions grouped by owner, evidence-quality stamps, planner override with audit trail |
| **Verdict** | Headline score + risk band + calibration-range CI + GE10 percentile framing + driver decomposition + confidence notes + "what the model consulted" panel |
| **Precedents** | The 20 closest past applications matched on wording, unit count, density, council and recency (hard 5-year window, undecided excluded) — each with reference, dates, units, outcome, "why it matched" reasons, and inspector rationale where extracted |
| **Policy** | The development plan in force: the full objective list (council-specific, e.g. 263 objectives for DLR) with addressed/open/flag status, theme and search filters, ordering explained |
| **Site & map** | Nearby decisions map (granted/refused dots), OPW flood status, census small-area context, zoning (plan-versioned, four Dublin councils), national constraint layers, **boundary-draw ingestion** |
| **Wording** | Measured rewrites (granted-scheme phrasing, accurate-type additions, wording swaps) each rescored with a delta; adopt-only-if-accurate warnings; no LLM |
| **Scenarios** | Edit-a-scenario and lever-sweep sensitivity analysis with plain-language, non-causal deltas |
| **PDF report** | Branded, dated, evidence-cited: headline + calibration, drivers, matched precedents with rationale, policy crosswalk, site evidence, risk register, evidence quality, planner note |

### 2.2 The brief (risk register)

Every register row is one of two kinds:

- **Data-backed** — severity/confidence derived from evidence the project holds (OPW flood layers, matched-precedent outcomes, density-band history, council track record, NIAH/Natura/traffic proximity, plan-objective gaps). Example: *"Nearest NIAH-recorded structure 'X' is 40 m from the site point" → severity medium, confidence medium.*
- **Unverified** — where no data exists, the row says so and carries an owner and a confirm-action. Example: *"Wastewater capacity: unverified — confirm with Irish Water via a pre-connection enquiry."* A unit test enforces that no constraint severity is invented without data.

### 2.3 Portfolio, monitoring, audit

- SQLite store (`06_copilot/current/portfolio.sqlite`): projects, **append-only scoring events** (model version, inputs, timestamp — never overwritten), scenarios, evidence snapshots, overrides.
- Monitoring diffs each saved scheme against its snapshot and reports changes ("risk moved 11% → 14%"), honestly noting the register is a frozen snapshot through 2025-12-23.
- **Planner override**: records target/original/override/rationale/planner/timestamp; the model value is never modified. Appears in the brief and PDF.

### 2.4 Evidence engines

- **Matched precedents** (display engine): TF-IDF wording + unit-count closeness + density closeness + same-council boost + recency decay, restricted to decided applications received in the 5 years before submission. Display-only — the frozen scoring path is unchanged.
- **Council-vs-location check**: coordinates are verified against the distribution of nearby historical applications; mismatches are blocked with a red error.
- **Boundary-draw ingestion**: draw the site polygon → automatic ITM-projected area, density, and constraints-inside counts (NIAH, Natura, wastewater points, traffic counters) → one click applies the area to the proposal.
- **Development-plan crosswalk**: full objective list per council with addressed/open/flag; numeric extraction artifacts are dropped.
- **Constraint layers** (national, free, reproducible downloads): NIAH buildings, Natura 2000 SAC/SPA boundaries, EPA urban waste-water emission points, TII/TMU traffic counters.
- **Wording tools**: phrase effects measured on a standard baseline; three rewrite strategies with rescored deltas.
- **GE10 percentile framing**: where a score sits among the 464 large schemes decided 2024–25, with the observed refusal rate of that decile.
- **Transit proximity**: named public-transport stops within 800 m of the site (14,031-stop national table), shown as a strength in the brief.

### 2.5 Inputs and workflow

- **Seven inputs** with three location modes: council centre (with a fallback warning), **address/Eircode geocoding** (free Nominatim lookup, Eircode coverage patchy — falls back to street/town), or custom ITM coordinates.
- **Example description templates** (thin / standard / detailed 47-unit / real 314-unit SHD exemplar) for quick demos and benchmarking.
- **Pre-flight checks before scoring**: numbers in the description cross-checked against the units/site/floor fields; unknown words flagged against the model vocabulary with closest-match suggestions (typo catching — an out-of-vocabulary word silently costs signal).
- **Portfolio workflow**: save scheme → compare up to 4 side-by-side → load any saved scheme back into the review form → delete; scenarios (edit and lever sweep) saveable per project.
- **Append-only logging**: every scored action (review, scenario, wording variant, monitor rescore) records model version, inputs and timestamp.

---

## 3. Model accuracy (v4-full, frozen 22 Sep 2026)

**Protocol**: trained exclusively on applications received before 2024-01-01 (n=183,439); evaluated out-of-sample on all 35,713 residential applications decided 2024–2025. Isotonic calibration fitted on the 2023 window. Post-submission information (FI requests, refusal reasons, decision metadata, appeals) is excluded from features by construction.

### 3.1 All residential (holdout n=35,713, refusal base rate 11.96%)

| Metric | Value |
|---|---|
| Ranking ROC-AUC | **0.7920** (bootstrap 95% CI 0.7842–0.7980) |
| Average precision | 0.4093 |
| Brier (calibration) | 0.0901 |
| Log loss | 0.3125 |
| 2024 alone (n=20,492) | AUC 0.7872, AP 0.4069 |
| 2025 alone (n=15,221) | AUC 0.7983, AP 0.4131 |

### 3.2 Large schemes, 10+ units — the product focus (n=464, base rate 18.97%)

| Metric | Value |
|---|---|
| ROC-AUC | **0.7823** |
| Average precision | 0.5298 |
| Brier | 0.1247 |

Score quintiles on the same 464 schemes (actual refusal rate per model band):

| Model band | Actual refusal rate |
|---|---|
| Safest fifth | 1.1% |
| Second | 11.8% |
| Middle | 12.0% |
| Fourth | 21.5% |
| **Riskiest fifth** | **48.4%** |

- The riskiest **10%** refused at **63.8%** (exact 95% CI 49.5–76.0%); the safest 10% at **0%** (CI 0–7.6%). Fisher's exact p = 1.7 × 10⁻¹².
- The riskiest fifth contains 51% of all GE10 refusals; the top two fifths, 74%.

### 3.3 Risk bands and calibration display

Calibrated bands: **low ≤ 3.8%, medium 3.8–11.4%, high > 11.4%** (all-residential calibration; most 10+ unit schemes legitimately land in the high band — the app says so and shows the GE10 percentile instead of letting the band mislead). Per-band empirical ranges are shown with the score, e.g. the 50–60% band historically refused at 49% (95% CI 42–56%, n=206); the 30–40% band at 35.5% (CI 32.7–38.5%, n=1,027).

### 3.3a The "within ±X pp" calibration statistic (time-safe holdout)

Computed on the 2024–25 holdout with per-row as-of features (the honest
number; the app's displayed band CIs come from the 2023 calibration window):

| Predicted band | n | Mean predicted | Observed | Deviation |
|---|---|---|---|---|
| 0–3.8% | 14,501 | 3.8% | 4.5% | −0.8pp |
| 3.8–11.4% | 10,182 | 7.7% | 8.3% | −0.5pp |
| 11.4–20% | 5,967 | 15.3% | 16.5% | −1.2pp |
| 20–30% | 2,652 | 25.2% | 25.7% | −0.5pp |
| 30–40% | 1,177 | 33.0% | 32.5% | +0.6pp |
| 40–50% | 683 | 44.3% | 46.1% | −1.8pp |
| 50–60% | 164 | 52.1% | 47.6% | **+4.5pp** |
| 60–100% | 387 | 89.3% | 86.8% | +2.5pp |

- Weighted mean absolute deviation: **±0.8pp** (n=35,453).
- Every band up to 50% is within ±1.8pp of its midpoint; **97.9% of
  applications** sit in bands within ±2pp.
- **Large schemes (10+ units, n=464)**: mean predicted 18.1% vs observed 19.0%
  (−0.9pp); every bin with n≥44 within ±2.1pp. A GE10 recalibrator was
  measured and **not promoted** (state/DECISIONS.md 2026-09-24).

**Where the outliers come from** (theme exploration, 2026-09-24):
- The 50–60% over-prediction is **rural one-off dwellings with private
  wastewater treatment wording** ("treatment system", percolation, farm
  entrances; Louth/Kildare/Wexford/Wicklow/Dublin): the model over-weights
  the treatment-system signal that is also common in granted rural cases.
- GE10's worst bin (40–50%, n=23, −12pp) is **Dublin-heavy urban infill**
  refused on design_layout / land_use_policy / traffic_access — the
  "paper can't see drawings" pattern.

### 3.5 Activate Capital portfolio backtest (2026-09-24)

Time-safe, per-submission-date retraining of the v4-faithful pipeline on 11
register-matched Activate schemes (all granted), with matched controls
(`05_policy/scripts/run_activate_backtest.py`,
`05_policy/current/activate_backtest_2026-09-24.*`):

- **Σpᵢ = 1.97 expected refusals vs 0 actual** — consistent with calibration
  (Poisson 95% CI for 0 events at λ≈2: [0, 3.7]); the model does not
  over-flag a lender-vetted portfolio.
- **Controls (same authorities, ±12 months): refused 37.1% vs granted 25.5%
  mean predicted risk (+11.6pp)** — correct direction.
- Top flags and their drivers: Trinity Collection 45.5% (comparable set 40%
  refused + zoning-plan profile + BTR wording), Barnhill Place 43.0% (DLR
  council fixed effect + 230-objective plan; thin description), Millerstown
  35.0% (Kildare 12-month refusal streak 23.9% + road/access wording).
- **Coverage finding**: 14 of the 25 portfolio schemes are not cleanly in the
  register (SHD/ABP era under-coverage) — a data-freshness gap to close, not
  a model finding.

### 3.4 Known failure patterns (from the systematic error autopsy)

1. **Missed refusals** — 12 of 88 GE10 refusals were scored mild: standard suburban estates whose refusals were site-specific (design detail, services, local objection). These have no close precedents and are flagged as lower-confidence.
2. **False alarms** — 121 of 376 grants flagged risky: specification-heavy urban apartment schemes (long professional descriptions, Dublin-heavy). Disclosed as a caution, not hidden.
3. **Specialised schemes** (senior living / care): ranking is fine (AUC 0.79) but probabilities understate risk (model ~15–20% vs observed ~27–35%). The app discloses the specialised prior (n=105) alongside the score.
4. **Type-coded SHD descriptions** ("type b", "c1/c2"): checked and *not* a problem — they refuse at 7.7% vs 21% untyped, and ranking is adequate.

### 3.5 Baselines and candidates

- Frozen **v3** reference: 2025 ROC-AUC 0.7989, AP 0.4202. v4-full is the promoted candidate; v3 remains the untouched baseline.
- **v5 structured optimiser** (planner-report fields): not promoted — beats v4 on AUC but below on AP; report variables too sparse on the holdout (state/DECISIONS.md 2026-09-13).
- **v5 theme classifier**: not promoted (see §4).

---

## 4. Refusal-reason capability (honest framing)

v4-full predicts **probability, not reasons**. The product surfaces "grounds" by transferring the extracted refusal themes of time-safe matched refusals. Measured leakage-free on the refused GE10 holdout (n=81):

| Method | Top-1 | Top-2 | Top-3 |
|---|---|---|---|
| Majority baseline ("always design_layout") | 24.7% | — | — |
| Precedent-transfer engine (shipped) | 16.0% | 38.3% | **55.6%** |
| v5 logistic classifier (C=0.3) | 18.5% | 35.8% | 54.3% |
| v5 logistic classifier (C=1) | 19.8% | 28.4% | 46.9% |

Conclusion recorded in state/DECISIONS.md (2026-09-24): **no submission-time method beats the majority baseline on top-1**, and the classifier only ties the transfer engine on top-3. The primary refusal ground usually lives in drawings, site objections and services — not in submission data. The product therefore claims only "the real ground is usually in our top-3 surfaced themes (~56%)" and does not claim ground-level prediction.

**Theme coverage** (the labels behind the above): refused GE10 decided 2021–2025 with an extracted primary theme: **610/672 (91%)**, up from 81% after the 2026-09-24 extraction campaign (122 DeepSeek extractions, 67 with reasons, cost $0.59). Remaining gaps: 7 Monaghan (documents left eplanning), a few link-blocked councils, and LLM-no-reason cases.

---

## 5. Data assets

| Asset | Size / coverage |
|---|---|
| National register | 219,152 rows, 1992–2025-12-23 (frozen snapshot; decisions after are not ingested) |
| Comparable reference (scoring) | 7 scheme buckets, 183,439 pre-2024 rows, TF-IDF 80k (1,2)-grams — frozen, alignment-verified |
| Comparable display metadata | row-aligned app refs, dates, units, outcomes + inspector rationale (3 merged sources: retagged canonical master 1,411 rows, GE10 master, new LLM extractions) |
| Recent precedent pack | ~143,800 rows received 2019+; 10+ units bucket: 1,562 rows, 865 with rationale |
| Refusal themes | 11-theme vocabulary, evidence-bound extraction; national frequency table (traffic 1,014, design 444, flooding 243, …) |
| Development plans | objective_code_layer.csv: 11,328 objective rows across 31 councils, plan-period-versioned |
| Census | 2022 small areas (16,838) — density, tenure, cars, septic |
| Flood | OPW NCFHM/NIFM per case point (219k points) |
| Transit | 14,031 named stops |
| NIAH | 48,327 recorded structures (ITM) |
| Natura 2000 | 632 sites (433 SAC + 199 SPA), ITM boundaries |
| EPA wastewater | 3,434 urban discharge points (TM65→ITM converted) |
| TII traffic | 308 counter locations |
| GE10 holdout | all 464 schemes scored with outcomes (ge10_scored_2024_25.csv) |

All layers are national, free, and reproducible via committed download/build scripts (`07_context/scripts/`).

---

## 6. Engineering and integrity controls

- **Submission-time boundary**: FI, refusal reasons, decisions, appeals excluded from model features by construction (rationales are displayed as evidence, never inputs).
- **Frozen artifacts**: scoring reference and model are frozen; the display metadata builder re-derives the row ordering and fails loudly if alignment breaks.
- **Append-only audit**: every scored event records model version, inputs and timestamp; nothing is overwritten; planner overrides are explicit and separate from the model value.
- **Honest uncertainty**: calibration CIs, "few close precedents", fallback naming (council-centre coordinates, missing floor area), and specialised-prior disclosure are features, not footnotes.
- **Tests**: 35 unit tests across evidence/wording/portfolio/report/brief services plus full AppTest flow coverage (review → brief → override → PDF → portfolio → monitoring).
- **Cost discipline**: the DeepSeek extraction pipeline is billing-safe (checkpointed, resumable, balance-aware); campaign cost tracked ($0.59 for 122 extractions).

---

## 7. Known limits (stated plainly)

- Register frozen at 2025-12-23; 2026 data exists but is decision-censored — monitoring is honest about this.
- Cork County decisions carry a data-quality flag (9 Cork holdout refusals absent from the recent pack — under investigation).
- Zoning is plan-versioned for the four Dublin councils only; elsewhere it is an explicit "unverified — confirm from the plan map" row.
- Wastewater **capacity** is not published nationally — proximity to EPA discharge points is shown, capacity is not.
- Free-text phrasing measurably moves the score (precedent-magnetism, not word magic) — disclosed, with measured rewrites making it visible.
- The model reads paper, not drawings: some refusals are not predictable from submission data. That is the ceiling, not a bug.
- Reason prediction is bounded as in §4.

---

## 8. Roadmap (live in state/ROADMAP.md)

1. Boundary-draw follow-ups (persist polygon, auto-rescore, polygon flood check) — days.
2. **Planning-pack ingestion** (architect PDF → scheme fields) — ~3 months, the next major capability.
3. More refusal-theme labels: retry no-reason cases (~$0.30); extend to 2–9 unit refusals (~$5–15); Monaghan portal branch.
4. Validation extras: paraphrase-robustness sweep, same-site grouping, 2026 readout.
5. Constraint residuals: ACA/TPO polygons, council RPS data, national zoning.
6. Live register feed for monitoring alerts.
7. Pricing experiments, pilots and the commercial wedge — owner: product decision.

*All explanations are model-attributed sensitivity statements built from historical rates — not guarantees and not planning advice.*
