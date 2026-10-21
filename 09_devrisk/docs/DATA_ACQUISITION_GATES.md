# Data acquisition mode — frozen benchmark and gates

Date: 2026-10-02. Modelling frozen. Every incoming dataset is evaluated
against this benchmark with a clean ablation, then kept or dropped fast.

## Frozen benchmark (do not retrain while waiting)

Same cohort, same protocols, corrected labels:

| Leg / Target | Benchmark |
|---|---|
| Commencement (production GBM, 2022+ clean eval) | MAE 433d; ±180d 16.6%; ±365d 37.5% |
| Commencement (train <2020, test 2020+) | MAE 366d rolling-24m; GBM 384d |
| Completion (scheme-level, constant) | median 403d, MAE 241d, IQR 254d |
| Sale (production ladder, corrected labels) | elastic-net 349d; size-band 353d |
| Sale (2022+ clean eval) | 386d |
| CCC->sale (event-level, corroborated) | constant MAE 228d; ±180d 67.9%; ±365d 79.3% |
| Error budget | grant->commencement 54.9%, construction 27.3%, CCC->sale 17.8% |

Label hygiene suite (tests/test_label_hygiene.py, 8 invariants) must stay
green for any rebuilt label set.

## Gates per source (fail fast)

### BER (SEAI)
GATE: materially reduce completion-label uncertainty OR improve phase
resolution. Measure: commencement->first-CCC MAE/IQR with BER-wave
completion vs the 241d/254d benchmark; share of schemes whose CCC date
is corroborated within 90 days by a final-BER cluster. DROP if neither
improves; keep as aggregate feature if only weak.

### HSA AF1/AF2 + ESB NC1 + Uisce (FOI)
GATE: observed mobilisation reduces grant->commencement MAE or 80%
interval width. Measure: commencement MAE/width with observed start
dates vs 433d (2022+) / 366d (2020+). DROP any source that fails;
keep events for the live updating model regardless.

### ECAD/GeoDirectory
GATE: materially improve BCMS/PPR/BER matching precision or coverage.
Measure: PPR pending-row attribution precision and scheme coverage
(767 -> ?); phase resolution via date-burst clusters vs BCMS units.
DROP if no precision/coverage gain; keep as address-standardisation
service if only marginal.

## Ingestion protocol

1. Land raw data with provenance manifest (existing ingestion pattern).
2. Rebuild affected labels; run label-hygiene suite (must pass).
3. Run the single ablation defined for that source against the frozen
   benchmark numbers above.
4. Record the result in PREDICTION_ACCURACY_FULL.md with the gate
   verdict; keep or drop.

## Standing user actions

1. SEAI BER registration (docs/SEAI_BER_ACCESS.md).
2. Send FOI letters 1-5 (docs/FOI_REQUEST_TEMPLATES.md) - HSA, ESB,
   Uisce, Part V, contributions.
3. ECAD sample request via eircode.ie form.
