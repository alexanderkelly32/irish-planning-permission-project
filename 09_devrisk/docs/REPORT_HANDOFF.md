# REPORT HANDOFF — everything needed to write the planning underwriting report

Status: numbers generated, bounded and confirmatory-checked as of 2026-10-06.
Source files under `09_devrisk/data/silver/` (paths per section).
Worked example: **SD17A/0397** (85 dwellings, South Dublin, submitted
2018-04-18); generated document `silver/report/demo/report_SD17A_0397.md`.

## 0. The consumer number set (fine-tooth-combed)

Rule: the consumer sees ONE headline probability per section, a confidence
line, and nothing that does not survive backtesting or statistical support.
The reference-class and raw model internals are NOT consumer-facing.
Grades below are from the confirmatory record.

### Tier 1 — headline numbers (each survived multi-era/backtest, large n)

| # | Line | Demo value | Evidence |
|---|---|---|---|
| 1 | Refusal probability (calibrated) | 17.2% (band 12.2% [11.2,13.2], n=4,460) | frozen model AUC 0.792, n=35,713 holdout, ±0.9pp calibration |
| 2 | Clean-outcome probability vs grant | clean 13.6% vs grant 72.1% | distinct information (r=0.355), Brier 0.2317, n=107,619 test |
| 3 | Six-month decision tail | 0.3% | AUC 0.680 vs 0.517 refusal-only; prevalence 11.1% |
| 4 | Ultimate success probability | 82.9% [75.4, 88.9] at 4 rescue matches | compound of validated parts; matched-cohort assumption stated |
| 5 | Rescue plan match-count table | 0/1.7/5.6/18.7/24.9% (fresh-era 0/1.2/4.5/17.4/21.0%) | strongest result - monotone, non-overlapping CIs, fresh-era confirmed |
| 6 | Abandonment base rate | 41.0% [40.5, 41.5] | n=40,172, zero-model arithmetic |
| 7 | Deliverable supply vs nominal | 2,935 nominal -> 1,475 [1,044-1,957] at 24m/3km | backtest +9.4-43.6% MAE over conversion baseline, 80 catchments |
| 8 | Authority static baseline | SDCC houses 13.1% [12.4, 13.8], -20.9pp vs national | n=8,901, arithmetic on history |

### Tier 2 — one-line context (real but weaker; never headlines)

| # | Line | Demo | Caveat |
|---|---|---|---|
| 9 | FI likelihood | 64.6% (band 47.5% [46.0, 49.0]) | demo-era model uncalibrated; historical AUC 0.69-0.73 |
| 10 | Appeal involvement | 41.6% (band 15.8% [14.7, 16.9]) | demo-era model materially miscalibrated - the BAND is the honest read; do not headline the point |
| 11 | Pre-commencement conditions | national 16.3% [12.7, 20.8] | corpus n=319, 2020+ only; rolling-origin AUC 0.71-0.77 |
| 12 | Precedent themes | 10-11 of 12 similar refusals: density/scale | keyword classifier, descriptive |
| 13 | Drafting associations | trimmed 91.5% vs 66.9% | correlational wording mandatory |
| 14 | Path distribution | fi_grant 24.3%, grant_appeal 30.3%, direct_refusal 15.4% | joint model beats baseline (log-loss 1.111 vs 1.173); collapse <2% paths |
| 15 | Divergence caution (fires or not) | not fired | validated as error-inflation only, never as "model wrong" |
| 16 | Price benchmark | €330k (IQR €242k-€466.5k, n=3,012) | market context |
| 17 | Site track record | 9 prior apps 1999-2017 | descriptive facts |

### Tier 3 — NOT in the consumer report

- Raw (uncalibrated) model scores of any era — internal only.
- Reference-class rate presented as a probability — context or cut.
- Units-reduction drafting line — sign flips on fresh era.
- Financial-condition family prediction — AUC 0.63-0.69.
- Option calculator — include ONLY if the client supplies assumptions;
  otherwise omit (it is arithmetic on assumptions, not intelligence).
- Six-way path table where a three-way summary (grant / refusal / appeal
  involvement) suffices for the reader.
- 2D calibration cell details — internal; surface only as the confidence
  band when a cell exists.
- Any "site difficulty" or "developer alpha" language — falsified/blocked.

