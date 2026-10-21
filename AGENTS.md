# Planning Optimiser

## Purpose

This project is an Ireland-first planning-intelligence product for developers and planning professionals. The core workflow is:

`SITE -> SCHEME -> PREDICT -> DIAGNOSE -> PRECEDENTS/EVIDENCE -> SCENARIOS`

The current product candidate is a submission-time residential planning-risk model plus a Streamlit precedent copilot. The v4-full product surface is a "Pre-Submission Review": score, evidence, PDF report, portfolio and monitoring (`06_copilot/scripts/model_v4_playground.py`).

## Repository Map

- `00_base/`: base extraction and operational source material.
- `01_flood/`: flood-data workspace and derived flood features.
- `02_development/`: canonical development/application datasets.
- `03_refusal/`: refusal documents, OCR and refusal-reason extraction. Staged gap driver: `03_refusal/scripts/run_refusal_coverage.py` (gap/download/ocr/prepare/merge; LLM via `02_development/scripts/run_deepseek_extraction.py`). New extractions land in `refusal_reasons_cases_llm_new.csv` (merged as a display source AFTER the retagged master - the canonical master is never modified).
- `04_fi/`: Further Information extraction. FI is post-submission and must not enter the submission-time model.
- `05_policy/`: policy documents, zoning layers, hard rules, model scripts and model artifacts.
- `06_copilot/`: Streamlit app and reusable prediction/retrieval logic.
- `07_context/`: national context layers. Constraint layers (NIAH buildings, Natura 2000 SAC/SPA, EPA wastewater points, TII traffic counters) built by `07_context/scripts/build_constraint_reference.py` from downloads in `07_context/scripts/download_constraint_layers.py`; query tables live in `07_context/current/constraint_*.parquet`.
- `10_energy/`: NEW energy-infrastructure intelligence line (the active pivot). Outcome predictor + timeline watcher for power projects (solar, wind, BESS, grid, biogas, hydro, CHP). Data centres are extracted as demand-side context only, never forecast targets. Cohort + baselines: `scripts/extract_energy_cohort.py`, `scripts/build_energy_baselines.py` (outputs in `source_data/`). The residential product line is FROZEN from this workspace (read-only). Known largest coverage gap: ABP strategic cases (pleanala.ie).
- `09_devrisk/`: development risk engine (time-safe "pain to develop" extension of the frozen model). Governing brief: `docs/Irish_Residential_Development_Risk_Engine_Technical_Brief.md` (+ Amendment A: single calibrated pain model is the primary aim); output spec: `docs/Initial_Development_Risk_Report_Product_Brief.md` (canonical report modules 6.1-6.15, four-class statement language, analyst QA). Configs (`configs/sources.yaml`, `configs/rules/pain_v2.yaml`, `pilot_gates.yaml`, `drift_monitoring.yaml`); package (`devrisk/`: provenance, ingestion npad/bcms/ppr, entity resolution, labels, survival/hazard, extraction contracts, reporting incl. v4 driver explanation); data layers (`data/` raw→bronze→silver→gold, gitignored) with provenance manifests; runner scripts in `09_devrisk/scripts/run_*.py`; unittest suite (`python -m unittest discover -s 09_devrisk\tests -t 09_devrisk\tests`). Ground-truth provenance per label: `09_devrisk/docs/LABEL_PROVENANCE.md`. Frozen v4-full is read-only via `devrisk/models/planning_adapter.py`; unlinked BCMS/PPR events are UNKNOWN, never "slow". Research baselines only — nothing calibrated except the FI model card (`data/gold/fi_model_v1.joblib`, holdout AUC 0.69, 2022 drift documented) and the timing strata card.
- `state/`: durable current project state for future sessions.
- `.codex/handoffs/`: session-specific continuation notes.
- `installed-skills/`: project-local copies of optional Codex skills.

## Canonical Model

Model **v4-full** is the promoted candidate (frozen 22 Sep 2026); Model v3 remains the frozen baseline:

