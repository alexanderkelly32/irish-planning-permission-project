# Prediction accuracy — full suite, 2026-09-28 (final)

## 98% confidence intervals (2026-09-29)

Bootstrap percentile, 2,000 resamples; exact binomial for rates. Full JSON:
`silver/full_suite_98ci.json`.

| Prediction | Metric | Estimate | 98% CI | n |
|---|---|---|---|---|
| Refusal (frozen v4, 2025 holdout slice) | AUC | 0.793 | 0.778 – 0.807 | 15,221 |
| | AP | 0.413 | 0.383 – 0.444 | 15,221 |
| | Brier | 0.085 | 0.080 – 0.089 | 15,221 |
| FI | AUC | 0.688 | 0.606 – 0.761 | 363 |
| | AP | 0.840 | 0.774 – 0.895 | 363 |
| Appeal | AUC | 0.659 | 0.621 – 0.698 | 1,729 |
| | AP | 0.347 | 0.297 – 0.406 | 1,729 |
| Decision > 6 months | AUC | 0.755 | 0.688 – 0.815 | 433 |
| Decision > 12 months | AUC | 0.718 | 0.475 – 0.919 | 433 |
| Commencement timing (strata) | MAE | 512d | 450 – 577 | 494 |
| Commencement timing (shrunk rolling 24m) | MAE | 361d | — | 494 |
| Sale timing (strata) | MAE | 419d | 337 – 507 | 97 |
| Sale timing P(>2yr to first sale) | AUC | 0.672 | 0.553 – 0.781 | 97 |
| Refusal-reason top-3 transfer | accuracy | 55.4% | — | 56 |

Caveats: refusal file holds the 2025 slice only (n=15,221; the full 2024-25
holdout was n=35,713 with AUC 0.792, 95% CI 0.784–0.798). Decision >12m and
sale-timing CIs are wide (rare events / small n) — honest, not precise.
Condition-family prevalence CIs (n=338) are in the JSON per family.
TimesFM-2.5 county MAE improvement (19.2k vs 28.4k seasonal) is a pooled
point estimate; county-level paired bootstrap not yet computed.

## 2026-09-29 monitoring-tier finding (post-CCC sale timing)

- Post-commencement re-forecast (`sale_reforecast_postcommencement.json`):
  from commencement -> first sale: median 501d, 80% width 1,598d (n=280);
  from completion cert -> first sale: median 87d (n=173), declared-duration
  terciles 257/95/39d (long-declared schemes sell fastest, r=-0.20).
- **Phase-level (CCC event -> first sale): median 34d** (n=2,021), 60% within
  +/-180d, 74% within +/-365d - the tightest timing statement in the engine.
  completion_units is too sparse to split full-scheme vs phase CCCs.
- Accuracy-lever ranking for the pre-grant tiers: ECAD labels (purchase),
  PACK_14/15 verdicts (user), Land Registry folios (identity + verification),
  phase-level label rebuild (free). ML variants on current features are
  exhausted (quantile GBMs / hazard / constraints / text / market / history
  all tested).

## 2026-09-29 interval-width pass (can the wide intervals be shrunk?)

- **Strata variance decomposition** (`silver/timing_strata_variance.json`):
  commencement 80% widths range 381d (SDCC, data artefact) to 1,539d
  (Kilkenny); 2022+ era 814d vs pre-2020 1,432d; tightest realistic stratum
  2022+ 10-29 apartments 712d. Sale: AHB/BTR exclusion does NOT tighten
  (3,035d vs 3,053d); sale-from-commencement still 1,596d wide (n=243).
- **Applicant-identity features BLOCKED**: ApplicantForename/Surname are
  blank in every register layer we hold (bronze + ge10_with_flooding) -
  would need Land Registry/CRO data.
- **Rolling strata interval engine** (`run_strata_interval_engine.py`,
  `silver/strata_interval_engine.json`): time-safe 24m-window stratum
  quantiles (auth|band|type -> auth -> rolling global). Commencement:
  width 1,135d at **83.2% coverage** vs GBM smooth 1,155d at 74.6% - the
  GBM was under-covering; the strata engine is both better calibrated and
  slightly tighter. Sale: 1,485d at 83.5% vs 1,462d at 75.3%.
