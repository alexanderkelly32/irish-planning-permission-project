# Imagery State-Machine — Repository & Data Inventory (2026-10-08)

Purpose: document everything the multimodal development-monitoring programme
can build on, and everything that must NOT be repeated. Frozen results are
law until a new experiment passes its predefined gate.

## 1. Development identifiers & master tables

- `case_key` = "Council Name__appno" (e.g. `South Dublin County Council__SD17A/0397`).
  Used across register, labels, BCMS links, PPR links, state machine.
- `development_id` = identifier used in the site_polygons.geojson and the
  AlphaEarth pipeline (verify mapping when joining).
- Register: `bronze/npad_register_bronze.parquet` (491,760 rows): authority,
  description, units, site area, floor area, ITM coords, received/decision/
  grant/FI/appeal dates, Decision, ApplicationType, LandUseCode.
- Labels: `silver/pain_labels_pool.csv` (1,095 schemes): activation_days,
  completion_days, linked flags, sales_linked, fi_requested, appeal_submitted.
- Clean view: `silver/dq/labels_clean.csv` (491 schemes; excludes quarantined/
  pending). Quarantine rules R1-R11 in `silver/dq/quarantine.csv`.

## 2. Site polygons

- **`silver/site_polygons.geojson` — 646 real Polygon features**, properties
  {development_id, area_m2}. THIS is the primary spatial substrate; use
  polygons (with 25/50/100/250 m buffers) wherever possible, centroid fallback
  only where no polygon exists and must be flagged.
- Derived stats (not geometries): `silver/parcel_geometry_features.csv`
  (area/perimeter/compactness/frontage/elongation for the same 646).
- Phase candidates: `silver/phase_polygon_candidates.geojson` (unvalidated).
- 4Dublin polygons (separate pilot): `raw/housing_open/4dublin_polygons.geojson`.

## 3. Administrative event streams

- BCMS: `silver/bcms_events_silver.parquet` (249,127 events): notice received,
  commencement, CCC dates, units, phase numbers. Links: `silver/bcms_links_all_granted.csv`.
- CCC blocks: `silver/ccc_blocks.csv` (2,286 blocks: first/last CCC, events, units).
- PPR sales: `silver/scheme_sales_bcms_notice_auto.csv` (7,329 linked sales).
- Conditions compliance: `silver/idocs/` ledgers + readiness docs (~100 schemes
  with correspondence texts incl. bond/contribution compliance).
- FSC/DAC: `silver/infrastructure_readiness_features.csv` (5,948 schemes).
- State machine: `silver/state_machine/states.csv` (15 states, entered dates,
  sources, observed/inferred flags) + transitions.json.

## 4. Frozen temporal splits & benchmarks (do not substitute)

- Refusal model (v4-full): train pre-2024, holdout 2024-2025, n=35,713,
  AUC 0.792, calibration ±0.9pp. FROZEN.
- Commencement benchmark: ~433d MAE on the 2022+ clean eval; ~366d rolling-24m.
- Completion: constant median 403d, MAE ~241d.
- Development first-sale: ~349d MAE. CCC→first-sale: ~228d MAE.
- Standard split convention: train received/grant < 2022, test >= 2022.
- State-machine/calibration machinery (conformal bands, per-transition tables)
  is production; imagery must add ON TOP of these, not replace them.

## 5. Existing imagery work — MUST NOT be repeated

- **AlphaEarth (annual GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL, 2017-2025):
  FALSIFIED.** State classifier 0.562 vs 0.656 majority; commencement
  357d vs 349d base; CCC-within-365d AUC 0.564 (below gate); sale +2.8%.
  Pipeline: `scripts/run_alphaearth_*.py`, features `raw/alphaearth/
  alphaearth_features.csv` (5,814 site-years). Annual cadence is the reason
  it cannot see construction timing — do not rerun the annual embedding
  design; higher-cadence Sentinel time series is the untested route.
- Google Earth Engine auth works on this machine: `ee.Initialize(
  project="planning-project-1")` (gcloud default credentials).

## 6. Potential leakage fields (never use backwards)

- All post-submission dates: FI dates, appeal dates, decision/grant dates,
  BCMS notice/CCC dates, PPR sale dates, condition-compliance dates.
- Realised future weather between prediction date and outcome.
- Revised polygons or later imagery relative to the snapshot.
- The state machine's `entered` dates are event records — usable only as
  labels/events at their own timestamp, never as submission-time features.

## 7. Weather sources to fetch (free, authorised)

- Met Éireann EDR API (opendata2.met.ie/edr): NRT ONLY (collections cover
  the last ~48h; parameters air_pressure, air_temperature etc.) - NOT
  suitable for 2018-2026 history. VERIFIED 2026-10-08.
- Met Éireann historical daily station observations: climate-portal CSV
  downloads (met.ie/climate/available-data; Azure blob links) - the route
  for history; fetch pending.
- Met Éireann gridded daily rainfall/temp + 1991-2020 normals.
- ERA5-Land reanalysis only if gridded Met Éireann is insufficient.

## 8. Imagery sources to fetch (free, authorised)

- Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED in EE), 10m, 5-day revisit.
- Sentinel-1 GRD (COPERNICUS/S1_GRD in EE), VV/VH 10m, 6-day revisit.
- NASA HLS 30m as a baseline; OPERA disturbance alerts if practical.
- OSM building footprints (historic where available) as secondary signal.
- Do NOT use proprietary basemaps (Google/Bing/Esri) contrary to terms.

## 9. Registry & discipline

- Append-only experiment registry: `experiments/imagery_experiment_registry.csv`
  (id, hypothesis, cohort, prediction date, features, model, split, metrics,
  CI, compute cost, verdict KEEP/RETEST/DROP, reason).
- Staged: S1 feasibility (50 inspected), S2 screening (200-400), S3 full
  backtest, S4 prospective monitor (timestamped, never edited).
