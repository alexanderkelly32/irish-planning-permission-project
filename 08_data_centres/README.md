# 08_data_centres

Initial workspace for a broad data-centre sweep across the planning dataset.

## What is here

- `scripts/extract_data_centres.py`
- `scripts/bucket_ambiguous_data_centres.py`
- `scripts/build_data_centre_map.py`
- `source_data/all_data_centre_mentions.csv`
- `source_data/likely_data_centres.csv`
- `source_data/data_centre_related_applications.csv`
- `source_data/ambiguous_data_centres.csv`
- `source_data/excluded_non_data_centre_mentions.csv`
- `source_data/ambiguous_data_centres_bucketed.csv`
- `source_data/ambiguous_data_centres_bucket_summary.csv`
- `source_data/data_centre_exploration_summary.csv`
- `source_data/data_centres_map_ready.csv`
- `current/data_centres_map.html`
- `current/data_centres_overview.png`
- `current/data_centres_map_summary.json`

## Current approach

This follows the same broad pattern as `07_solar`, but tuned for data-centre wording in:

- `02_development/source_data/ground_source_extracted_final_wide_comprehensive_master.csv`

The extractor intentionally throws a wide net. It looks for:

- explicit `data centre` / `data center` / `datacentre` wording
- `data storage facility` and `data processing facility`
- large-scale `ICT facility` wording that reads like a data-centre campus
- noisier lookalikes such as `digital hub`, telecom `co-location`, `ICT room`, and `server room`

The first pass then:

- keeps clear data-centre applications
- separates likely related applications such as amendments, retention, and extension-of-duration cases
- moves edge cases into an ambiguous review bucket
- records obvious non-data-centre false positives that came back from the wide-net scan

The review bucketing step then promotes or excludes edge cases such as:

- mixed-use blocks with explicit data-centre floors
- telephone exchange conversions to telecoms data-centre use
- small or specialised resilience / recovery facilities

## Caveat

This is still a planning-description-led scrape rather than a definitive national inventory of built or operating data centres. It should be a strong planning map, but some very small ancillary IT facilities may still sit near the line between a true data centre and ordinary on-site server infrastructure.
