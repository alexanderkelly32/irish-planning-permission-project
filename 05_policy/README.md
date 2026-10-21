# 05_policy

Policy document pull focused on the Dublin local authorities represented in `03_refusal`.

## Scope

Source refusal file used to set the archive span:
- `03_refusal/current/refusal_reasons_cases_master.csv`

Filter applied:
- Dublin authorities only
- refusal cases with `reason_count > 0`

Earliest refusal-reason dates found:
- `Dublin City Council`: `2018-05-10` (`2532/18`)
- `Dun Laoghaire Rathdown County Council`: `2002-03-05` (`D02A/0005`)
- `Fingal County Council`: `2011-04-28` (`F11A/0080`)
- `South Dublin County Council`: `1995-07-20` (`S95A/0266`)

## Contents

- `documents/downloaded/`
  - downloaded policy PDFs grouped by authority
- `documents/extracted_text/`
  - cached text extraction per PDF, reused by the modeling pipeline
- `documents/zoning/raw/`
  - raw zoning downloads from official Dublin open-data or ArcGIS sources
- `documents/zoning/normalized/`
  - normalized zoning layers staged for spatial joins
- `documents/zoning/previews/`
  - rendered preview PNGs for PDF-derived zoning sheets
- `current/policy_documents_index.csv`
  - extracted document inventory with quality flags and text paths
- `current/policy_chunks.csv`
  - chunked policy text used for retrieval and feature generation
- `current/policy_clause_tags.csv`
  - deterministic policy theme tags per chunk
- `current/dublin_case_policy_matches.csv`
  - top retrieved policy chunks per Dublin case
- `current/dublin_case_policy_features.csv`
  - case-level policy retrieval features
- `current/hard_policy_rules_registry.csv`
  - structured hard-rule registry extracted from policy text
- `current/hard_policy_apartment_standards.csv`
  - canonical apartment minimum-size standards by authority and plan period
- `current/hard_rule_review_queue.csv`
  - extracted hard-rule candidates queued for human review
- `current/hard_rule_review_queue_apartment.csv`
  - apartment-only review pack for the first manual verification pass
- `current/verified_hard_policy_rules.csv`
  - approved hard rules copied from the reviewed source file
- `current/dublin_case_verified_hard_rule_features.csv`
  - case-level hard-rule outputs built only from approved rules
- `current/dublin_case_verified_hard_rule_matches.csv`
  - detailed case-to-rule matches built only from approved rules
- `current/verified_hard_rule_summary.json`
  - summary for the approved-rule pipeline
- `current/dublin_case_points_from_base.csv`
  - ITM coordinates recovered from raw base `geometry` for Dublin cases
- `current/dublin_zoning_layers_manifest.csv`
  - local manifest of normalized zoning layers currently staged
- `current/dublin_zoning_prep_summary.json`
  - summary of zoning downloads and derived case points
- `current/dublin_case_zoning_join_available_layers.csv`
  - case-to-zoning join using only the currently staged zoning layers
- `current/dublin_case_zoning_join_available_layers_summary.json`
  - quick coverage summary for the available-layer zoning join
- `current/dublin_case_zoning_with_inference.csv`
  - case-level zoning output that keeps official joins and adds clearly labeled Dublin City stability inferences for `2016-2022`
- `current/dublin_case_zoning_with_inference_summary.json`
  - summary of official plus inferred zoning coverage
- `current/pdf_zoning_sources_manifest.csv`
  - indexed PDF map-sheet sources for Dublin City, South Dublin, and Fingal zoning derivation work
- `current/pdf_zoning_manual_georef_queue.csv`
  - PDFs that still need manual georeferencing before they can contribute to zoning lookups
- `current/pdf_zoning_embedded_geo_footprints.geojson`
  - sheet footprints derived from embedded GeoPDF metadata where available
- `current/pdf_zoning_case_sheet_lookup.csv`
  - case-to-candidate-sheet lookup using embedded GeoPDF footprints
- `current/pdf_zoning_case_sheet_lookup_summary.json`
  - summary of case-to-sheet lookup coverage
- `current/pdf_zoning_prep_summary.json`
  - summary of PDF-derived zoning source prep
- `current/fingal_2011_2017_backcast.csv`
  - Fingal-only working table combining embedded-sheet candidates with low-confidence zoning backcasts from stable later official layers
- `current/fingal_2011_2017_backcast_summary.json`
  - summary of the Fingal `2011-2017` backcast workflow
- `current/dublin_case_hard_rule_features.csv`
  - case-level hard-rule comparison features
- `current/dublin_case_hard_rule_matches.csv`
  - detailed case-to-rule comparisons where a direct numeric comparison was possible
- `current/dublin_hard_rule_summary.json`
  - quick summary of extracted hard rules and comparison coverage
