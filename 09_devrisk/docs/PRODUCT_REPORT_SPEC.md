# Product Report — Measurement & Uncertainty Specification (v1)

Principle: every number in the customer report carries the right kind of
uncertainty, chosen per output. No single "risk score". Bounds live in
silver/report/bounds/report_bounds.json and are regenerable.

## 1. Permission / refusal risk

- Metric: calibrated refusal probability (frozen v4-full; holdout AUC
  0.792, calibration +-0.9pp).
- Right bound: LOCAL CALIBRATION BAND - among historical applications
  whose predicted risk fell in the same band, the observed refusal rate
  and its Wilson 95% CI. Example display: "Predicted 12% (band 10-15%);
  historical observed rate in this band: 11.4% [9.8, 13.1]."
- Why: the model is isotonically calibrated; the remaining honest
  uncertainty is the empirical band rate, not model-internal variance.
- Note: the frozen model's own holdout calibration (+-0.9pp mean abs)
  is stated once as a model-quality line; per-scheme bounds come from
  the band table.

## 2. Planning path distribution

- Metric: full path probability vector (multinomial, full-distribution
  log-loss 1.111 vs 1.173 stratified baseline).
- Right bound: PER-PATH calibration bands (observed path frequency by
  predicted-probability band, Wilson CI) + support counts per path.
- Report displays each path with its band; paths with predicted
  probability <2% are collapsed into "other/unlikely" - never presented
  as precise rare-event probabilities.

## 3. Clean-outcome probability

- Metric: P(grant & no FI & no appeal & decision <= 12m); AUC 0.638,
  prevalence 0.551, Brier 0.2317; corr with grant prediction 0.355
  (distinct information - always shown with the grant probability).
- Right bound: local calibration band (as refusal).

## 4. Six-month delay tail

- Metric: P(decision > 6m); AUC 0.680 vs 0.517 using refusal alone
  (+0.163); prevalence 0.111.
- Right bound: local calibration band + prevalence context ("1 in 9
  applications overall; yours is 1 in X").

## 5. Pre-commencement conditions

- Metric: P(any pre-commencement condition); rolling-origin AUC
  0.714-0.765 across three splits (promoted); bootstrap-compatible
  lower bound ~0.72.
- Right bound: Wilson CI on family prevalence (small-n families) +
  the rolling-origin AUC range stated honestly. Family-level claims
  only where n >= 15 positive cases; otherwise "insufficient support".
- Financial-family model remains provisional (AUC 0.63-0.69): shown
  with the provisional flag.

## 6. Rescue / mutation intelligence

- Metric: grant rate by number of recommendations matched (frozen
  retrospectively on <2021, evaluated >=2021): 0/1/2/3/4 -> 0.0/1.7/
  5.6/18.7/24.9%.
- Right bound: WILSON 95% CI per match count (e.g., 3 matched:
  18.7% [16.2, 21.5]; 4 matched: 24.9% [22.8, 27.1]). Every
  recommendation carries its support count (n of historically similar
  refused cases that changed X and were granted) and the correlational
  wording ("historically associated with", never causal).

## 7. Deliverable competing supply

- Metric: expected deliverable units by horizon (state-conditional
  aggregation); backtest gain +9.4..+43.6% MAE over conversion baseline,
  -45..-56% vs nominal.
- Right bound: MONTE CARLO interval - the forecast distribution over
  200 draws per scheme, displayed as median with 50/80% ranges, plus
  the backtest coverage of those intervals (to be added when the MC
  ranges are computed). Individual scheme dates never implied.

## 8. Option / land-bid calculator

- Not a probability - deterministic under stated assumptions.
- Right bound: SENSITIVITY GRID over assumption ranges; no CI. Every
  input labelled observed / modelled / client-assumption / derived.

## 9. Planning fingerprint

- A synthesis of components 1-8, each with its own bound. No combined
  score. The report's "confidence" line = the weakest component's bound,
  not an aggregate.

## Display rules

1. Never a point probability without its band/CI and support count.
2. Rare events are collapsed, not estimated precisely.
3. Correlational wording is mandatory for rescue and regime statements.
4. "Not enough historical support" is a legitimate output.
5. The report states what it CANNOT say (individual commencement dates;
  causal claims) at least once per section where relevant.
