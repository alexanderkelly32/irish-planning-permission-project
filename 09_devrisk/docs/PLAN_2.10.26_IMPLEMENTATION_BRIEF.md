# Plan 2.10.26 — implementation snapshot

Date: 2026-10-02. What was implemented, measured outcomes, what was not done.

## Implemented

| # | Plan item | What was built | Files |
|---|---|---|---|
| E1 | Professional-team extraction | Scanned all 5,308 planner-report PDFs; regex role->firm extraction (1,148 mentions, 636 PDFs); entity-resolved; time-safe team features (prior n, FI rate, appeal rate, median decision days) | `run_extract_consultant_teams.py`, `silver/consultant_mentions.csv`, `silver/consultant_team_features.csv` |
| E2 | Site lineage | Same-parcel (<=60m) application genealogy from the full register; 220/1,095 pool schemes (20.1%) have prior same-parcel applications; features: prior refusals/grants, rate, size trajectory, days since last decision, description similarity | `run_site_lineage.py`, `silver/site_lineage_features.csv` |
| E3 | Local pipeline state | Time-safe 1/3/5/10km features at each grant date from BCMS + register (KDTree): granted-not-commenced units, commenced units, CCCs 3/6/12m, progression ratio, same-type competitors, prior apps | `run_pipeline_state_features.py`, `silver/pipeline_state_features.csv` (n=1,095) |
| E4 | Developer state + interactions | Time-safe developer/group state: live uncommenced schemes, units granted/commenced/completed, authority count, recent grant->start and start->CCC medians, size trajectory, type familiarity, county-expansion flag, SPV count, dev x authority/type/band shrunk medians (264 schemes with history) | `run_developer_state_features.py`, `silver/developer_state_features.csv` |
| E5 | Infrastructure readiness | FSC/DAC national dataset downloaded; Uisce Eireann capacity-register page saved (status mentions extracted); SDCC road-opening licences located | `run_infrastructure_pulls.py`, `raw/infrastructure/` |
| — | Ablation suite | Base (log_units + apartment flag) vs +each family on commencement (GBM), sale (GBM), FI (logistic) | `run_plan_ablation_suite.py`, `silver/plan_ablation_suite.json` |

## Measured outcomes

| Target | Base | +lineage | +pipeline | +devstate | +team |
|---|---|---|---|---|---|
| Commencement MAE (days) | 351 | 344 | **339** | 344 | 351 |
| Sale MAE (days) | 2,098 | 2,099 | 2,094 | 2,106 | 2,098 |
| FI AUC | 0.438 | 0.484 | **0.591** | 0.382 | 0.430 |

Notes: sale base here is the 2-feature model (the full ladder's ~425d uses more
features), so comparisons are within-row. Pipeline state is the strongest new
signal (FI +0.153 AUC, commencement -12d). Lineage helps FI (+0.046). Team
features are flat at current extraction quality. Devstate is flat-to-worse
with this construction.

## Not done

- Team extraction refinement (the plan's #1 priority deserves better than the
  1,148 regex mentions; OCR of scanned PDFs would raise coverage).
- E5 feature integration (FSC/DAC join to schemes; Uisce WWTP-status feature;
  road-licence construction-state events) — data pulled, not yet wired.
- Policy-fit experiment (plan item 6): zoning-layer literal features exist
  only for Dublin (dublin_case_policy_features from earlier work); national
  version not built.
- Parcel geometry/topography (item 8): not built.
- Construction-team/technology fingerprints (item 9): BCMS method/material
  fields exist in silver but were not turned into features.
- Local absorption (item 10, new-build €/m²): not built.
- Graph entity table / graph model: not built.
- Two-product framing (day-zero vs continuously updating): architecture
  exists (multi-state engine + harness) but was not extended this pass.
- Decision-timing and appeal ablations for the new families: not run
  (suite covered commencement/sale/FI).

## State of the running loops

- PACK_22 (final pull-classifier round, 60 rows) awaiting user verdicts.
- Confirmed sales: 811/1,095 (74.1%) at last label rebuild.
- OSM estate pull: complete (1,071 inventories).