- `current/dublin_refusal_model_dataset.csv`
  - Dublin GE10 modeling table with policy features appended
- `current/dublin_refusal_predictions.csv`
  - scored cases with refusal probabilities and grounded policy explanations
- `current/dublin_refusal_metrics.json`
  - baseline vs policy-model holdout metrics
- `source_data/dublin_policy_manifest.csv`
  - one row per downloaded document
  - includes source URL, coverage years, refusal span context, and gap notes
- `source_data/verified_hard_policy_rules.csv`
  - human-reviewed hard-rule source of truth; only `approved` rows should feed the verified pipeline
- `source_data/verified_hard_policy_rules_template.csv`
  - schema template for building the reviewed hard-rule table
- `source_data/hard_rule_review_guide.md`
  - concise instructions for the manual review step
- `prompts/hard_rule_extraction_prompt.md`
  - LLM prompt for extracting candidate hard rules with citations
- `scripts/download_dublin_policy_docs.py`
  - reproducible downloader used to build this folder
- `scripts/build_dublin_policy_pipeline.py`
  - end-to-end extraction, chunking, retrieval, feature engineering and model training
- `scripts/build_dublin_hard_rules.py`
  - first hard-rules-first layer that extracts structured standards and compares them to cases where possible
- `scripts/init_verified_hard_rules.py`
  - seeds the review queue and verified-rules template from the extracted registry
- `scripts/build_verified_hard_rules.py`
  - builds hard-rule outputs using only human-approved rules
- `scripts/query_policy_for_case.py`
  - inspect retrieved policy chunks for a single `case_key`
- `scripts/prepare_dublin_zoning_inputs.py`
  - downloads programmatically reachable Dublin zoning layers, normalizes any manually supplied zoning files for missing plan periods, and recovers Dublin case points from base `geometry`
- `scripts/join_available_dublin_zoning.py`
  - joins Dublin cases to whatever normalized zoning layers are currently staged locally
- `scripts/build_dublin_zoning_inference.py`
  - builds a second zoning output that adds Dublin City `2016-2022` inferred zoning only where the earlier official reference layer and `2022-2028` official layer agree at the case point
- `scripts/prepare_pdf_derived_zoning.py`
  - indexes zoning map PDFs, renders previews, detects embedded GeoPDF metadata, and seeds the manual georeferencing queue
- `scripts/build_pdf_zoning_sheet_lookup.py`
  - joins cases to any PDF-sheet footprints that have embedded geospatial calibration
- `scripts/build_fingal_2011_2017_backcast.py`
  - builds a Fingal-only low-confidence backcast where `2017-2023` and `2023-2029` official layers agree, and carries forward the best embedded-sheet candidate

## Coverage Notes

Downloaded archive coverage:
- `Dublin City Council`: development plans covering `2016-2028`
- `Dun Laoghaire Rathdown County Council`: development plans covering `2004-2028`
- `Fingal County Council`: development plans covering `2005-2029`
- `South Dublin County Council`: development plans covering `2004-2028`

Public-site archive gaps still remaining:
- `Dun Laoghaire Rathdown County Council`: `2002-2003`
- `South Dublin County Council`: `1995-2003`

Those two gaps are recorded in `source_data/dublin_policy_manifest.csv` as `missing_public_source`.

## Pipeline Usage

Build the leakage-safe Dublin submission-time model:

```powershell
python 05_policy\scripts\build_dublin_submission_model.py
```

This model defines prediction time as immediately before submission. It excludes FI, refusal-reason, decision-date, appeal, grant, withdrawal, expiry, extraction-status, and post-submission status fields from the feature set. It writes:

- `current/dublin_submission_model_dataset.csv`
- `current/dublin_submission_policy_matches.csv`
- `current/dublin_submission_target_mapping_audit.csv`
- `current/dublin_submission_benchmark_summary.csv`
- `current/dublin_submission_authority_benchmark_summary.csv`
- `current/dublin_submission_related_group_split_diagnostics.csv`
- `current/dublin_submission_grouped_text_benchmark_summary.csv`
- `current/dublin_submission_rolling_temporal_validation.csv`
- `current/dublin_submission_tfidf_coefficients_description_text_only.csv`
- `current/dublin_submission_tfidf_coefficients_description_text_stripped.csv`
- `current/dublin_submission_predictions.csv`
- `current/dublin_submission_metrics.json`
- `current/dublin_submission_calibration_baseline_logistic.csv`
- `current/dublin_submission_calibration_policy_logistic.csv`
- `current/models/dublin_submission_baseline_logistic.joblib`
- `current/models/dublin_submission_policy_logistic.joblib`

It also runs simple decomposition benchmarks under the same split and leakage rules:

- authority only
- authority + received year
- structured features without text
- description/address text only
- stripped description text only, with obvious authority/date/address/application-number clues removed
- authority history features built only from earlier applications in the same authority

