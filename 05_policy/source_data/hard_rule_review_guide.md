# Hard Rule Review Guide

Start with `hard_rule_review_queue_apartment.csv` (05_policy/current/).

That is the smallest high-value review set and should be completed before parking, open space, or height.

## What To Check

For each row, verify:

1. The numeric threshold is actually present in the source policy.
2. The rule is a real minimum or maximum, not guidance or commentary.
3. The rule applies to the exact subject type shown:
   - `studio`
   - `1-bed`
   - `2-bed`
   - `3-bed`
   - `4-bed`
4. The unit is correct:
   - `sqm`
   - `sqm_per_unit`
   - `m`
5. The rule applies to the plan years shown.
6. The source page and excerpt are close enough to the real rule text.

## What To Edit

Open `verified_hard_policy_rules.csv` (05_policy/source_data/) and copy in the rows you trust from the review queue.

For each reviewed row, set:

- `review_status`
  - `approved` if the rule is correct and usable
  - `rejected` if the extraction is wrong
  - `needs_review` if the policy text is still unclear
- `reviewer`
- `reviewed_at`
- `review_notes`
- `verification_method`
  - usually `human_pdf_check`
- `verbatim_quote`
  - short exact quote from the policy page

## Recommended Review Order

1. Dublin City apartment minimum floor areas
2. South Dublin apartment minimum floor areas
3. DLR apartment minimum floor areas
4. Fingal apartment minimum floor areas
5. Communal amenity minimums
6. Private amenity minimum depth

## Rows That Need Extra Care

These are more likely to be incomplete or noisy and should not be approved without checking the PDF carefully:

- rows where `source_section_title` is obviously unrelated, such as shopfront design
- rows where the excerpt does not visibly contain the rule
- DLR rows with only part of the bedroom mix captured
- any row extracted from OCR-heavy pages or split tables

## Practical Standard

Only approve a row if you can point to one exact page and one exact quote that supports it.

If you cannot do that, leave it out of the verified file.
