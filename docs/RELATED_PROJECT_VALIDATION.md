# Related-project validation status

`05_policy/scripts/build_v3_related_project_diagnostics.py` audits the frozen 2025 Model v3 holdout without changing the model or its benchmark.

It treats a related project only as an identical `SiteId` within the same planning authority. Missing `SiteId` values become singleton case groups; it does not infer relationships from address text. This is deliberately stricter than the revision-pair queue.

The current output is `05_policy/current/raw_planning_v3_related_project_diagnostics.json`. It found no repeated usable SiteId groups in the pre-2025 training data and no 2025 holdout group seen in training. Therefore the whole holdout is in the conservative `unseen` subset and the original frozen metrics are unchanged.

`related_project_validation.py` also provides reproducible `GroupKFold` topology checks for a future candidate with accepted related-project groups. Do not describe Model v3 as group-retrained or group-validated until that data exists and a candidate has actually been trained and scored under those folds.
