# 10_energy

Energy-infrastructure intelligence workspace: outcome prediction and timeline
watching for Irish power projects (solar, wind, battery storage, grid,
biogas, hydro, CHP). Data centres are extracted as demand-side context only —
they are not prediction targets.

## What is here

- `scripts/extract_energy_cohort.py` — builds the energy cohort from the
  canonical planning register, reusing the `07_solar` and `08_data_centres`
  extractions (read-only) for solar farms and data centres.
- `source_data/` — extraction outputs (cohort CSVs, decision-normalisation
  stats, summary JSON).
- `current/` — derived references and maps for the product layer.

## Design rules (carried from the frozen planning work)

- The residential product line and all frozen artifacts (`05_policy`,
  `06_copilot`, `09_devrisk`) are read-only from this workspace.
- `case_key` is the primary key; authority+application-number only as fallback.
- Time-safety applies to every feature that will feed a model: historical
  features are computed from earlier rows only.
- Decisions are normalised into `grant / refuse / split / invalid / exempt /
  withdrawn / additional_info / undecided / other`; the raw string is always
  kept alongside.
- Utility-scale vs minor classification is stored explicitly and never
  silently dropped; the mention-level CSV keeps everything the patterns hit.

## Caveats

The county register under-covers ABP-determined strategic cases (SID data
centres, wind above the SID threshold, grid reinforcement and interconnectors).
ABP ingestion is the known largest coverage gap and is tracked separately.

## Status

Cohort extraction (v1). No models yet.
