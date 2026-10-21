# Sprint 0 baseline: national residential Model v3

Verified 1 September 2026 from the checked-in artifacts under `05_policy/current`. This is a frozen regression reference for the optimiser work; it is not a claim of guaranteed individual planning outcomes.

## Reproduction

```powershell
$env:PYTHONPATH = (Resolve-Path .vendor).Path
python 05_policy/scripts/verify_model_v3_baseline.py `
  --registry 05_policy/baselines/model_v3_2026-09-01.json
```

The verifier reads the saved prospective predictions, recomputes the metrics, loads the v3 bundle, and runs the same smoke query twice. It does not rebuild or overwrite model artifacts. The registry contains the environment, command, metric tolerance, and SHA-256 hashes.

## Current architecture

- Source/derived planning tables: `02_development`, `03_refusal`, and `04_fi`.
- Model construction and evaluation: `05_policy/scripts/build_national_residential_model_v2.py`, `build_comparable_feature_experiment.py`, and `build_national_residential_model_v3.py`.
- Frozen candidate bundle: `05_policy/current/model_v3/national_residential_v3_comparables.joblib`.
- Reusable query scoring and precedent logic: `06_copilot/scripts/precedent_copilot_logic.py`.
- Presentation layer: `06_copilot/scripts/similar_developments_app.py`.
- Current persistence: files only; there is no canonical Site/Application/Scheme/Scenario/ModelRun database.

## Model contract

Model version: `national_residential_v3_comparables`.

Prediction time is immediately before submission. The classifier predicts local-authority refusal risk. The product's estimated grant probability is derived as `1 - refusal_probability` and must be labelled as a modelled estimate.

Direct feature groups are:

- planning authority;
- broad application bucket;
- leakage-stripped initial development description;
- submission year;
- time-safe national, authority, same-site, and nearby history counts/rates;
- earlier text-similar comparable-case outcome aggregates.

The bundle explicitly bans FI requests, decision fields for the scored case, appeals, refusal reasons, and post-submission status.

## Frozen prospective results

| Measure | Value |
|---|---:|
| Holdout rows | 15,221 |
| Holdout dates | 2025-01-02 to 2025-12-23 |
| Refusal rate | 11.56297% |
| Ranking ROC-AUC | 0.7989005 |
| Ranking average precision | 0.4201984 |
| Ranking Brier | 0.1381840 |
| Ranking log loss | 0.4314373 |
| Calibrated ROC-AUC | 0.7925909 |
| Calibrated average precision | 0.4104294 |
| Calibrated Brier | 0.0849118 |
| Calibrated log loss | 0.2907695 |

Bootstrap intervals, reliability by authority/application bucket, risk-band thresholds, and the full prospective output remain in the v3 manifest and `05_policy/current` CSV/JSON artifacts. Small or one-class council/type groups require caution.

## Structured-field audit

The GE10 development table contains 9,876 rows. Current non-null coverage is:

| Candidate field | Rows | Coverage |
|---|---:|---:|
| `units_total_best` | 9,876 | 100.0% |
| `max_storeys_best` | 4,041 | 40.92% |
| `parking_spaces_best` | 2,549 | 25.81% |
| `cycle_parking_spaces_best` | 1,531 | 15.50% |
| `site_area_ha_best` | 1,412 | 14.30% |
| `floor_area_sqm_best` | 939 | 9.51% |
| `open_space_sqm_best` | 1,873 | 18.97% |

Height and setback fields are not present as reliable national structured columns. Density, plot ratio, site coverage, and ratios can be derived only where their component values are present and units are validated.

## Implications for the first scenario release

The structured form will capture the full V1 scheme contract, but each field will carry a support classification. Units can alter the v3 application bucket at boundaries; description edits can alter text/comparable features and must be labelled language sensitivity. Most other physical fields are initially captured-only or retrieval-only and may produce an unchanged v3 score. The UI must say so explicitly rather than inventing a causal or model-active effect.

## Known technical debt blocking a fuller optimiser

- No canonical durable domain records or scheme versioning.
- No immutable ModelRun ledger.
- No structured mutation service or scenario comparison view.
- No automated test suite (the repository currently uses Python `unittest` for new tests).
- Structured feature coverage is incomplete, especially for height and setbacks.
- Existing v3 comparable features are text-based and must remain time-safe.
- Appeals, refusal reasons, FI, policy evidence, and revision pairs are separate future layers and must not leak into the submission-time classifier.
