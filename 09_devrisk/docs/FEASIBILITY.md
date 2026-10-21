# Data Quality & Feasibility Report — first hand-off (2026-09-27, rev 2)

Scope: brief §26 items 4–9 (source manifest, structured ingestion, cohort
distribution, ten-scheme vertical slice, linkage/coverage measurement) plus
the pain-label build, economic (PPR) leg and first submission-time pain-model
baselines (Amendment A). No model is promoted; outputs are research
baselines.

## 0. Primary aim (Amendment A, 2026-09-27)

The primary aim is a single predictive model: "how painful will this
development be to actually develop?" — a calibrated submission-time
probability of severe observable development pain, anchored on time outcomes
(planning duration, grant→commencement, commencement→completion, commencement→
first sale / sell-through) and price pressure (vs contemporaneous
same-county transactions). Structured labels precede document extraction; the
composite rule is published (`configs/rules/pain_v2.yaml`), components stay
visible, and every label's ground-truth field is documented in
`docs/LABEL_PROVENANCE.md`.

## 1. Sources ingested

| Source | Snapshot | Rows | Coverage notes |
|---|---|---|---|
| NPAD-derived register (held by repo) | 1991-03-05 .. 2026-01-19 | 491,760 | 377 duplicate case keys; SHD/ABP-era named schemes known to be under-covered |
| BCMS/NBCO commencements (direct CSV) | downloaded 2026-09-27 | 249,127 | 234,758 rows with geo (94.2%); 238,186 with a planning reference (95.6%); 101,790 with a completion record (40.9%) |
| PPR (PSRA bulk ZIP) | 2010-01-01 .. 2026-09-18 | 807,724 | all rows dated/priced; 41,150 not-full-market-price rows; reuse permitted with PSRA attribution |

Raw BCMS file: 279.2 MB, sha256 `e30b23b7…`; PPR zip 19.1 MB, sha256
`e67f1b4c…` (manifests record full hashes).

## 2. Pilot candidate pool (mature granted residential, 10+ units)

- **1,095 schemes**, 25 authorities, grant years 2016–2022, ≥36 months follow-up.
- Size bands: 10–29: 518 · 30–99: 507 · 100–249: 46 · 250+: 24.
- COVID materially exposed (≥30 restricted days in 24-month at-risk window): 434 (39.6%).
- The 250+ band is thin (24 schemes): the 100-scheme proposal draws all 24 and tops up other bands. The brief's suggested 250+ share is not achievable from the register alone; this is a documented coverage finding, not an adjustment to hide it.
- Proposal + audit workbook: `data/silver/pilot_candidates_100.parquet`,
  `data/silver/pilot_100_audit.csv`.

## 3. BCMS linkage (transparent candidates on the 100-scheme proposal)

- 95 of 99 pilot schemes produced ≥1 candidate within 500 m / unit tolerance.
- Candidate bands: **160 confirmed, 31 probable, 181 ambiguous, 84 rejected**.
- Strongest confirmed links are exact planning-reference matches: BCMS
  `CN_Planning_Permission_Number` embeds the register application number
  (e.g. register `20200166` ↔ BCMS `…20200166`, 10.8 m, 0 unit diff).
- **Linkage precision has NOT yet been manually audited** (Gate 2). The
  vertical-slice workbook is the next review step; confirmed links are used
  only for research labels, never for training, until audited precision ≥95%.

## 4. Activation labels (pilot, research baseline)

- 99 eligible schemes, 46 with confirmed-link commencements.
- Overall KM: P(admin commencement by 12/24/36m) ≈ 16% / 25% / 33%.
- **Caveat:** schemes without a confirmed BCMS link are right-censored, so
  these understate true activation where linkage coverage < 100%. Coverage and
  precision are reported separately per the brief; these numbers are NOT
  product probabilities.
- COVID-exposed strata show lower unadjusted 24-month activation (18% vs 31%),
  consistent with restrictions; tiny n, unadjusted, no causal claim.

## 5. Ten-scheme vertical slice

`data/silver/vertical_slice_10_review.csv`: 23 candidate rows across 10
schemes with scheme identity, link evidence (distance, unit diff, band,
reasons), commencement date and label. A human reviewer column is included.
Observed examples look credible (exact reference matches at 4–11 m with 0–4
unit diffs); probable links include one long-delay commencement that needs
review.

## 6. Pain labels and model readout (Amendment A)

Ground truth per component is field-level and documented in
`docs/LABEL_PROVENANCE.md` (nothing invented; the only judgment is the
provisional composite rule, brief 13.3).

Pain_v2 components from structured data (n = 1,095):

- FI requested: 798 (72.9%) · appeals: 101 (9.2%) · slow activation (≥24m): 168
  · slow completion (≥36m): 25 · no completion after 36m matured: 24.
- Economic leg (PPR): 198 schemes with confirmed sales links (18.1%);
  slow exit defined for 95; below-market pricing for 22.
- Composite: high 282 (25.8%), moderate 574, low 239.
- BCMS confirmed-link coverage: 765/1,095 schemes (69.9%) via exact
  planning-reference matches.