In the current implementation, `received_year` is numeric rather than categorical. The code also adds lagged authority refusal-rate features from prior applications so that time is represented through historical planning context rather than a brittle year bucket alone.

Optional XGBoost and LightGBM benchmarks are attempted when those packages are installed. If they are not installed, the script records the skipped benchmark in the metrics JSON and still completes the logistic-regression baseline. In this workspace they were installed locally under `.vendor/`, so run with:

```powershell
$env:PYTHONPATH = (Resolve-Path .vendor).Path
python 05_policy\scripts\build_dublin_submission_model.py
```

## Frozen National Model v1

`current/model_v1/national_residential_v1.joblib` is the frozen product candidate for submission-time residential planning risk. Its contract is recorded in `current/model_v1/manifest.json`.

The bundle contains two deliberately separate tracks:

- ranking model: trained on 203,931 pre-2025 residential applications; 2025 holdout ROC-AUC `0.779`
- calibrated probability model: classifier trained before 2023, Platt calibrated on 2023-2024, and tested on untouched 2025 cases; Brier `0.089`, calibration slope `0.930`

Inputs are limited to planning authority, numeric submission year, broad residential application bucket, and stripped initial application description. FI, decisions, appeals, refusal reasons, and all other post-submission fields are banned.

Rebuild the frozen bundle and its reliability metadata with:

```powershell
python 05_policy\scripts\build_prospective_calibration_backtest.py
```

The council and application-type reliability files are:

- `current/raw_planning_v1_reliability_by_authority.csv`
- `current/raw_planning_v1_reliability_by_application_type.csv`

## National Model v2 Candidate

`current/model_v2/national_residential_v2_history.joblib` is the current accuracy candidate. It keeps the v1 text/council/type/year inputs and adds submission-time historical planning-context features:

- national prior 24-month refusal rate
- authority prior 12/24-month refusal rates
- same-site prior refusal rate where `SiteId` is available
- nearby same-authority prior 1km/3km refusal rates where ITM coordinates are supplied
- log-transformed prior count features

The v2 ranking model is trained on 203,931 pre-2025 residential applications and tested on untouched 2025 cases. It improves ROC-AUC from about `0.779` to `0.793` and average precision from about `0.378` to `0.410`.

The v2 calibrated probability track trains the classifier before 2023, Platt calibrates on 2023-2024, and tests on untouched 2025 cases. It reaches ROC-AUC `0.786`, Brier `0.086`, log loss `0.294`, calibration intercept `0.070`, and calibration slope `1.032`.

Rebuild v2 with:

```powershell
python 05_policy\scripts\build_national_residential_model_v2.py
```

The supporting experiment is:

```powershell
python 05_policy\scripts\build_spatial_history_feature_experiment.py
```

## National Model v3 Candidate

`current/model_v3/national_residential_v3_comparables.joblib` is the current best accuracy candidate. It keeps v2 history features and adds time-safe comparable-case features. For each application, the feature builder retrieves text-similar earlier applications in the same broad residential bucket and aggregates their outcomes.

The v3 ranking model improves the 2025 prospective-style holdout to ROC-AUC `0.799`, average precision `0.420`, Brier `0.138`, and log loss `0.431`.

The v3 calibrated probability track trains before 2023, Platt calibrates on 2023-2024, and tests on untouched 2025 cases. It reaches ROC-AUC `0.793`, average precision `0.410`, Brier `0.085`, log loss `0.291`, and calibration slope `1.053`.

Build comparable features and v3 with:

```powershell
python 05_policy\scripts\build_comparable_feature_experiment.py
python 05_policy\scripts\build_national_residential_model_v3.py
```

The precedent copilot now loads Model v3 by default. Model v1 remains the simpler frozen baseline, and Model v2 remains the history-feature candidate. Earlier Dublin GE10 models remain research artifacts and should not be presented as the current product model.

Build the full Dublin policy pipeline:

```powershell
python 05_policy\scripts\build_dublin_policy_pipeline.py
python 05_policy\scripts\build_dublin_hard_rules.py
python 05_policy\scripts\init_verified_hard_rules.py
python 05_policy\scripts\build_verified_hard_rules.py
```

Inspect the policy matches for one case:

```powershell
python 05_policy\scripts\query_policy_for_case.py --case-key south_dublin_county_council_sd18a_0449
```

Optional embeddings:
- set `USE_OPENAI_EMBEDDINGS=1` before running the pipeline
- if no API key is available, the script falls back to TF-IDF retrieval only

Prepare currently available zoning inputs and run the zoning join:

```powershell
python 05_policy\scripts\prepare_dublin_zoning_inputs.py
python 05_policy\scripts\join_available_dublin_zoning.py
python 05_policy\scripts\build_dublin_zoning_inference.py
python 05_policy\scripts\prepare_pdf_derived_zoning.py
python 05_policy\scripts\build_pdf_zoning_sheet_lookup.py
python 05_policy\scripts\build_fingal_2011_2017_backcast.py
```

