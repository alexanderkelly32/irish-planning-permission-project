# Precedent.ie — distilled

*Distilled 2026-09-24 from the public-site scrape (`docs/planning_sites/precedent.ie.md`). Vendor claims, not verified facts.*

## Snapshot

**Precedent is the breadth leader**: a land-sourcing and planning-data platform that joins every planning decision in the State with ground constraints and — its headline differentiator — extracted refusal reasons. Commercial SaaS, no public per-scheme prediction.

- Stated scale: **203,449 applications** across **all 31 planning authorities**; **16,834 refusals explained — "93% of every refusal on record"**; register decisions from 2021.
- Pricing (from earlier read of /pricing, not in this scrape): **€195/login/month, 12-month minimum**.
- Free: case lookup by reference or address, no account (`/case`), with ref normalisation ("23/5520" = "235520"; same number can exist in several councils).
- Positioning line: "the thing no register publishes — why applications actually get refused."

## Product surface

- **Control-centre map**: planning decisions, land-use zoning (GZT), RZLT, flood extents, ecological designations, protected structures.
- **One-click site check — six layers**: zoning (objective + source plan), flood (OPW/CFRAM extents within 100 m), ecology (inside SAC/SPA/NHA/pNHA or not), protected structures (**not loaded for every authority — disclosed on-page**), subsoil, planning history (every application within 200 m + appeals).
- **Four buyer personas**: developers/land sourcers (find zoned land that never carried an application), planners/consultants ("read the refusal two doors down, in the planner's own words"), renewable-energy developers (search by distance to spare grid capacity; refused wind/solar/battery grouped by reason), land agents (evidenced history for buyers).
- **Case pages** show decision-document summaries, with honest gaps stated ("Analysis not available for this case", "PDF Document Missing… could not be linked").
- **Insights blog** (`/blog`) publishes dated, checkable analyses: Limerick refusals (461 read as of 4 Sep 2026; refusal counts per year stated as "a count, not a rate"; theme shares "do not sum to 100"; traffic 44% top ground); renewable refusals (88 refused wind/solar/battery, 25 councils, 2021–2026); spare grid capacity (13,791 clear unbuilt fields of 2 ha+ within 2 km of 5 MW spare capacity, joined to Land Registry titles).

## Methodology & trust posture

- "Built entirely on official public registries • Every figure checkable."
- Counts are **dated, not running totals** ("as of 4 September 2026"), so percentages don't silently shift under their own articles.
- Discloses per-authority coverage gaps on the page itself (protected structures "not loaded for this authority yet").

## Our angle vs Precedent

Precedent's edge is **data breadth and freshness** (title boundaries, subsoil, grid, 27+ authority zoning, 93% refusal-reason coverage). Our edge is **the submitted scheme as the unit of analysis** — a dated, out-of-sample-validated refusal probability for a specific 10+ unit proposal, plus a planner-owned risk register with override/audit. Precedent answers "what's on this site"; we answer "what happens to this scheme". The two are complements; a pilot side-by-side on one live case would map the overlap.

## Source pages

- Home: https://precedent.ie/ — case lookup: https://precedent.ie/case — insights: https://precedent.ie/blog
- Case page example: https://precedent.ie/case/1 (scrape p.78; shows "Analysis not available" and "PDF Document Missing" honesty patterns)
- Pricing page **not captured** in this scrape — re-fetch https://precedent.ie/pricing for the current figure.
