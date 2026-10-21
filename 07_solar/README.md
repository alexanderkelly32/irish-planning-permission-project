# 07_solar

Initial workspace for rough solar exploration across the planning dataset.

## What is here

- `scripts/extract_solar_farms.py`
- `scripts/bucket_ambiguous_solar.py`
- `source_data/all_solar_mentions.csv`
- `source_data/likely_solar_farms.csv`
- `source_data/solar_farm_related_applications.csv`
- `source_data/ambiguous_solar_mentions.csv`
- `source_data/ambiguous_solar_bucketed.csv`
- `source_data/ambiguous_solar_bucket_summary.csv`
- `source_data/solar_exploration_summary.csv`
- `source_data/likely_solar_farms_by_la.csv`

## Current approach

This is a first-pass text extraction from:

- `02_development/source_data/ground_source_extracted_final_wide_comprehensive_master.csv`

The extractor:

- pulls all rows where the description mentions `solar`, `photovoltaic`, or `PV`
- flags likely utility-scale projects when the wording points to a solar farm / solar park, or when it combines ground-mounted solar language with utility infrastructure signals such as substations, inverters, battery storage, grid connection, CCTV, fencing, and access tracks
- leaves the remaining non-rooftop matches in an ambiguous review bucket for spot-checking

The ambiguous bucketing pass then sorts those rows into practical categories such as:

- utility-scale candidates
- utility-scale related applications
- rooftop/building PV
- small or medium ground-mounted PV
- ancillary infrastructure PV
- agricultural on-site PV
- telecom / carport / miscellaneous solar uses

## Caveat

This is intentionally rough. It should be good enough to start mapping and exploration, but some cases will still need manual review before treating the set as final.
