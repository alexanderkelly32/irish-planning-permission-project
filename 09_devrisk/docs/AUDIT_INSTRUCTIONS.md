# Link audit instructions (human adjudication)

## Priority task: sales workbook (highest return)

`09_devrisk/data/silver/sales_workbook.csv` — 1,384 mature granted GE10
schemes, ranked by size, pre-filled with everything we know (register
address, description, BCMS address/project/eircode, suggested estate tokens).

For as many rows as you want:

1. **`estate_name_1/2/3`** — the development's name(s) as they appear in PPR
   addresses (e.g. "The Mill Race", "Browneshill Wood", "Ashfield"). The
   `suggested_estate_tokens` column is a starting point from BCMS records;
   verify on propertypriceregister.ie search. Spelling matters (PPR is
   typo-prone), so give variants in separate columns.
2. **`eircode`** — one eircode from the estate if known (any unit).
3. **`sellable_units`** — actual individually-sold unit count if you know it
   (blank = use proposed units).
4. **`is_build_to_sell`** — Y for ordinary build-to-sell; N for BTR/social/
   PRS/retained (those are excluded from sell-through).
5. **`notes`** — anything material (e.g. "phase 1 of 2", "marketed as X").

Partial filling is fine — every filled row is a scheme we can pull. Save the
file (same name, same folder, overwrite) and tell me; I run
`run_pull_sales.py`, rebuild exit labels and report the coverage jump.

## Secondary task: link adjudication queues

Two queue files in `09_devrisk/data/silver/audit/`:

1. **`audit_bcms_name_links.csv`** — 200 sampled rows (of 1,676 candidates)
   across 176 mature schemes still unmatched by planning-reference. Columns:
   scheme address/units/grant date, BCMS candidate address/project/ref/units/
   commencement, distance, uncommon-token overlap, chronology.
2. **`audit_ppr_expanded_links.csv`** — 450 rows across 150 schemes: expanded
   PPR sale candidates (estate-name/token match) with address similarity,
   overlap count and sale-after-grant flag.

## How to adjudicate

For each row, set `verdict` to one of:

- **confirmed** — the BCMS/PPR row is clearly the same scheme (estate name +
  town agree, distance small, dates sensible).
- **probable** — likely but not certain (keep out of training; sensitivity only).
- **rejected** — clearly a different scheme (different estate/town, wrong
  chronology, unit mismatch).

Use `verdict_note` for anything material (e.g., "PPR row is the marketing
name of this scheme"). Leave blank where unsure — blank rows are ignored.

Save the filled CSVs in the same folder with the same names (overwrite).

## What happens next

`python 09_devrisk\scripts\run_import_verdicts.py` converts `confirmed`
verdicts into overlay link files; the next `run_labels_extended.py` rebuild
folds them into the label set and coverage numbers update. No model retrains
on `probable` rows.

## Honest expectation

- The BCMS queue targets the last ~40% of mature schemes: some genuinely
  never lodged a commencement notice (real absence) — those can be marked
  rejected with note "no BCMS notice exists"; that is a finding, not a
  failure.
- The PPR queue is about expanding sales-link coverage beyond the strict
  eircode/estate rules; precision matters more than coverage (Gate 2).