## 1. What this report is
A bounded, evidence-backed planning underwriting document for one proposed
scheme, frozen at submission time. It answers: permission risk, whether the
process will be clean, the delay tail, the burden if successful, what
historically rescues refusals, what competes locally, and — only under
stated assumptions — what that means economically.
Discipline: one headline per section with its confidence line; associations
never stated as causes; the report says what it cannot know.

## 2. The confidence hierarchy (tone guide)
- Fresh-era/rolling confirmed: rescue plan, clean-outcome, 6m tail,
  pre-commencement conditions, supply aggregation, abandonment,
  divergence-as-error-inflation, 2D cells.
- Confirmed with caveat: frozen refusal model (time-safety for
  retrospectives), description-trim (correlational).
- Demoted - never headline: units-reduction, divergence-as-AUC,
  financial-condition family, latent site difficulty/alpha.

## 3. Consumer report structure (writing order)

Write in this order; use the tier tables above for the numbers. The
report's job is to differentiate: a normal planning platform cannot say
the clean-vs-grant gap, the rescue plan, the abandonment rate or the
expected-deliverable supply - those four are the product.

1. **Permission risk** — calibrated refusal probability + confidence band
   + one context sentence for the authority baseline. (Tier 1 #1, #8)
2. **Clean process** — clean-outcome vs grant, the r=0.355 distinctness
   stated in one sentence. (Tier 1 #2)
3. **Process friction** — FI and appeal as ONE line each, band-anchored;
   delay tail. (Tier 1 #3, Tier 2 #9-10)
4. **If it goes wrong** — abandonment rate, rescue match-count table,
   precedent themes, drafting associations (correlational wording).
   (Tier 1 #5-6, Tier 2 #12-13)
5. **If it wins** — pre-commencement condition context (Tier 2 #11).
6. **The lender number** — ultimate success probability with its CI
   (Tier 1 #4).
7. **The market** — deliverable supply vs nominal, price benchmark
   (Tier 1 #7, Tier 2 #16).
8. **The site** — track record dossier (Tier 2 #17).
9. **Economics** — option calculator ONLY with client assumptions, or omit.
10. **Fingerprint** — one line of the headline numbers; no aggregate score;
    divergence-caution status if fired.

Every headline number has exactly one confidence line (Wilson CI or band,
with support count). Nothing from Tier 3 appears.

## 4. What the report must never claim

- Causality for rescue/drafting/regime statements.
- Individual scheme commencement/completion dates.
- A unified "risk score" aggregating components.
- Family-level condition predictions outside the corpus window.
- Any economic output without labelled client assumptions.
- Site-difficulty or developer-alpha ratings (falsified/blocked).

## 5. Provenance map

| Component | Key file(s) |
|---|---|
| Frozen refusal model | `05_policy/current/model_v4/` |
| Calibration bands (refusal/paths/clean/tail) | `silver/report/bounds/report_bounds.json` |
| Reference-class + divergence | `silver/report/zero_day/reference_class_test.csv`, part1 report |
| 2D cells | `silver/report/zero_day/calibration_2d_cells.csv` |
| Compound + abandonment | `silver/report/confirmatory/confirmatory_summary.json` |
| Rescue/drafting | `silver/sprint2/refusal_grant_pairs.csv`, rescue_plan_report.json |
| Authority baselines | `silver/report/zero_day/authority_type_baselines.csv` |
| Supply | `silver/sprint5/supply_backtest.csv` |
| Condition corpus | `silver/conditions/condition_corpus.csv` |
| Registry (all 70 experiments) | `silver/experiment_registry.json` |
| Full trial history | `09_devrisk/docs/PREDICTION_ACCURACY_FULL.md` (§1-50) |
| Measurement spec | `09_devrisk/docs/PRODUCT_REPORT_SPEC.md` |
| Engine freeze | `09_devrisk/docs/ENGINE_V1_FREEZE.md` |
| Demo document | `silver/report/demo/report_SD17A_0397.md` |

## 6. The dossier close

Every report ends with a revealed dossier in retrospectives: actual decision,
FI, appeal, decision duration — compared to predictions, with the misses
stated (demo: granted in 22 days ✓; FI predicted 64.6% and occurred ✓;
appeal predicted 41.6% and did not occur — flagged by the band).
