# 09_devrisk — Irish Residential Development Risk Engine

Extension of the frozen planning-outcome model (v4-full) into a time-safe,
auditable **development execution-risk engine**: planning friction, activation
(commencement), delivery/completion and build-to-sell exit timing, plus
cost-exposure indicators.

Governing brief: `docs/Irish_Residential_Development_Risk_Engine_Technical_Brief.md`
(revision 2, 2026-09-27).

## Status

Sprint 0/1: scaffold, source manifest, structured ingestion (NPAD-register,
BCMS, PPR), cohort design, entity-resolution and label tooling. No new
probability model is promoted yet; the frozen v4-full planning model is
untouched and integrated only through its public scoring interface
(`05_policy/scripts/model_feature_builder.score_proposal`).

## Layout

- `configs/sources.yaml` — official source manifest (URLs, licences, cadence, access notes).
- `configs/rules/` — versioned label rules (`pain_v2.yaml`, `friction_v1.yaml`),
  pre-committed stop/go gates (`pilot_gates.yaml`) and drift thresholds (`drift_monitoring.yaml`).
- `configs/cohorts/pilot_100.yaml` — stratified 100-scheme pilot cohort definition.
- `devrisk/` — package: provenance, ingestion (npad/bcms/ppr), entity resolution,
  labels, survival/hazard models, extraction contracts, reporting
  (report_spec, v4 driver explanation, condition families, prototype report).
- `data/` — raw → bronze → silver → gold layers plus provenance manifests
  (gitignored; fixtures for tests are committed under `tests/fixtures`).
- `scripts/` — thin runnable drivers over the package.
- `tests/` — unittest suite: schema, chronology, leakage, matching, labels,
  hazard, extraction, report spec (94 tests).
- `docs/` — architecture, feasibility, label provenance; output spec is
  `docs/Initial_Development_Risk_Report_Product_Brief.md`.

## Commands (from project root, PowerShell)

```powershell
$env:PYTHONPATH = (Resolve-Path .vendor).Path
python 09_devrisk\scripts\run_ingest.py bcms     # download + raw hash + bronze
python 09_devrisk\scripts\run_ingest.py npad     # register parquet -> bronze
python 09_devrisk\scripts\run_ingest.py ppr      # PPR bulk ZIP -> bronze + silver
python 09_devrisk\scripts\run_cohort.py          # mature 10+ unit granted cohort + strata
python 09_devrisk\scripts\run_exit_labels.py     # PPR linkage + exit labels + price benchmarks
python 09_devrisk\scripts\run_pain_labels.py     # pain_v2 labels for the full pool (structured data)
python 09_devrisk\scripts\run_pain_model.py      # submission-time pain model (temporal holdout)
python 09_devrisk\scripts\run_pain_components.py # per-component models + ablations
python 09_devrisk\scripts\run_fi_model.py        # calibrated FI-request model card
python 09_devrisk\scripts\run_audit_queue.py     # BCMS + PPR link adjudication queues (human review)
python 09_devrisk\scripts\run_survival_baseline.py
python 09_devrisk\scripts\run_cli.py --help      # generic CLI
python -m unittest discover -s 09_devrisk\tests -t 09_devrisk\tests -v
```

## Invariants

1. The frozen v4-full planning model and its artifacts are never modified.
2. Every probability exposed downstream must be calibrated; until a model is
   validated, outputs are research baselines with explicit uncertainty.
3. No future information may leak into a historical prediction: every feature
   carries `available_at`; labels carry observation windows and censoring.
4. Related applications are grouped by scheme/site before any split.
5. Every derived field and label carries provenance (source file, row, rule version).
6. Ambiguous scheme links are never silently treated as truth.

See `docs/ARCHITECTURE.md` for details.