- Artifact: `05_policy/current/model_v4/national_residential_v4_full.joblib` (+ `manifest.json`)
- Product app: `06_copilot/scripts/model_v4_playground.py` ("Pre-Submission Review")
- Comparable reference (scoring path): `model_v4/comparable_reference.joblib` - frozen, do not modify.
- Comparable display metadata (names, dates, rationales): `model_v4/comparable_metadata.joblib` - display-only, built by `05_policy/scripts/build_comparable_metadata.py`, must stay row-aligned with the frozen reference (the builder verifies alignment and fails loudly).
- Scope: national residential applications, submission-time features, pre-2024 training reference, 2024-2025 out-of-sample holdout (n=35,713).
- Inputs: authority, description text, units, site area, floor area, ITM coordinates, submission year. Everything else is derived at query time.
- Exclusions: FI, refusal reasons, decision outcomes/dates, appeals, and other post-submission information. (Refusal rationales of historical comparables may be *displayed* as evidence; they are never model inputs.)
- Holdout: ROC-AUC `0.792`, average precision `0.409`; calibrated Brier `0.090`, log loss `0.313`.
- GE10 (10+ units) focus: n=464, ROC-AUC `0.782`; riskiest decile refused at 63.8%, safest at 0%.
- Risk bands: low <= 3.8%, medium 3.8-11.4%, high > 11.4%.

Model v1 remains the simpler frozen baseline. v2 is the historical-context candidate. Do not silently replace model artifacts or benchmark definitions.

## Product Surface (v4-full)

`model_v4_playground.py` is a product, not a calculator:

- **Evidence services** (`06_copilot/scripts/v4_evidence_service.py`): matched precedents (wording + unit count + density + council + recency, 5-year window, undecided excluded - display engine only; the frozen scoring path is unchanged), council-vs-location check, development-plan objective crosswalk (addressed/open/flag, numeric-junk codes dropped), flood/small-area/zoning site evidence, nearby decision map points, boundary-draw ingestion (`boundary_evidence`: drawn polygon -> area/density/constraints-inside counts), calibration band CIs, GE10 percentile/decile framing, fallback naming, specialised-scheme prior disclosure, and evidence snapshots for monitoring.
- **The brief** (`v4_brief_service.py`): risk register (issue/evidence/severity/confidence/mitigation/owner/status - severities only from data the project holds; missing data becomes "unverified" rows with confirm-actions), next actions by owner, evidence-quality stamps, transit-stop proximity, and the model changelog (`05_policy/current/model_v4/CHANGELOG.json`, internal - not shown to users).
- **Planner override & audit trail**: `overrides` table in the portfolio store - the model value is never overwritten; overrides carry rationale, planner name and timestamp and appear in the brief and PDF.
- **Wording tools** (`v4_wording_service.py`): measured rewrites (granted-scheme phrasing, accurate-type additions, wording swaps) each rescored with deltas. No LLM; adopt-only-if-accurate warnings. Phrase-highlighting was removed from the product (too noisy); phrase effects remain internal.
- **Portfolio & monitoring** (`v4_portfolio_store.py`, SQLite at `06_copilot/current/portfolio.sqlite`, gitignored): saved projects, append-only scoring events, scenarios, evidence snapshots, overrides, and rescore-and-diff alerts.
- **PDF report** (`v4_report.py`, fpdf2 from .vendor): branded pre-submission review with scheme, drivers, confidence/fallbacks, matched precedents with rationale, policy crosswalk, site evidence, risk register, evidence quality, planner note and a single footer disclaimer line. Model-methodology, changelog and wording sections are intentionally absent (proprietary).
- Rules that bind: every scored event records model version, inputs and timestamp; deltas are sensitivity statements, never causal claims; "few close precedents" and confidence intervals are shown prominently as features, not apologised for; the register never invents a severity the model cannot support.

## Commands

