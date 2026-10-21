# Locked model registry — 2026-10-02

Architecture and keeper features frozen per plan direction. No new feature
families enter production models without a forward-holdout improvement
recorded here.

## Production models (locked)

| Target | Architecture | Keeper features |
|---|---|---|
| Refusal | v4-full (frozen 22 Sep 2026, read-only) | unchanged |
| FI | logistic/GBM + TF-IDF text + structured + history | + pipeline state (provisional: +0.001 with text; +0.030 structured-only) |
| Appeal | logistic + structured + TF-IDF | + pipeline state (+0.015 holdout) |
| Decision timing | quantile GBM + smooth CDF + authority congestion | unchanged |
| Commencement | quantile GBM + structured + constraints + applicant | + developer-state v2 (-15d), + pipeline (-16d), lineage provisional (-10d) |
| Completion | constant median / hazard baselines | no feature model survives OOS |
| Sale | elastic-net ladder | developer-state v2 marginal (-4d); rebuild deferred until BER/ECAD labels |
| Price | same-county contemporaneous benchmark | unchanged |

## Label rules (locked)

- scheme_sales_verified.csv: only verification_status != 'pending' rows
  feed labels (label hygiene fix 2026-10-02).
- Verified label count at lock: 767/1,095 pool schemes (70.0%).
- Phase-level sale labels: blocked structurally (no phase address ranges
  published); only unit-address-level data (ECAD/BER) can unblock.
- Unlinked = UNKNOWN, never negative.

## Frozen experiment ledger

All experiment outcomes recorded in PREDICTION_ACCURACY_FULL.md; nothing
is retried without new data.
