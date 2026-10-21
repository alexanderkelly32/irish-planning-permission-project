# Pilot drawing pull — 9 estates, manual browser task

The iDocsWeb "I Agree" postback resists automation (parked: ASP.NET
viewstate flow). The pilot needs the site-layout / phasing drawings for
these 9 estates. In a normal browser this is ~2 minutes per estate.

## How to do it

For each URL: open it, click **"View Scanned Files"**, tick **"I Agree"**,
then download the documents whose names contain **Site Layout**, **Layout
Plan**, **Phasing**, **Master Plan** or **Overall Site** (PDF preferred).
Save them anywhere local and tell the assistant where — filenames must
keep the application number.

| # | Estate (appno) | URL |
|---|---|---|
| 1 | Limerick 21531 (5 phases) | https://eplanning.ie/LimerickCCC/AppFileRefDetails/21531/0 |
| 2 | Kildare 18711 (4 phases) | https://www.eplanning.ie/KildareCC/AppFileRefDetails/18711/0 |
| 3 | Tipperary 20171 (3 phases) | https://www.eplanning.ie/TipperaryCC/AppFileRefDetails/20171/0 |
| 4 | Kildare 181027 (3 phases) | https://www.eplanning.ie/KildareCC/AppFileRefDetails/181027/0 |
| 5 | Kildare 18541 (3 phases) | https://www.eplanning.ie/KildareCC/AppFileRefDetails/18541/0 |
| 6 | Waterford 21836 (2 phases) | https://www.eplanning.ie/WaterfordCCC/AppFileRefDetails/21836/0 |
| 7 | Wicklow 181193 (2 phases) | https://www.eplanning.ie/WicklowCC/AppFileRefDetails/181193/0 |
| 8 | Galway City 18127 (2 phases) | https://www.eplanning.ie/GalwayCity/AppFileRefDetails/18127/0 |
| 9 | Meath 22930 (2 phases) | https://www.eplanning.ie/MeathCC/AppFileRefDetails/22930/0 |

## What we do with them

Extract phase boundary polygons / house-number schedules from the PDF
pages (vector or image), then test: can ECAD/BER address points be mapped
into BCMS phases at >=95% audited precision? That is the pilot's go/no-go.
