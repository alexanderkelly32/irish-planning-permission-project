# Structured-field signal screening

Run on 1 September 2026 with:

```powershell
$env:PYTHONPATH = (Resolve-Path .vendor).Path
python 05_policy/scripts/build_structured_feature_screening_experiment.py
```

Output: `05_policy/current/raw_planning_v4_structured_screening.json`.

## Design

This is a deterministic, text-free paired signal screen. Both arms use planning authority, application bucket, time-safe history, and earlier comparable-outcome aggregates. The candidate additionally uses submitted units, site area, floor area, density and plot-ratio proxies, plus missingness flags. It uses a frozen pre-2025 training window and the 2025 holdout (`n=15,221`).

It is not a Model v3 replacement experiment: description text is omitted and the classifier is a fast SGD logistic regression used to assess incremental signal.

## Result

| Metric | Text-free base | + structured fields | Delta |
|---|---:|---:|---:|
| ROC-AUC | 0.5809 | 0.6124 | +0.0315 |
| Average precision | 0.2245 | 0.2511 | +0.0265 |
| Brier | 0.1133 | 0.1108 | -0.0025 |
| Log loss | 1.5648 | 1.5292 | -0.0356 |

The fields contain incremental signal in this screen. They are still not ready to replace or augment v3 in production: the full v3 ranking model remains materially stronger (ROC-AUC 0.7989; AP 0.4202), and a proper successor must use the same text/reference contract, calibration, council/type reliability, and grouped related-project robustness checks.

## Product consequence

Keep units/site/floor-area fields captured for future modelling and retrieval. Do not claim a structured causal scenario effect. Height, setbacks, amenity, parking, and transport remain non-model-active because their national historical coverage is inadequate or unvalidated.
