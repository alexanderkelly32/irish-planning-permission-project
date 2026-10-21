# 03_refusal

Primary workspace for refusal-reason extraction and coverage tracking.

## current/

Canonical working outputs:
- `greater_than_10_units_with_refusal_reasons_master.csv`
- `refusal_reasons_cases_master.csv`
- `refusal_reasons_long_master.csv`
- `refusal_reason_tag_counts_master.csv`

Coverage snapshot export:
- `refusal_pipeline_coverage_by_la_20260302.csv`

## source_data/

Source-of-truth copies feeding the current views:
- `greater_than_10_units_with_refusal_reasons_master.csv`
- `refusal_reasons_cases_master.csv`
- `refusal_reasons_long_master.csv`
- `refusal_reason_tag_counts_master.csv`
- `ocr_text_index.csv`

## scripts/

Domain scripts for:
- refusal reason extraction
- OCR merge/fill workflows
- LLM batch preparation and merge

## Current Coverage Snapshot (checked 2026-03-02)

From canonical refusal files in `current/`:
- GE10 refusal rows: `1,520`
- Downloaded decision files on disk: `1,695` (`documents/downloaded`)
- OCR text files on disk: `1,165` (`documents/ocr`)
- Refusal cases with locally present decision files (filename-match check): `1,374`
- With matched document/case processing record: `1,070`
- Local docs not yet represented in case table: `322`
- Refusal cases with no local decision file found: `146`
- With OCR-based extraction source: `387`
- With LLM extraction pass: `356`
- With reasons populated in master (`reason_count > 0`): `738`

For per-local-authority values, use:
- `current/refusal_pipeline_coverage_by_la_20260302.csv`
