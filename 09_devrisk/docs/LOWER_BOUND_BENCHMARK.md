# Lower-bound prediction accuracy — initial timing models

Temporal-holdout benchmark of the simplest defensible models on the data
currently held (`scripts/run_lower_bound_benchmark.py` →
`data/silver/lower_bound_benchmark.json`). "Lower bound" = what the constant
model achieves; any real model must beat it. Strata = authority × anchor-year
× size band with authority/overall fallbacks. Measured 2026-09-28.

## Headline table (holdout, out-of-sample)

| Outcome | n (train/holdout) | Constant MAE (days) | Strata MAE | Current best | Horizon classification |
|---|---|---|---|---|---|
| Time to decision (submission→decision) | 2,753 / 433 | 86.7 | 80.2 | **GBM 63.9** (pinball P50 32.0 vs strata 40.1) | P(>6m) AUC 0.63-0.75; >12m 0.72 |
| Time to commencement (grant→CN, linked only) | 337 / 370 | 350.9 | 346.0 | strata (≈ constant) | P(>24m) AUC 0.58 (0.52-0.65) |
| Time to completion (CN→CCC, completed only) | 330 / 324 | 163.9 | 227.7 | **constant** (strata hurts) | P(>36m) AUC 0.66 (n tiny) |
| Time to first sale (grant→PPR, sold only) | 137 / 147 | 420.1 | 453.1 | **constant** (strata hurts) | P(>24m) AUC 0.51 (no signal) |

## What this means (honest reading)

1. **Decision timing is the one outcome with real predictability.** Lower
   bound MAE 86.7d; strata 80.2d; the GBM (congestion features + scheme type)
   63.9d against a test median of 125d. This is the only timing model worth
   putting in the product now.
2. **Commencement timing is barely predictable** (MAE ~346d vs median 379d;
   horizon AUC 0.58). Pre-2020 authority strata transfer poorly to the
   post-COVID era — regime dominates. We already knew the hazard model had no
   signal; this confirms even location conditioning adds ~nothing.
3. **Completion and first-sale timing are not predictable from
   authority/size/era.** Strata *worsens* MAE (227.7 vs 163.9 completion;
   453.1 vs 420.1 sale) — training-era patterns don't transfer, and sale n is
   small (137 train). The honest floor: constant ≈ cohort median/quantiles,
   with wide uncertainty.
4. **Lower-bound framing for the product:** any shipped timing estimate must
   beat these floors and be reported with the achieved MAE/coverage band.
   Only e (decision) clears that bar today; f's timing legs stay
   baseline-labelled.

## Caveats

- Commencement/completion benchmarks are conditional on confirmed links
  (BCMS 69.9% coverage); sale conditional on confirmed PPR links (26.3%).
  Unlinked schemes are unknown, not included.
- Splits are temporal (decision: received >= 2024; others: grant >= 2020).
- Pinball/MAE on censored outcomes are computed on event-observed subsets
  only; horizon classifiers use the full linked sets.
