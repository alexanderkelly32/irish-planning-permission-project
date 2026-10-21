# AlphaEarth (Satellite Embeddings) — access steps

Dataset: `GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL` — 64-dim embeddings per
10 m pixel, annual composites 2017–2025, designed for classification/
regression/change detection.

## Access routes

**A. Google Earth Engine (free tier, standard annual dataset)**
1. Sign in to https://earthengine.google.com with a Google account
   (free non-commercial signup; commercial use needs a separate
   arrangement — flag before product use).
2. Create a Cloud project at https://code.earthengine.google.com
   (project creation is automatic on first login).
3. Install the API: `pip install earthengine-api`
4. Authenticate once: `earthengine authenticate`
5. Dataset: `ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDINGS/V1/ANNUAL")`
   — images 2017..2025, band `embedding` (64 dims, 10 m).

**B. Maps Platform satellite-embeddings preview (REST, API key)**
- Custom windows (weekly/monthly/5-day) are private preview; requires a
  Google Cloud API key and preview approval.
- URL: https://mapsplatform.googleapis.com/... (preview docs only).

## Extraction plan (what to pull)

For each site polygon (see `silver/site_polygons.geojson`):
- 2017..2025 annual images, bands `embedding` (64) clipped to:
  site polygon, 100 m ring, 250 m ring.
- Reduce per polygon per year: mean + std of each band, plus per-pixel
  time series for change features (cosine year-over-year, % large change,
  first year of major change, consecutive change years).
- Export as one CSV per site-year (or a single national CSV) to
  `09_devrisk/data/raw/alphaearth/`.

## Note on the free dataset

Annual 10 m composites: monthly milestone dating is NOT possible from it;
small phases may be inseparable; no pre-2017 history. Weekly/custom-window
embeddings are a separate commercial preview.
