# V4 text-plus-structured candidate evaluation

`05_policy/scripts/build_national_residential_model_v4_candidate.py` evaluates a separate research candidate. It does not write a deployable model artifact and does not change the app default.

The candidate adds submitted units, site area, floor area, density/plot-ratio proxies and missingness indicators to the v3-style text/history/comparable feature set. It uses deterministic SGD logistic regression solely to make full five-fold grouped evaluation tractable; it is therefore not an estimator-identical ablation of the liblinear v3 artifact.

On the untouched 2025 holdout (`n=15,221`), the v4 candidate ranking ROC-AUC was `0.7931` and average precision `0.4129`, below frozen v3 (`0.7989`, `0.4202`). Its calibrated Brier score was `0.0848` versus v3's `0.0849`, but this small calibration difference does not offset weaker ranking. The candidate is not promoted.

The accepted revision audit contributes 90 mapped cases, with 86 pre-2025 rows. GroupKFold produces five non-overlapping training folds; known accepted-pair members cannot occur across a train/test fold. Most records are still singleton groups, so this is a leakage guard rather than a comprehensive project-identity benchmark.

Generated evidence: `05_policy/current/raw_planning_v4_candidate_evaluation.json` and `raw_planning_v4_2025_predictions.csv`.
