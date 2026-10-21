# DevRisk Architecture Note (Sprint 0)

Status: working note for the development-risk engine extension. The frozen
planning model (v4-full) and its artifacts are untouched; this workspace is
strictly additive.

## 1. What exists and what is new

The repository already ships a frozen, calibrated submission-time planning
model (`05_policy/current/model_v4/national_residential_v4_full.joblib`,
version `national_residential_v4_full`) and a product surface
(`06_copilot/scripts/model_v4_playground.py`). Its public scoring interface is
`05_policy/scripts/model_feature_builder.score_proposal(proposal)`, returning
`{model_version, raw_ranking_score, refusal_probability, grant_probability,
risk_band, risk_band_thresholds, inputs}`.

New in `09_devrisk/` (per `docs/Irish_Residential_Development_Risk_Engine_Technical_Brief.md`):

- source manifest and stop/go gates (`configs/`);
- raw → bronze → silver → gold layers with hashed provenance manifests
  (`data/`, gitignored);
- canonical scheme/application/event/link/label schemas
  (`devrisk/entity_resolution/schemas.py`);
- transparent BCMS linkage candidates and confidence bands
  (`devrisk/entity_resolution/scoring.py`);
- censored activation labels, friction rule engine, PPR milestone labels
  (`devrisk/labels/`);
- Kaplan–Meier + discrete-time hazard baselines (`devrisk/models/survival.py`);
- non-invasive frozen-model adapter (`devrisk/models/planning_adapter.py`);
- CLI + runners (`devrisk/cli.py`, `scripts/`).

## 2. Integration contract with the frozen model

- Read-only: the adapter imports the existing scoring path; nothing is
  retrained or rewritten.
- Downstream models may consume the refusal score only when it is generated
  out-of-fold or time-safely for historical rows (brief §15.6). In-sample
  scores must never enter downstream training.
- The frozen evaluation (holdout metrics, calibration tables) is reproduced
  from saved artifacts in `05_policy/current/`, not recomputed here.

## 3. Data layers

- **raw** (`data/raw/`): immutable downloads + `.meta.json` sidecars (sha256,
  retrieval timestamp, URL). Overwrite only with an explicit new version.
- **bronze** (`data/bronze/`): source-shaped parquet with per-row hashes.
- **silver** (`data/silver/`): canonical tables — `bcms_events_silver.parquet`,
  `pilot_candidates_pool.parquet`, `pilot_candidates_100.parquet`, link
  candidates, activation labels, vertical-slice review workbook.
- **gold**: feature snapshots and model matrices (empty until Sprint 5+).
- **manifests** (`data/manifests/`): provenance JSON per artifact
  (`manifest_v1`): input hashes, source URL, retrieval time, transformation
  code/version, row/rejection counts, output hash, schema columns.

Every feature/label carries an `available_at`; `provenance.enforce_available_at`
fails builds when `available_at > snapshot_at`.

## 4. Cohort design (Sprint 2, in progress)

Candidate pool: mature granted residential schemes with ≥10 units, grant dates
2016-01-01..2022-12-31, ≥36 months follow-up by 2026-09-27. COVID exposure of
the 24-month at-risk window is computed from the official restriction dates
(2021-01-08 / 2021-04-12 / 2021-05-04) and stored per scheme. The stratified
100-scheme proposal (25% per size band) plus a review workbook is exported for
human review; no scheme is promoted to training without identity adjudication.

## 5. Identity and labels

- BCMS candidates: broad rules (500m buffer, county, unit tolerance, address
  tokens) then exposed match features (distance, token similarity, uncommon
  place-name agreement, unit diffs, exact planning-reference match, county
  match). Bands: confirmed / probable / ambiguous / rejected, each with a
  reason list for the audit workbook.
- PPR linkage: scheme -> confirmed BCMS address/eircode set -> PPR
  transactions (precomputed token sets; eircode, uncommon estate tokens,
  address similarity, sale-after-commencement chronology). Confirmed links
  feed exit labels; unlinked schemes are UNKNOWN on exit.
- Activation labels: censored time from final grant to first valid
  commencement; horizons 12/18/24/36m; corroboration tiers A/B/C; competing
  events recorded, never silently dropped. Only confirmed links count as
  events.
- Pain composite (`configs/rules/pain_v1|v2.yaml`): observed structured
  components (FI, appeal, durations, slow exit, below-market pricing) with
  published severity rules; raw components always retained; ground-truth
  field per component in `docs/LABEL_PROVENANCE.md`.
- PPR: milestone labels only for eligible tenure types; coverage denominator
  mandatory; PSRA reuse terms recorded (attribution required; no
  advertising-primary use).

## 6. Validation and leakage controls

- Temporal splits; schemes grouped before splitting (to be enforced when
  models are trained).
- Leakage tests: `available_at` enforcement, chronology invariants (grant ≥
  submission, commencement ≥ grant unless exceptional, sale ≥ first
  commencement), probability bounds, label window/eligibility presence,
  confirmed links carry evidence.
- Pre-committed stop/go gates: `configs/rules/pilot_gates.yaml` (frozen before
  results; see §17.6 of the brief).

## 7. Known decisions / open questions

- Stack: pandas + numpy + scipy + scikit-learn, matching the repository;
  survival code is dependency-free (KM with Greenwood CI; discrete-time
  logistic hazard). DuckDB/Polars/lifelines deliberately not introduced.
- PPR bulk download sits behind a form flow; only access notes recorded until
  a snapshot is lawfully obtained.
- Register coverage limits: 1,095 mature granted 10+ unit schemes in the
  national pool; SHD/ABP-era schemes are known to be under-covered (see
  Activate backtest in `state/HANDOFF_2026-09-24.md`).
- Open research questions from the brief §25 are tracked, not resolved in
  code.
