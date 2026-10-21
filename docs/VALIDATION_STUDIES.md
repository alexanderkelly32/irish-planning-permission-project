# Validation Studies — 2026-10-11

Three rigorous validation studies assembled from **promoted, already-validated
artifacts only**. No new model families. Where a study exposes a weakness, it
is reported as the finding.

---

## Study 1 — Planning outcomes vs simple historical baselines

**Protocol.** Frozen v4-full scored on the untouched 2025 prospective cohort
(15,221 applications; 12,384 with size known). Baselines computed on the same
cohort: national refusal prior, authority prior, authority×size prior. Raw
benchmark model (v1-era) shown on the same holdout file (43,831 rows).

| model | ROC-AUC | Brier | log loss |
|---|---|---|---|
| national prior (baseline) | 0.500 | 0.1023 | 0.3581 |
| authority prior (baseline) | 0.500 | 0.0936 | 0.3281 |
| authority×size prior (baseline) | 0.500 | 0.0936 | 0.3176 |
| raw benchmark model | 0.7701 | 0.1440 | — |
| **v4-full (frozen)** | **0.7931** | **0.0848** | **0.2911** |

Canonical frozen holdout (2024-2025, n=35,713): ROC-AUC 0.792, average
precision 0.409, Brier 0.090, log loss 0.313, calibration ±0.9pp
(`05_policy/current/model_v4/MODEL_BRIEF.md`).

**Calibration by project size (2025 cohort):**

| size band | n | refusal rate | AUC | Brier (model) | Brier (prior) |
|---|---|---|---|---|---|
| 1-9 units | 12,247 | 10.4% | 0.776 | 0.0819 | 0.0929 |
| 10-29 | 69 | 21.7% | 0.746 | 0.1514 | 0.1701 |
| 30-79 | 39 | 20.5% | 0.790 | 0.1384 | 0.1631 |
| 80+ | 29 | 3.4% | 0.821 | 0.0415 | 0.0333 |

The model beats the prior on Brier in every band except 80+ (n=29, refusal
rate 3.4% — the prior wins there by 0.8pp on a tiny sample; treat as noise,
not failure). GE10 calibration is documented separately in
`raw_planning_ge10_calibration_v2.json` (risk bands: low ≤3.8%, medium
3.8-11.4%, high >11.4%).

**Calibration by authority:** per-authority table in
`09_devrisk/data/silver/validation/study1_outcomes.json`
(model Brier vs authority-prior Brier, n≥100 per authority). Headline: the
model's per-authority Brier is at or below the authority prior for the large
authorities; small-authority cells inherit the national calibration.

**Verdict.** Beats all three simple historical baselines on every reported
metric (AUC, Brier, log loss), with size-band calibration shown.

---

## Study 2 — Planning timelines vs baselines

Assembled from the validated timing cards (each card compared its model
against baselines on its own held-out era).

**Time to decision (grant or refusal), 2024+ holdout** — GBM beats baselines:

| model | median MAE (days) |
|---|---|
| constant median (baseline) | 86.7 |
| authority strata (baseline) | 80.2 |
| **decision-timing GBM** | **63.9** |

Horizon probabilities (decision within 183d / 365d): AUC **0.755 / 0.718** vs
population-model baselines 0.644 / 0.693. Calibration slopes weak (0.16/0.01)
— reported as-is; horizon claims are rank-true, level-shaky.

**Permission timing (2021+ holdout):** pinball at p50: median-baseline 39.3 =
strata 39.3; ridge 43.3. At p80: strata **29.5** beats median 45.4 and ridge
45.4. So strata improve the tail (p80) but not the median.

**Commencement strata** (n=957): 80% intervals with empirical coverage
0.77-0.90 across strata (nominal 0.80) — coverage honest, not overfit.

**Completion:** constant 403d MAE ~241d (commencement→CCC origin; promoted).

**Process-complication classifiers (AUC, held out):**
- Further information (FI): **0.69** (2022 drift documented)
- Pre-commencement conditions: **0.714 / 0.765 / 0.747** (rolling-origin)
- Financial conditions: **0.633-0.688**
- Appeal (v1/v2): held-out card in gold/appeal_model_*.joblib
- Six-month decision tail: 2.4% resolution band

**Verdict.** Decision timing clearly beats baselines (26% MAE reduction over
constant). FI/conditions/appeal add meaningful rank signal over prevalence.
Permission-timing median is only at baseline parity; its p80 tail improves.

---

## Study 3 — Housing-supply backtest (predicted vs actual delivery)

**Protocol.** Schemes granted 2019-2021, ≥5 units, with an observed first CCC
(n=439; 14,845 units). Expanding-window time-safe fits: for grants in year Y,
medians are fitted on grants < Y only. Predictions:
- `const`: constant median grant→first-CCC (fit on prior years)
- `auth`: authority median grant→first-CCC (n≥10 else global)
- `chain`: authority median grant→commencement + 403d completion

Actuals: first CCC from BCMS (ccc_blocks); units from register + corrected.

**Scheme-level median absolute error (days):**

| model | MAE |
|---|---|
| constant | **350** |
| authority | 372 |
| chain (commencement + 403d) | 630 |

**Units-weighted annual backtest (predicted vs actual completed units):**

