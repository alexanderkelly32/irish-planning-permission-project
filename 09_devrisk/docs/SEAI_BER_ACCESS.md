# SEAI BER dataset access — exact steps

Goal: obtain the SEAI BER data for completion-cluster analysis. This is a
user action (account registration); the pipeline is pre-built to consume
the download when it lands.

## Steps

1. Go to https://www.seai.ie and create an account (email + password;
   free for researchers; no payment needed).
2. Open the National BER Research Tool: https://ndber.seai.ie/BERResearchTool/ber/search.aspx
   (logged in). This is the portal that grants the bulk download.
3. On the research-tool page, use the **download / export** function
   (varies by page version: a "Download full data" or CSV export button,
   or the datasets linked under "Open Data").
4. Download the **anonymised domestic BER dataset** for all years
   available (aim 2015 through latest quarter). Take CSV/zip files and
   save them anywhere; tell the assistant the path.
5. If the tool exposes a **spatial variant** (grid coordinates, small-area
   codes, or mapped exports), download that too — it is the version usable
   for completion-cluster analysis.

## What we expect in the file (varies by release)

| Field | Purpose |
|---|---|
| assessment date / date of issue | completion-wave timing (final BERs) |
| provisional vs final flag | filter to final BERs (constructed dwelling) |
| dwelling type, floor area, year of construction | new-build detection (year built == scheme era) |
| county / small area / grid coordinates | spatial clustering per estate |
| BER rating, energy values | matching consistency, unit mix proxies |

## Known caveat

The public research dataset has historically been anonymised (no full
addresses or Eircodes). If the download contains small-area/grid codes or
coordinates, we cluster per estate directly. If it contains only county
aggregates, we use it for completion-timing corroboration and use the
**BER Public Search** (per-Eircode, also in the portal) for address-level
queries on the shortlisted pilot estates only (30-50 estates, one-time).
Report which variant you received.

## Outputs you will get back

- completion-wave dates per estate (first final-BER burst -> completion
  proxy), validated against BCMS CCC dates;
- phase clusters via address + date bursts (polygon-free phase inference);
- pilot table for the 30-50 estates: BCMS CCC vs BER-wave agreement.