- Verdict: with current data the honest 80% intervals are ~1,135d
  (commencement) and ~1,485d (sale); 50% intervals are 627d / 842d. Narrowing
  further needs new labels (ECAD, PACK_14/15) or applicant-level data; the
  variance is real, not a modelling artefact.

## 2026-09-29 continuous timing pass (smooth CDFs, bin-free)

User asked for continuous classifiers instead of horizon bins. Delivered:

- `sale_timing_smooth_v1/v2.joblib` + `commencement_smooth_v1/v2.joblib`:
  19-quantile GBMs, monotone per-scheme CDF -> P(T <= t) at ANY horizon,
  bin-free quantile-coverage calibration (decision-timing pattern).
- **Commencement**: calibration excellent (mean abs coverage dev **1.8pp**,
  max 8.3pp). Discrimination remains weak: time-dependent AUC 0.56 @12m,
  0.52 @24m, ~0.45-0.51 beyond (v1: ~0.50-0.52). Constraint features
  (flood/NIAH/WWTP/traffic/Natura + prior activation rates) gave the 12m lift
  only. Censoring-aware discrete hazard (full pool, unlinked censored):
  no discrimination, under-calibrated levels, KM wins on Brier - falsified
  again, now with 958 events (was ~750 at first falsification).
- **Sale**: td-AUC ~0.5 across horizons (v2 with constraints: no change);
  coverage dev 10.6pp (small n=97). The earlier binned P(>2yr) logistic
  AUC 0.67 (n=97, wide CI) does not survive as continuous discrimination.
- Verdict: both timing CDFs are **calibrated but not discriminating** at
  scheme level. Timing is dominated by unobservables (developer behaviour,
  phasing, financing). Real uplift needs new labels (ECAD / PACK_14 / PACK_15)
  or new signal (applicant identity, company-level data).
- New feature file: `silver/timing_constraint_features.csv` (13 constraint +
  history features, full coverage on 1,113 pool schemes).

## 2026-09-29 label rebuild + timing retrain (post coverage push)

- Labels rebuilt from current links (`run_labels_v2.py`): exit labels now
  **561 sales-linked schemes** (was 383); pain pool **958 commencement-linked**
  (87.5% of pool). Old timing cards preserved as `*_v1.json`.
- **Sale timing**: strata MAE 419d (98% CI 337–507, n=97); horizon classifier
  P(>2yr to first sale) AUC **0.672** (0.553–0.781) vs ~0.51 before the label
  growth — first real horizon-discrimination signal. Test-set median 544d
  (was 703d; the new estate-name-linked schemes sell faster — composition
  shift is honest, not a modelling gain).
- **Commencement**: full-suite strata MAE 512d (450–577, n=494); deployable
  era-recalibrations unchanged at ~361–367d MAE (rolling/shrunk, n=494).
- **Reason transfer**: high-grade OCR re-extraction merged into llm_new
  (+48 cases, 18 genuinely tagged, 30 inferred marked unclear/low and excluded
  from tags). Transfer top-3 55.4% on n=56 vs baseline 25.0% — statistically
  unchanged from 55.6% (n=81); the new docs are mostly older cases, not
  2024-25 holdout refusals.
- `full_suite_98ci.json` refreshed with the new n.

## 2026-09-29 retrain pass (v2 artefacts, v1 untouched)

- **FI v2** (`fi_model_v2.joblib`, `fi_model_v2_card.json`): full GE10 register
  (not the ~1.3k pain pool) + 4Dublin pipeline FI labels (+4 positives); GBM
  d3 chosen on 2020 val (0.754). Holdout **AUC 0.691** (98% CI 0.668–0.716),
  n=1,731 — same discrimination as v1 but on ~5x the rows with a much tighter
  CI. By-year: 2021 0.721 / 2022 0.733 / 2023 0.683 / 2024 0.719 / 2025 0.578.
- **Appeal v2** (`appeal_model_v2.joblib`, `appeal_model_v2_card.json`): added
  time-safe authority/local prior appeal rates, density/site/covid features,
  GBM option; 4Dublin pipeline appeal labels (+13). Tuned on 2019-2020 val,
  holdout **AUC 0.657** (98% CI 0.626–0.687) vs v1 0.659 (0.621–0.698).
  **No gain — falsified.** v1 stays the appeal baseline.