Run from the project root in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .vendor).Path
python 10_energy\scripts\extract_energy_cohort.py   # rebuild energy cohort (mentions/cohort/utility-scale)
python 10_energy\scripts\build_energy_baselines.py  # reference-class refusal rates + decision timing
python 05_policy\scripts\build_comparable_metadata.py   # rebuild display metadata (verify alignment with frozen reference)
python 05_policy\scripts\build_national_residential_model_v3.py
streamlit run 06_copilot\scripts\model_v4_playground.py
python -m unittest 06_copilot.tests.test_v4_evidence_service 06_copilot.tests.test_v4_wording_service 06_copilot.tests.test_v4_portfolio_store 06_copilot.tests.test_v4_report 06_copilot.tests.test_v4_brief_service
python -m unittest discover -s 09_devrisk\tests -t 09_devrisk\tests   # devrisk engine tests
python 09_devrisk\scripts\run_report.py "Carlow County Council__19263"   # prototype research report
```

One-off evaluations (reproducible, slow - each loads the 219k-row register):

```powershell
python 05_policy\scripts\run_activate_backtest.py          # Activate portfolio time-safe backtest (11/25 matched)
python 05_policy\scripts\build_reason_prediction_eval.py   # theme-transfer accuracy (top-3 ~56%)
python 05_policy\scripts\build_v5_theme_classifier.py      # v5 theme classifier (NOT promoted)
python 05_policy\scripts\build_ge10_recalibration.py       # GE10 recalibrator (NOT needed)
python 03_refusal\scripts\run_refusal_coverage.py gap|download|ocr|prepare|merge   # refusal-reason extraction driver
python 02_development\scripts\run_deepseek_extraction.py --out-dir 03_refusal\current\llm_new_ge10 --model deepseek-v4-pro
```

Check syntax:

```powershell
python -m py_compile 05_policy\scripts\*.py 06_copilot\scripts\*.py
```

Full current-state handoff for a fresh agent: `state/HANDOFF_2026-09-24.md`
(all stats, artifacts, decisions, open items). Product brief with accuracy
tables: `05_policy/current/model_v4/MODEL_BRIEF.md`. Roadmap:
`state/ROADMAP.md`. Competitor intel: `docs/PLANNING_SITE_INTEL_2026-09-24.md`
+ `docs/planning_sites/distilled/`.

## Engineering Rules

- Treat prediction time as immediately before submission unless a model explicitly says otherwise.
- Keep raw data, derived features and model artifacts separate and reproducible.
- Use `case_key` first; use trimmed lowercased authority plus application number only as fallback.
- Historical and comparable features must be calculated only from earlier applications.
- Keep council-specific calibration separate from the shared national classifier unless validation justifies otherwise.
- Every prediction/scenario should record model version, input values and timestamp; do not overwrite prior results.
- Explain model sensitivity as “holding other inputs constant”, never as a proven causal effect.
- Recommendations need comparable applications, policy or revision-pair evidence before being presented as planning advice.
- Do not add FI, refusal reasons or eventual decision metadata to the submission model.
- Do not commit secrets, API keys, local credentials or generated caches unless they are already part of the project convention.
- Prefer existing functions and schemas over new parallel abstractions. Use `apply_patch` for manual edits.

## Validation Standard

Report more than AUC: holdout size/date range, class balance, ROC-AUC with bootstrap CI, average precision, Brier, log loss, calibration/reliability, thresholds, risk bands, council/type breakdowns and temporal robustness. A single aggregate AUC is not sufficient for a product claim.

## Current Product Direction

The product surface has shifted from calculator to review: the evidence tabs, PDF report, portfolio and wording tools above are shipped and working. The next high-value capability remains a scenario engine: duplicate a structured proposal, mutate a small number of supported fields, rescore each variant, and show the modelled change alongside comparable-case evidence. This must be framed as sensitivity analysis until refused-to-revised-to-granted revision data supports stronger claims. A future alerting story needs a live register feed; the monitor currently diffs against the frozen history snapshot (through 2025-12-23) and says so honestly.