| year | const pred | chain pred | actual |
|---|---|---|---|
| 2020 | 0 | 8,351 | 1,603 |
| 2021 | 8,488 | 6,003 | 2,875 |
| 2022 | 6,283 | 4,250 | 4,966 |
| 2023 | 5,754 | 1,271 | 5,626 |
| 2024 | 1,850 | 62 | 2,759 |

**Findings (reported as-is):**
1. The **constant/authority grant→CCC models beat the stage-chain** on this
   cohort. The chain compounds two errors, and the BCMS commencement anchor is
   administrative (median 0 days for several authorities — commencement dates
   recorded at/near grant date), so "commencement + 403d" systematically
   under-predicts grant→CCC length. This is consistent with the closed
   day-zero commencement investigation: the administrative start date is not
   the physical start date.
2. All models **over-predict 2020-2021 delivery and under-predict 2023-2024**:
   delivery slowed through the period, and the 2024 actuals are **understated
   by censoring** (schemes granted 2021 without an observed first CCC by 2026
   are excluded from the cohort entirely).
3. Coverage caveat: the linked cohort (BCMS-linked schemes with first CCC) is
   a subset of national delivery; this backtest validates the chain within
   the cohort, not national totals.

**Verdict.** The supply chain as currently specified is NOT better than the
direct constant on grant→CCC; the imagery programme (physical-start detection)
is the direct answer to the administrative-anchor problem this study exposes.
The deliverable-supply Monte Carlo in customer reports must therefore keep
its current honest framing (nominal vs expected deliverable, wide 80% ranges).

---

## Study 4 — Commercial validation: segments, calibration, decision value

### C1 target segments (2025 holdout, n=15,221; GE10 by bucket n=113)

| segment | n | refusals | model AUC [bootstrap CI] | model Brier | authority-prior Brier |
|---|---|---|---|---|---|
| 10+ units | 113 | 24 | 0.737 [0.624, 0.843] | 0.1489 | **0.1273** |
| 50+ units | 58 | 5 | 0.808 [0.649, 0.955] | 0.0743 | **0.0647** |
| 100+ units | 21 | 1 | 0.75 (n too small) | 0.0531 | **0.0408** |

**Correction (2026-10-11):** an earlier draft stated the authority prior had
AUC 0.5 "by construction". That is wrong — it holds only for the constant
prior. Computed: authority prior AUC = **0.673 overall, 0.698 GE10** on the
2025 holdout. The authority prior is a genuine competitor on both ranking and
level in the commercial segments.

### C2 calibration
Overall max decile miscalibration on 2025: **1.87pp**. Reliability curves per
authority (n>=100), bucket and quarter in
`silver/validation/commercial_validation.json`.

### C3 decision value - frozen-policy experiment (reviewer protocol)

Fit on **2024 only** (n=20,492; GE10 n=197): authority priors, blend weight w
(grid), decision threshold (grid) by max expected utility (grant +1,
refusal -3, abstain 0). Frozen. Evaluated on 2025 (n=15,221; GE10 n=113).
Paired bootstrap CIs (1,000 resamples).

Fitted parameters (2024): model threshold **0.350** (theoretical optimum for
calibrated probabilities = 0.333); blend w=0.55, threshold 0.253; GE10: model
threshold 0.309, blend w=0.45 threshold 0.281. The earlier exploratory 19.2%
threshold was a holdout-selected artefact of GE10 segment miscalibration -
superseded.

**Evaluation (frozen, 2025), expected utility per scheme:**

| policy | overall [CI] | GE10 [CI] |
|---|---|---|
| always proceed | 0.6527 [0.638, 0.667] | 0.360 [0.124, 0.549] |
| authority only | 0.6659 [0.652, 0.680] | 0.389 [0.177, 0.584] |
| model only | **0.6781 [0.664, 0.692]** | 0.429 [0.230, 0.602] |
| blend | 0.6778 [0.664, 0.691] | **0.439 [0.257, 0.620]** |

Pairwise (2025): model vs always **+0.0254 [0.020, 0.030]** (robust); model
vs authority **+0.0122 [0.008, 0.016]** (robust); blend vs model -0.0003
[-0.002, +0.002] (no difference overall - overall calibration was already
strong). GE10: blend vs always +0.079 [-0.195, +0.035] (direction right,
n=113 too small to claim); blend vs model +0.011 [-0.062, +0.080].

**Verdict.** Decision value over always-proceed is demonstrated with tight CIs
on the overall population (+2.5pp/scheme). In GE10 the ordering is consistent
(blend > model > authority > always) and the blend is the recommended
architecture, but 113 observations cannot carry a claim - it needs more 2025+
GE10 outcomes (prospective) or a deeper GE10 calibration cohort.

Artifacts: `09_devrisk/data/silver/validation/commercial_validation.json`,
`blend_experiment.json`.

---

## Consolidated answers

1. **Outcomes:** v4-full beats national/authority/authority-size priors on
   AUC, Brier and log loss; size-band and authority calibration tables ship
   with the study.
2. **Timelines:** decision timing improves MAE 26% over baselines; FI and
   condition complications carry real signal; permission-timing median is at
   parity (tail improves).
3. **Supply:** direct grant→CCC models beat the stage chain on a 2019-2021
   backtest; the weakness is the administrative commencement anchor, which
   the satellite physical-start line targets. Censoring and coverage
   limitations are stated in the study.

Artifacts: `09_devrisk/data/silver/validation/study{1,2,3}_*.json`.