- **Refusal-reason transfer**: full DeepSeek extraction over the 152 high-grade
  OCR'd refusal docs launched in background (llm_highgrade_full); pool will
  grow beyond the current 118 LLM cases, then the top-3 transfer is re-evaluated.
- Label provenance addition: `fi_appeal_labels_v2.csv` (register primary,
  4Dublin pipeline fills only where the register is silent; +4 FI / +13 appeal).



Measured out-of-sample on temporal holdouts. Coverage reflects the current
link sets (BCMS 61.9% mature; PPR 383/1,384 = 27.7% mature).

| # | Target | Accuracy today | Feeder data |
|---|---|---|---|
| a | **Time to decision** | **READY** — GBM quantiles MAE **63.9d** (const 86.7, strata 80.2; median 125d); pinball P50 32.0 vs 43.3. **Smooth CDF (new)**: bin-free coverage calibration mean |dev| **5.5pp**, max 9.8pp; P(>6m) calibration-in-large **+0.13pp**, Brier 0.184 vs 0.227; P(>12m) −0.74pp. AUC on horizon classifiers: 0.755 (>6m), 0.718 (>12m). Personalised via authority congestion (~80% importance), size, vintage | Register dates (3,186 GE10), congestion features |
| b | **Refusal likelihood** | **READY (frozen)** — AUC **0.792** (0.784-0.798) n=35,713; AP 0.409; Brier 0.090; calibrated ±0.8pp mean; GE10 AUC 0.782, 18.1% vs 19.0% | Full register + text + history/flood/plan |
| c | **Refusal reasons** | **Evidence transfer** — top-3 **55.6%** vs 24.7% baseline (top-1 16.0%), n=81; priors from 1,380 refused (78% tagged) | 03_refusal human-verified tags |
| d | **Grant conditions** | **CORPUS UNBLOCKED** — 338 granted planner reports labelled from the existing 5,512-PDF local corpus (was 17); family priors now corpus-based; conditional model next | Local PDFs (8 authorities) |
| e | **Time to sale** | **BASELINE** — no scheme signal (horizon AUC 0.51); constant MAE 423d (median 674d); coverage 383 schemes (27.7%) | PPR links (human + auto + spatial) |
| f | **Judicial review** | **ABSTAINS** — courts data not imported | — |
| g | **FI likelihood** | **READY** — AUC **0.688** (0.626-0.746), AP **0.840**, Brier 0.184; n=363; 2021 0.747 / 2022 0.570 (drift monitored) | Register FI dates (72%) + text |
| h | **Appeal likelihood** | **BASE-RATE** — AUC 0.51 at 298 events (21.5%) | Register appeal fields |
| i | **Time to commencement** | **BASELINE** — c-index 0.48; strata MAE 354d (median 379d); horizon AUC 0.58 | BCMS 61.9% linked |
| j | **Price vs peers** | **OBSERVED benchmark** for 383 schemes (28-30 below-market) + **TimesFM-2.5 market context (new)**: county price forecasts MAE €19.2k vs €28.4k seasonal; volume MAE 29.5 vs 34.8 | PPR prices + county series |

## New in this pass

- **Smooth conditional CDF for decision timing** (19-quantile GBMs, monotone):
  any-horizon probabilities, bin-free calibration, +0.13pp bias on >6m.
  Artifact `gold/decision_timing_smooth_v1.joblib`.
- **TimesFM-2.5 macro forecasts** (Apache-2.0, commercially usable):
  county PPR volumes (+20% vs seasonal), prices (+32%), BCMS commencements
  (+6% vs persistence). Wired into reports as market context.
  `silver/macro_forecasts.parquet` (83 series x 12 months).
- **Spatial PPR matching live**: geocoder batch 1 done (5,972 rows; 1,830
  located; 23 confirmed links, 9 new schemes, 334-row audit queue pending).

## Bottom line

Ship-ready with confidence: a (decision timing incl. smooth horizons), b
(refusal), g (FI). Evidence-grade: c (reasons), j (price benchmark + macro
forecasts). Honest baselines: e (sale timing), i (commencement timing).
Blocked on data imports: d (conditions), f (JR). Not modelable from public
submission data: h (appeal).
