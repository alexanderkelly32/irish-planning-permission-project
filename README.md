# Planning Project

This repository is organized into domain workspaces:

- `00_base`
- `01_flood`
- `02_development`
- `03_refusal`
- `04_fi`
- `05_policy`
- `06_copilot`
- `07_solar`

Each domain has:
- `current/` canonical working outputs (when present)
- `source_data/` source-of-truth CSVs
- `scripts/` domain scripts

For folder provenance and movement history, see `provenance/README.md`.

## Codex / Session Context

Project-wide working rules are in `AGENTS.md`. Durable project state is maintained in `state/SESSION.md`, `state/TODO.md`, `state/DECISIONS.md` and `state/DEBUG_LOG.md`. The latest continuation checkpoint is in `state/HANDOFF-2026-09-01-project-context-and-model-v3.md`.

Optional local Codex skills are stored in `installed-skills/`. The global Codex skills directory is managed read-only in this environment, so these copies are kept with the project for handoff and inspection.

## Canonical Working Set (checked 2026-03-02)

- Base extracted wide: `02_development/source_data/ground_source_extracted_final_wide_fixed.csv` (`491,760` rows)
- Base GE10 extracted wide: `02_development/source_data/ground_source_extracted_final_wide_ge10_fixed.csv` (`9,876` rows)
- GE10 comprehensive: `02_development/source_data/greater_than_10_units_comprehensive_master.csv` (`10,050` rows)
- GE10 + refusal: `03_refusal/current/greater_than_10_units_with_refusal_reasons_master.csv` (`10,018` rows)
- Refusal case-level: `03_refusal/current/refusal_reasons_cases_master.csv` (`1,088` rows)
- Refusal reason-level long: `03_refusal/current/refusal_reasons_long_master.csv` (`3,405` rows)
- GE10 + refusal + FI requests: `04_fi/current/greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv` (`10,018` rows)
- Solar exploration workspace: `07_solar/source_data/likely_solar_farms.csv` (rough first-pass utility-scale solar extraction)

## Refusal Pipeline Snapshot (checked 2026-03-02)

Based on:
- `03_refusal/current/greater_than_10_units_with_refusal_reasons_master.csv`
- `03_refusal/current/refusal_reasons_cases_master.csv`

Totals across all local authorities:
- Refusal cases in GE10 universe: `1,520`
- Downloaded decision files on disk: `1,695` (`03_refusal/documents/downloaded`)
- OCR text files on disk: `1,165` (`03_refusal/documents/ocr`)
- Refusals with a locally present decision file (filename-match check): `1,374` (`90.4%`)
- Refusals with matched document/case processing record: `1,070` (`70.4%`)
- Refusals with local docs not yet represented in case table: `322`
- Refusals with no local decision file found: `146`
- Refusals with OCR-based extraction source: `387` (`25.5%`)
- Refusals with LLM extraction pass: `356` (`23.4%`)
- Refusals with populated reasons in master (`reason_count > 0`): `738` (`48.6%`)

Per-local-authority breakdown:
- `03_refusal/current/refusal_pipeline_coverage_by_la_20260302.csv`

## Merge Map (Recommended)

Primary key:
- Use `case_key` where present.
- Fallback key: `PlanningAuthority + ApplicationNumber` (trimmed, lowercased).

Recommended order:
1. Start with `02_development/source_data/ground_source_extracted_final_wide_ge10_fixed.csv`.
2. Left join refusal fields from `03_refusal/current/greater_than_10_units_with_refusal_reasons_master.csv` on `case_key`.
3. Left join FI fields from `04_fi/current/greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv` on `case_key`.
4. Left join flood fields from `01_flood/current/ge10_with_flooding.csv` on fallback key if needed.

## Notes

- `current/` is a mirrored canonical view; prefer updating `source_data/` where domain workflows expect source-of-truth edits.
- `old_original_attempt/` is historical and should not be used as an active modeling base.
- The Planning Precedent Copilot app now lives in `06_copilot/scripts/similar_developments_app.py`.
