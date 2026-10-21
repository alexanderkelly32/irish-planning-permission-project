# Label provenance — where every "pain" signal comes from

No label in this workspace is invented. Every component is a dated, observed
event from a named source field, following the brief's outcome definitions
(sections 5.2-5.6) and the composite rules in `configs/rules/pain_v2.yaml`.
This page is the ground-truth audit trail; it ships next to the labels.

## Component -> source field -> coverage

Coverage measured on the 1,095-scheme mature-granted pool (grants 2016-2022,
censor 2026-09-27).

| Component | Ground truth | Source / field | Coverage |
|---|---|---|---|
| `fi_requested` | FI request actually recorded | NPAD register `FIRequestDate` or `FIRecDate` | 72.9% |
| `appeal_submitted` | Applicant appeal lodged | NPAD register `AppealSubmittedDate` / `AppealRefNumber` | 9.2% |
| `planning_duration_days` | Time in planning | register `DecisionDate - ReceivedDate` | 99.9% |
| `activation_days` | Time to first valid commencement notice | BCMS `CN_Commencement_Date`, linked to scheme by exact `CN_Planning_Permission_Number` = register application number | 69.9% of schemes linked |
| `completion_days` | Time to completion certificate | BCMS `CCC_Date_Validated`, same link | 40.9% of notices have a CCC |
| `slow_exit_24m` | First sale >= 24 months after commencement | PPR `Date of Sale` linked via BCMS address/eircode -> PPR address | defined only for schemes with confirmed PPR links (95 of 198 sold schemes) |
| `below_market_25pct` | Scheme median price below same-county contemporaneous 25th percentile | PPR `Price` (VAT-exclusive for new builds), ±12 month window | 103 schemes benchmarked; 22 below |

## What is NOT a label

- **No cost-overrun label.** No verified budget/outturn data exists in public
  sources; the brief explicitly forbids inventing one (section 5.6).
- **Unlinked is unknown.** A scheme without a confirmed BCMS/PPR link is
  unknown on that component, never "did not commence" or "did not sell".
  Linkage coverage is reported separately from precision.
- **JR absence is not a negative.** No court source is treated as complete
  enough to label `jr_absent` (section 5.2).

## Composite rules (versioned, provisional per brief 13.3)

- `pain_v1` (friction + activation + completion) and `pain_v2` (+ slow exit,
  below-market pricing) are published in `configs/rules/`.
- High/moderate/low thresholds are the *only* judgment calls; they must pass
  inter-rater review on the audited cohort before product use (Gate 3).
- Every composite row retains its raw components so rules can change without
  re-extraction.

## Economic timing anchor

The user-facing outcome is time-and-money overruns. Time overruns are measured
as: planning duration (register), grant->commencement (BCMS), commencement->
completion (BCMS CCC), commencement->first sale and sell-through (PPR). Price
pressure is measured only as relative position vs contemporaneous same-county
transactions, never as an absolute overrun claim.

PPR reuse: PSRA terms permit free re-use with attribution; not for the
principal purpose of advertising a product (see `configs/sources.yaml`).
