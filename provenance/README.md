# Planning Project Provenance

Last updated: 2026-03-02

This file describes the current workspace layout and which files are canonical today.

## 1) Current Workspace Layout

Top-level active domains:
- `00_base`
- `01_flood`
- `02_development`
- `03_refusal`
- `04_fi`

Support folders:
- `provenance/` documentation
- `notes/` logs and operator notes
- `old_original_attempt/` legacy archive
- `keys/` local key material

## 2) Canonical Files (Current)

Base and development:
- `02_development/source_data/ground_source_extracted_final_wide_fixed.csv`
- `02_development/source_data/ground_source_extracted_final_wide_ge10_fixed.csv`
- `02_development/source_data/ground_source_extracted_final_wide_comprehensive_master.csv`
- `02_development/source_data/greater_than_10_units_comprehensive_master.csv`

Refusal pipeline:
- `03_refusal/current/greater_than_10_units_with_refusal_reasons_master.csv`
- `03_refusal/current/refusal_reasons_cases_master.csv`
- `03_refusal/current/refusal_reasons_long_master.csv`
- `03_refusal/current/refusal_reason_tag_counts_master.csv`

FI enrichment:
- `04_fi/current/greater_than_10_units_with_refusal_reasons_plus_ge10_fi_enriched.csv`
- `04_fi/current/greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv`

## 3) Current Row Counts (checked 2026-03-02)

- `02_development/source_data/ground_source_extracted_final_wide_fixed.csv`: `491,760`
- `02_development/source_data/ground_source_extracted_final_wide_ge10_fixed.csv`: `9,876`
- `02_development/source_data/greater_than_10_units_comprehensive_master.csv`: `10,050`
- `03_refusal/current/greater_than_10_units_with_refusal_reasons_master.csv`: `10,018`
- `03_refusal/current/refusal_reasons_cases_master.csv`: `1,088`
- `03_refusal/current/refusal_reasons_long_master.csv`: `3,405`
- `04_fi/current/greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv`: `10,018`

## 4) Refusal Coverage Snapshot (checked 2026-03-02)

Computed from:
- `03_refusal/current/greater_than_10_units_with_refusal_reasons_master.csv`
- `03_refusal/current/refusal_reasons_cases_master.csv`

Totals:
- GE10 refusal cases: `1,520`
- Downloaded decision files on disk: `1,695` (`03_refusal/documents/downloaded`)
- OCR text files on disk: `1,165` (`03_refusal/documents/ocr`)
- Refusal cases with locally present decision files (filename-match check): `1,374` (`90.4%`)
- With matched document/case record: `1,070` (`70.4%`)
- Local docs not yet represented in case table: `322`
- Refusal cases with no local decision file found: `146`
- With OCR extraction source: `387` (`25.5%`)
- With LLM extraction pass: `356` (`23.4%`)
- With reasons populated in master (`reason_count > 0`): `738` (`48.6%`)

Per-LA detail file:
- `03_refusal/current/refusal_pipeline_coverage_by_la_20260302.csv`

## 5) Practical Guidance

- Use `03_refusal/current/*master*.csv` for refusal analysis.
- Use `02_development/source_data/*` as base inputs for rebuilds/refreshes.
- Use `04_fi/current/*fi*enriched*.csv` when FI features are required.
- Treat `old_original_attempt/` as historical only.