Temporal holdout (train received <2020, n=647; test received ≥2021, n=276):

| Target | AUC (95% CI) | AP |
|---|---|---|
| FI requested | **0.688 (0.618–0.760)** | **0.803** |
| Composite high-pain (v2) | 0.577 (0.484–0.660) | — |
| Slow activation ≥24m | 0.603 (0.502–0.695) | 0.208 |
| Appeal | 0.551 (0.413–0.681) | 0.056 |
| Slow exit ≥24m | skipped: too few labelled in train | — |

Calibrated FI model card (`silver/fi_model_card.json`): C tuned + isotonic on
2020; holdout AUC 0.687, AP 0.803, Brier 0.194 (beats base-rate Brier 0.212);
2021 alone AUC 0.747 / AP 0.880; **2022 alone AUC 0.570** — clear regime
drift, exactly the brief's §16.7 warning. Productising requires rolling-origin
retraining and drift monitoring.

Ablation (FI): structured-only AUC 0.474 → +description text 0.691 →
+time-safe authority/5km history 0.688. **The description text is essentially
the whole submission-time signal; history features add nothing on this
cohort.**

Honest readout:

1. The planning-friction leg (FI) is genuinely predictable at submission and
   is the strongest pain component. It is the first calibratable piece.
2. Timing/economic legs are regime-driven (COVID, funding cycles) and only
   weakly scheme-specific at submission; they need survival modelling with
   explicit regime covariates and more linkage coverage before they can carry
   weight in a composite.
3. Test prevalence drifted vs train (18.5% vs 25.7% for high-pain) — per-cohort
   calibration is required, per the brief's regime-change rules.
4. Whether the frozen v4 refusal probability adds signal to pain (brief
   §25 Q9) requires time-safe out-of-fold scores — a rolling-origin job, not
   the query-time score (which embeds a frozen 2024 history snapshot).

## 7. What is NOT claimed

- No cost-overrun probability (no verified budget/outturn data).
- No calibrated friction/JR probabilities shipped beyond the research FI
  model card; JR needs a verified positive-event table.
- PPR sales labels exist only where links are confirmed; unlinked schemes are
  UNKNOWN on exit, never "slow selling" (see `docs/LABEL_PROVENANCE.md`).
- No physical-progress claim (BCMS notice = intent; corroboration tiers A/B/C).

## 7b. Survival and drift evidence (session 3)

**Activation survival (final-grant snapshot, hazard model):** discrete-time
logistic hazard with scheme features + interval index + time-varying COVID
regime flags. Train grants <2020 (n=511), test >=2021 (n=382).
Concordance 0.48 test / 0.45 train; td-AUC@24m 0.53; predicted 24m terciles
flat (0.53/0.53/0.54). **The hazard model does NOT discriminate activation
timing; it does not beat the KM cohort baseline** (brief 16.6 stop rule:
model not advanced). KM strata show size matters (10-29u: 51% by 24m vs 250+u:
29%) and grant-era matters (2016-19: 52% vs 2021+: 50%) — the cohort-strata
baseline is the interim estimator. 10 commencements preceded their register
grant date (enabling works; flagged, clipped, reported).

**Completion survival:** among 730 commenced schemes, 655 completed; median
~477 days commencement→CCC; ~90% complete by 36m (size bands similar where n
allows).

**FI rolling origins (2018-2022):** AUC 0.64/0.67/0.73/0.75/0.60 by origin
year; model over-predicts ~5-15pp with flat calibration slopes; 2022 vintage
shows prevalence drop (0.77→0.61) and Brier spike. Drift thresholds
pre-declared in `configs/rules/drift_monitoring.yaml`; quarterly review,
version-and-deprecate, never auto-refit to noise.

**Sprint 6 observation:** the existing 04_fi request-item extraction covers
only ~166 of the 1,095 pool schemes and contains ePlan boilerplate pages in
many files — document pipeline quality must be rebuilt per-authority; counts
are joined as label-side enrichment (fi_item_count/fi_doc_count), never as
submission features.

## 8. Next steps (per brief §26/27 + Amendment A)

1. Optional human audit: adjudicate `data/silver/audit_queue_bcms_links.csv`
   (61 rows) and `data/silver/audit_queue_ppr_links.csv` (60 sampled rows).
   Gate 2 needs ≥95% confirmed-link precision; modelling already uses
   conservative exact-reference rules and the audit measures whether they are
   safe. Not a blocker for research modelling.
2. Productise the FI leg: rolling-origin retraining (evidence base exists),
   drift monitoring per `configs/rules/drift_monitoring.yaml`, band CIs, then
   the pain model card (FI probability + cohort-strata activation baseline +
   composite with published weights).
3. Activation: promote the cohort-strata KM baseline (size band x grant era)
   as the interim estimator; revisit scheme-specific survival only with
   richer final-grant features (document-extracted conditions, unit changes).
4. Sprint 6 execution: rebuild the FI/conditions document pipeline for 2-4
   pilot authorities behind `devrisk/extraction` connectors (contract
   `planning_friction_v1`); the 04_fi corpus needs per-authority quality
   remediation first.
5. Stop for review before any 500-scheme expansion.
