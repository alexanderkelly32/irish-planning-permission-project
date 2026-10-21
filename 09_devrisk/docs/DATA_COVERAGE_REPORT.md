# Data Coverage & Engine Readiness Report

Measured from the live data layers on 2026-09-28
(`09_devrisk/scripts/run_data_audit.py` →
`data/silver/data_coverage_audit.json`). Nothing below is extrapolated.

## 0. Authority records matrix (user research, 2026-09-28)

`docs/Ireland_Local_Authority_Development_Records_Matrix.xlsx` (parsed to
`silver/authority_records_matrix.csv`) documents per-authority record
availability. Key findings for our pipeline:

- **2014+ commencements/completions: NBCO covers ALL 31 authorities.** Our
  BCMS import is therefore the complete online source for the mature cohort
  (grants 2016-2022). The 61.9% linkage rate is a matching problem, not a
  data-availability problem.
- **Pre-2014 commencements: online only for Donegal (Dublin partly).** 26
  authorities need archive/FOI requests (template in the spreadsheet). Only
  relevant if the cohort is extended to pre-2016 grants.
- **Taking-in-charge lists/registers published for ~10 authorities** - a
  future completion/substantial-delivery evidence source.
- **Fire/DAC: public file access mostly unverified**; our BCMS
  CN_FSC_Number / CCC_FSC fields are the online route (35,913 / 22,421 rows).

## 1. All data sources

## 0b. GE10 coverage status (2026-09-28, post-extension)

The register is the ceiling: **3,585 GE10 rows** (national ArcGIS feed; known
feed gaps: SHD/ABP-era strategic-housing schemes 2018-2021, Cork data-quality
flag, Monaghan portal).

| Layer | Before | After extension |
|---|---|---|
| All-granted GE10 cohort (grant date recovered from decision date where missing: +535) | 1,916 | **2,421** |
| Mature granted (2016-2022) with pain labels | 1,095 | **1,384 (100% of mature)** |
| BCMS confirmed links (all-granted) | 765 (pool only) | **1,428** |
| BCMS linkage within mature window | 69.9% (pool) | **66.6%** (incl. 125 human-confirmed name links) |
| PPR confirmed links (all-granted) | 288 (pool only) | **413 (17.1%)** |
| Submission-time engines (a/b/e) | pool | **all 3,585 GE10 rows** |

By vintage: BCMS linkage 54-66% for 2016-2022 grants, declining to 32% for
2025 (notices still being filed) — recent-vintage coverage is time-bound,
not data-bound, and accrues automatically. PPR: ~19% mature, 7.9% for 2025
(sales not yet occurred). Pain labels now cover every mature granted GE10
scheme; recent grants are linked but label-pending until follow-up matures.

### Imported (in devrisk raw/bronze/silver, provenance manifests)

| Source | Rows | Coverage highlights | Used by |
|---|---|---|---|
| NPAD register (repo parquet) | 491,760 (1991-03 → 2026-01), 31 authorities | GE10: 3,585 rows; decision dates 3,189; grant dates 1,916 (53%); FI dates 59%; appeal dates 24.5%; eplanning links 66% | a, b, d, e, h, i, j, k, m |
| BCMS commencements/completions (NBCO CSV) | 249,127 (2001 → 2026) | geo 94% · planning ref 96% · completion record 41% · eircode 23% | f, h, j, k |
| PPR (PSRA bulk ZIP) | 807,724 (2010 → 2026-09) | dates/prices 100% · eircode 31% · 5.1% not-full-market | f(exit), g, h, j |
| Refusal-reason master (repo 03_refusal) | 1,411 cases (1,380 refused; 78% tagged) | human-verified theme tags | b |
| 04_fi request items (repo) | 166/1,095 pool schemes (15%) | quality remediation needed (ePlan boilerplate pages) | d, j |
| Condition starter labels | 17 verified planner reports | regex v1, 11 families | c |
| register_2026 pull | 26,880 rows (00_base) | already covered by main parquet through 2026-01 | — |

### NOT yet imported (ordered by product value)

| Source | Purpose | Blocker / next step |
|---|---|---|
| **Planner-report PDFs per authority** (Carlow+Meath pilot, 166 granted eplanning schemes queued) | grant conditions at scale (c), facts/evidence (j), cost-pressure (g) | runner built (`run_condition_corpus.py`); eplanning remote-disconnected from this environment — retry; then audit pack |
| **Macro construction/market series** (CSO material-cost indices, SCSI TPI, Euribor) | cost-pressure context (g), regime covariates | download + vintage manifests; sources in `configs/sources.yaml` |
| **Courts Service** (judgments, Planning & Environment List, Legal Diary) | positive JR evidence (d) | design positive-events table; never jr_absent from a failed search |
| Optional later: RZLT maps, ABP appeal records, Uisce Éireann, company filings | context features | post-pilot |

## 2. Engine-by-engine coverage and readiness

| # | Engine | Data coverage | Readiness |
|---|---|---|---|
| a | Planning outcome | complete (183k train / 35.7k holdout, frozen v4) | **READY** |
| b | Refusal reasons | 1,380 refused, 78% tagged; conditional priors + transfer | **READY** |
| c | Grant conditions | 17 labelled + corpus runner (crawl pending) | **BLOCKED ON IMPORT** |
| d | Friction | FI: 1,095 labels, AUC 0.69 — **READY**. Appeal/clarification/redesign: observed only (101 appeals = 9.2%), too few to model | FI ready; rest NOT modelled |
| e | Permission timing | 3,186 schemes (2014-2025); GBM beats baselines | **READY** |
| f | Activation/delivery/exit | BCMS links 69.9% · completion 655/730 commenced · PPR sales links 26.3% | **BASELINE ONLY** (hazard no signal; honest) |
| g | Cost pressure | description indicators + below-market benchmark; macro series missing | **EVIDENCE ONLY** |
| h | Comparables | full register + longitudinal milestones on linked subset | **READY** |
| i | Explanation | v4 exact contributions + GBM importances | **READY** |
| j | Facts & evidence | structured layers strong; document corpus at scale missing | **PARTIAL** |
| k | Unknowns / next-best evidence | generated from linkage flags | **READY** |
| l | Scenarios | v4 re-scores; timing variants pending | **READY** |
| m | Risk register | observed components | **READY** |
| n | Report + analyst review | markdown + PDF + overrides | **PROTOTYPE** |

## 3. Where coverage is genuinely thin

1. **Grant conditions (c): 17 labelled reports.** This is the single biggest
   functional gap in the shipped-module set. The corpus runner exists; the
   crawl needs a network retry, then an audit of ~50-100 reports.
2. **Appeal/clarification modelling (d): ~101 events.** Below the modelling
   floor; present as observed components, keep the FI model as the friction
   workhorse.
3. **PPR exit linkage (f): 26.3%.** Precision-first rules; more coverage via
   eircode/address work is possible but slow; exit stays baseline-only per
   the product scope decision anyway.
4. **Register GE10 grant-date coverage: 53%.** Limits the pain cohort to
   1,095 mature granted schemes; the 2026 register pull will grow this
   organically over time.
5. **04_fi corpus quality.** Only 15% of the pool and contains ePlan error
   pages; needs per-authority re-extraction (part of the c/j workstream).

## 4. Verdict

Enough data to run **a, b, e, h, i, k, l, m and the FI leg of d** at
prototype quality today. The remaining functional gaps are import problems,
not modelling problems: (1) planner-report corpus (retry crawl), (2) macro
series, (3) Courts positive-evidence table. Each has a defined next action;
none requires new modelling to unblock the pipeline.
