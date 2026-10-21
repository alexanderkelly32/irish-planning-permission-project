# Data provenance & licences

Everything in `09_devrisk/data/silver/report_bundle/` is derived from **public
Irish data**. Sources and licence/attribution requirements per file:

| bundle file | source | licence / note |
|---|---|---|
| `national_residential_v4_full.joblib`, `manifest.json` | fitted on the national planning register (below) | our model artifact; MIT-style under the repo licence |
| `comparable_reference.joblib` | derived from planning register descriptions | same |
| `runtime_models.joblib`, `bands.json`, `condition_models.joblib`, `theme_exposure_v6.joblib`, `drafting_constants.json` | fitted on register + BCMS + conditions corpus + refusal-reason corpus | our artifacts |
| `register_geo_min.parquet`, `refused_descriptions.parquet`, `supply_min.parquet`, `activation_min.parquet` | national planning application register (31 planning authorities, scraped from public ePlan portals); BCMS commencement records (public notices) | public planning records (PSI). Attribute "local planning authorities of Ireland" |
| `ppr_bronze.parquet` | Residential Property Price Register (propertypriceregister.ie) | PSRA open data — attribute "Residential Property Price Register, PSRA" |
| `flood_points.parquet` | OPW flood maps / CFRAM | public (OPW) |
| `sa_reference.parquet` | CSO Small Area Population Statistics | CSO open data — attribute "CSO" |
| `plan_summary.parquet`, `history_reference.parquet` | development-plan documents of the 31 planning authorities | public PSI |
| `authority_type_baselines.csv` | register aggregation | derived |

## Excluded from the repository (kept local only)

- **Live API keys** (`deepseek_key.txt`, `openai_key.env`, `keys/`) — secrets.
- **Private working notes** (`state/`, `notes/`, `tasks/`) — session transcripts and strategy.
- **Client-specific files** (`*Booterstown*`) — personal address data.
- **Third-party reviewer work product** (`*_COMPLETED*.csv`, `*review*.csv`, audit packs).
- **Raw source documents** — council PDFs/OCR (`03_refusal/documents/`,
  `04_fi/documents/`, `extraction_of_site_data/`), development-plan PDFs
  (`05_policy/current/policy_details/`), raw PPR/CRO archives. These remain
  available from the original public sources; the builder scripts in
  `02_development/scripts`, `03_refusal/scripts`, `05_policy/scripts` document
  how each was downloaded and processed.

## Rebuilding the bundle

`09_devrisk/scripts/run_freeze_runtime.py` rebuilds `report_bundle/` from the
local data layers. It is not required for using the engine — the frozen bundle
ships in the repo — but it is the reproducibility path.

## Using the engine

```
python 09_devrisk/scripts/run_report_engine.py inputs.json
```

See `09_devrisk/scripts/inputs_example.json` for the input schema. The engine
reads only `report_bundle/`; no network, no live data, no runtime training.
