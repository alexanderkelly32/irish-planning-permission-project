# Architecture

## Current runtime (v4, updated 2026-09-24)

The product is the Streamlit app `06_copilot/scripts/model_v4_playground.py`
("Pre-Submission Review"), backed by a frozen scikit-learn model bundle and
file-based reference tables. Current session handoff: `state/HANDOFF_2026-09-24.md`.

**Scoring path (frozen, do not modify):**
- `05_policy/current/model_v4/national_residential_v4_full.joblib` — ranking
  pipeline (TF-IDF (1,3) 50k + numerics + council/bucket OHE; balanced
  liblinear C=0.5), calibrated base model, isotonic calibrator, thresholds.
- `model_v4/comparable_reference.joblib` — frozen pre-2024 TF-IDF reference
  for the comparable aggregates.
- Query-time feature builder: `05_policy/scripts/model_feature_builder.py`
  (`build_feature_row` / `score_proposal`), using reference tables in
  `07_context/current/` (sa_reference, flood_points, plan_summary,
  history_reference) and the constraint tables.

**Display/evidence layer (additive only):**
- `06_copilot/scripts/v4_evidence_service.py` — matched precedents
  (`recent_precedents_reference.joblib`, 5-year window), plan crosswalk,
  site context, constraint lookups, boundary-draw ingestion, calibration
  band CIs, GE10 percentile framing.
- `v4_brief_service.py` — risk register, next actions, evidence-quality stamps.
- `v4_wording_service.py` — measured rewrite variants (no LLM).
- `v4_report.py` — fpdf2 PDF report (vendored).

**State:** `06_copilot/current/portfolio.sqlite` (`v4_portfolio_store.py`) —
projects, append-only score events, scenarios, snapshots, overrides. Gitignored.

**Display packs:** `05_policy/current/model_v4/comparable_metadata.joblib` +
`recent_precedents_reference.joblib`, rebuilt by
`05_policy/scripts/build_comparable_metadata.py` (alignment-verified against
the frozen reference; merges three rationale sources — retagged canonical
master, GE10 master, new LLM extractions).

**Data pipelines (reproducible):**
- `03_refusal/scripts/run_refusal_coverage.py` — gap/download/ocr/prepare/
  merge refusal-reason extraction; LLM batch via
  `02_development/scripts/run_deepseek_extraction.py` (billing-safe).
- `07_context/scripts/download_constraint_layers.py` +
  `build_constraint_reference.py` — NIAH / Natura 2000 / EPA wastewater /
  TII traffic query tables.
- Evaluations: `05_policy/scripts/run_activate_backtest.py`,
  `build_reason_prediction_eval.py`, `build_v5_theme_classifier.py`,
  `build_ge10_recalibration.py`.

## Target domain model

The long-term system should separate:

- `Site`: physical location, geometry, authority, zoning and planning history.
- `Application`: statutory submission, dates, source identifiers and outcome.
- `Scheme`: proposed physical characteristics and their provenance.
- `Document`: source documents and page/chunk citations.
- `ModelRun`: immutable prediction with model/calibration/input metadata.
- `Scenario`: copy of a scheme plus explicit field deltas and its ModelRun.

The portfolio store is the first durable step; full document and scheme
entities remain file-based. Do not introduce a large migration without a
proven workflow.

## Feature boundaries

Submission-time features may include initial proposal text, structured scheme
fields, authority/type/year, pre-submission site history, earlier nearby
outcomes, zoning and environmental constraints known at the time. FI, refusal
reasons and decision documents are evidence for display products or
explanations, never inputs to the pre-submission classifier. Rationales of
historical comparables are displayed as evidence only.

## Scenario flow

`scheme form -> baseline score -> validated mutation -> scenario score ->
delta explanation -> matching granted/refused precedents`

The mutation layer has explicit bounds and provenance; deltas are sensitivity
statements, never causal claims.