If you manually download official zoning files for missing plan periods, place one vector layer per folder in:

- `05_policy/documents/zoning/raw/dublin_city_council/2016_2022/`
- `05_policy/documents/zoning/raw/south_dublin_county_council/2016_2022/`
- `05_policy/documents/zoning/raw/south_dublin_county_council/2010_2016/`
- `05_policy/documents/zoning/raw/south_dublin_county_council/2004_2010/`
- `05_policy/documents/zoning/raw/fingal_county_council/2011_2017/`

Supported local formats:
- `.geojson`
- `.json`
- `.gpkg`
- `.shp`
- `.zip` containing a shapefile

The prep script will normalize the first matching file it finds in each folder and write the result into `documents/zoning/normalized/`.

## Recommended Hard-Rule Workflow

1. Run `build_dublin_hard_rules.py` to create extracted candidate rules.
2. Run `init_verified_hard_rules.py` to seed `current/hard_rule_review_queue.csv`.
3. Review and edit `source_data/verified_hard_policy_rules.csv`.
4. Mark only trusted rows as `approved`.
5. Run `build_verified_hard_rules.py` so downstream case comparisons use only approved rules.

## Verified Hard-Rule Status

Current approved-rule totals:
- `49` approved rules
- `21` apartment minimum floor area rules
- `15` communal amenity rules
- `6` parking minimum-per-unit rules
- `1` visitor parking ratio rule
- `6` open-space minimum site-ratio rules

Current verified comparison coverage:
- direct apartment-size matches: `9`
- verified apartment-size breaches: `2`
- communal rules available by plan: `475` cases
- parking rules available by plan: `137` cases
- open-space rules available by plan: `912` cases

Current limitation:
- many parking and open-space rules still need zoning or site-scope linkage before they can be applied as exact hard-rule comparisons

## Zoning Status

Current zoning prep / join status:
- Dublin base cases with recovered ITM coordinates from raw `geometry`: `2372`
- matched zoning joins from currently staged layers: `631`
- multiple polygon matches: `23`
- no local layer yet for the case plan period: `1464`
- no polygon match despite a local layer being present: `178`
- missing case geometry in the modeling join table: `68`

Currently staged normalized zoning layers:
- `Dublin City Council 2022-2028`
- `Dun Laoghaire Rathdown County Council 2022-2028`
- `Dun Laoghaire Rathdown County Council 2016-2022`
- `Dun Laoghaire Rathdown County Council 2010-2016`
- `Dun Laoghaire Rathdown County Council 2004-2010`
- `South Dublin County Council 2022-2028`
- `Fingal County Council 2017-2023`
- `Fingal County Council 2023-2029`

Remaining plan-period gaps to fill:
- `Dublin City Council 2016-2022`
- `South Dublin County Council 2016-2022`
- `South Dublin County Council 2010-2016`
- `South Dublin County Council 2004-2010`
- `Fingal County Council 2011-2017`

Current coverage that already improved from historic automation:
- `Dun Laoghaire Rathdown 2016-2022`: `50` matched cases
- `Dun Laoghaire Rathdown 2010-2016`: `1` matched case so far
- `Fingal 2017-2023`: `30` matched cases

Current inferred-zoning status:
- Dublin City `2016-2022` inferred from stable before/after zoning at the case point: `338` cases
- Dublin City `2016-2022` still unresolved after the stability check: `55` cases
- Fingal `2011-2017` not inferred yet because there is not currently a defensible before/after pair of official vector layers
- South Dublin intentionally left as official-only for now

## PDF-Derived Zoning Status

Current PDF source prep:
- `40` PDF map sources indexed
- `12` sources with embedded GeoPDF calibration
- `28` sources still requiring manual georeferencing

Current PDF source coverage by authority:
- `Dublin City Council`: `10` PDFs, all manual georeferencing required
- `South Dublin County Council`: `17` PDFs, all manual georeferencing required
- `Fingal County Council`: `13` PDFs total, `12` with embedded geospatial metadata

Current case-to-sheet lookup from embedded GeoPDFs:
- `53` cases narrowed to candidate sheets
- all current matches are `Fingal 2011-2017`
- current Fingal sheet footprints overlap enough that these are mostly multiple-candidate-sheet matches rather than unique sheet assignments

Current Fingal `2011-2017` working status:
- `24` cases have a low-confidence backcast because the `2017-2023` and `2023-2029` official layers agree at the case point
- `76` Fingal `2011-2017` cases still have no zoning backcast
- all `24` backcasts are explicitly labeled low confidence and should not be treated as equivalent to official or before/after-bracketed inferences
