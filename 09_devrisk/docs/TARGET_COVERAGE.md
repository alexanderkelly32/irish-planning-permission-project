# Target-by-target audit: data, coverage, predictability

Per the product direction (2026-09-28): predict concrete, observable events —
not a composite "pain" score. Each target below states its label source,
current coverage, what predicts it, and model status. Coverage measured on
the all-granted GE10 cohort (2,421) / mature window (1,384, grants
2016-2022) where relevant.

## 1. P(refusal) — planning outcome

- **Label**: local-authority refusal vs grant (register `Decision`).
- **Coverage**: complete — 3,585 GE10 rows; 575 refused. Frozen v4-full model
  (holdout n=35,713, AUC 0.792, calibrated). READY.

## 2. P(FI requested)

- **Label**: `FIRequestDate`/`FIRecDate` present. Mature coverage 1,000/1,384
  (72%).
- **Model**: calibrated logistic + TF-IDF, extended cohort retrain —
  holdout n=363, AUC **0.680** (0.62-0.74), AP 0.84. Description text carries
  the signal. READY (with drift monitoring).
- **Time-to-FI: NOT usable from the register.** The FI date fields cluster at
  51-63 days from submission (77 negatives) — they are statutory deadline
  artefacts, not real request dates. Real FI timing needs the document
  pipeline (04_fi files carry document dates; corpus remediation pending).

## 3. P(appeal)

- **Label**: `AppealSubmittedDate`/`AppealRefNumber`. Mature coverage 298/1,384
  (21.5%) — better than previously thought.
- **Model**: submission-time features give AUC **0.51** (no signal) even at
  298 events. Appeals are largely third-party/idiosyncratic at submission.
  Ship as a base rate with authority conditioning, not a feature model.

## 4. P(decision > 6m / > 12m) and time to decision

- **Label**: `DecisionDate - ReceivedDate`. Coverage 3,189/3,585 GE10.
- **Model**: GBM quantiles + horizon classifiers — READY (P50 MAE 63.9d vs
  baseline 80.2d; horizon AUC 0.75/0.72).

## 5. Refusal reasons (conditional on refusal)

- **Label**: human-verified theme tags, 1,380 refused cases (78% tagged).
- **Output**: conditional family priors + scheme transfer (top-3 55.6%
  disclosed). READY as evidence; conditional classifier not promoted.

## 6. Grant conditions (conditional on grant)

- **Label**: 17 starter-labelled reports (regex, 11 families). Corpus runner
  built for 166 granted eplanning schemes; crawl retry pending.
- **Status**: BLOCKED ON IMPORT — the only hard data gap in the concrete
  event set.

## 7. Time to commencement

- **Label**: grant -> first BCMS commencement (planning-reference link).
  Mature coverage 821/1,384 (59.3%); 562/585 unmatched have nearby BCMS
  records (neighbours/name mismatches) — audit queue live, expected to rise.
- **Model**: strata/hazard show no scheme-specific signal (lower-bound MAE
  ~346d vs median 379d). BASELINE-ONLY, honestly.

## 8. Time to sale

- **Label**: grant -> first PPR sale (address/eircode link). Mature coverage
  262/1,384 (18.9%); BTR/AHB exclusion explains only 86 schemes (6%) — the
  rest is address-format matching difficulty. Audit queue live.
- **Model**: no signal from authority/size/era (horizon AUC 0.51).
  BASELINE-ONLY; coverage growth is the lever, not features.

## 9. Certification milestones (FSC/DAC) — new proxies

- **Label**: FSC number on commencement notice (408/1,327 linked schemes),
  FSC on completion cert (312), DAC (301), completion-cert due date (152).
- **Use**: additional observable "progressed to certification" milestones;
  administrative, not physical completion. Table:
  `silver/milestone_proxies.csv`.

## 10. Comparison to similar schemes (size/density/authority)

Feasible for every target above: the register supplies authority, units, site
area (density), type; comparables carry the same labels. Engine h already
renders longitudinal comparables; each event model can be shown against
its comparable distribution (e.g., "your P50 112d vs 30-99 unit Meath peers
median 98d"). Data: complete.

## Coverage state summary

| Target | Label coverage | Predictable at submission? | Status |
|---|---|---|---|
| Refusal | 100% | yes (AUC 0.79) | READY |
| FI | 72% mature | yes (AUC 0.68) | READY |
| Appeal | 21.5% mature | no (AUC 0.51) | base-rate only |
| Decision timing | 89% GE10 | yes (MAE 64d) | READY |
| Refusal reasons | 78% of refused | conditional transfer | READY (evidence) |
| Grant conditions | 17 reports | pending corpus | BLOCKED ON IMPORT |
| Commencement timing | 59% mature (rising via audit) | no | BASELINE |
| Sale timing | 19% mature (rising via audit) | no | BASELINE |
| FSC/DAC milestones | 31% of linked | n/a (post-submission) | label built |

Two honest bottom lines: (1) the only missing data import is the
grant-condition corpus; (2) commencement/sale timing are coverage problems,
not model problems — the audit queues and time itself fix them.
