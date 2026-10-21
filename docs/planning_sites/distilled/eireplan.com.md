# EirePlan.com — distilled

*Distilled 2026-09-24 from the public-site scrape (`docs/planning_sites/eireplan.com.md`). Vendor claims, not verified facts.*

## Snapshot

**EirePlan is the workspace + API layer**: "The public record for sites in Ireland" — planning history, ground context, services and transport brought together around an address, with provenance on every figure. A data company first, software second. Free self-serve tier + quote-based paid plans; the only one of the five with a public REST API.

- Stated scale (as at 2026-08-19): **370,000+ applications from every planning authority**, **99.4% placed on the map**, joined to **33 national datasets**.
- Context it publishes: 16.5% of applications nationally were invalidated on completeness (Aug 2025–Jul 2026); average decision 71 days.
- Traction signal: named integration "Speed-Deed — in production since 2026".

## Product surface

- **Map**: every application in context; zoning and precedent view modes, layer toggles, amenities, drawing and measurement tools.
- **Sites**: one workspace per address — "a site outlives its applications": full history, the documents behind it, and the ground it sits on. A sample site (St Stephen's Green) is opened publicly.
- **Precedent search**: filter by authority, decision, status, type across the whole register → open the council's own documents behind any result (free, no account).
- **AI assistant**: answers drawn from the record and cited back to it; "where the record is incomplete, it says so." Free: 20 queries/month.
- **Per-authority statistics**: dedicated page for each of the 31 authorities — volumes, grant rate, invalidation rate, decision times — plus 2026 YTD vs same period last year.
- **API** (`api.eireplan.ie`, Bearer auth, documented REST):
  - Search precedents (`/ext/v1/precedents`) with pagination and normalised decision/status filters
  - Site history by address / Eircode / coordinates
  - **Site history by GeoJSON polygon boundary** (`/ext/v1/precedents/site-history/polygon`) — supply your site boundary, get its planning history
  - Precedent detail with official links; Knowledge API; Local Authority Lookup

## Data: 35 source feeds, six layers

1. **Planning & delivery** — all 31 local-authority registers; development plans, zoning, local area plans, plan-objective areas, council zoning maps; RZLT final maps; building-control commencement/completion notices; Property Price Register (county-level context).
2. **Ground & environment** — GSI aquifers, karst, landslide records/susceptibility, LiDAR coverage, physiography, quaternary geomorphology; EPA radon risk, strategic noise contours, licensed industrial/waste facilities, water-framework status.
3. **Services & capacity** — **urban wastewater capacity (treatment plants and agglomerations)** for early service-capacity screening; grid connections and contracted capacity ("wastewater headroom, grid connections").
4. **Heritage & land** — National Monuments Service recorded monuments + protection zones; NIAH surveyed buildings; **protected structures and ACAs "where the authority publishes them"**; **Tailte Éireann cadastral parcels with freehold/leasehold tenure** (fetched per site, to show how a boundary sits against title).
5. **People & movement** — CSO Census 2022 small areas/EDs; Pobal HP Deprivation Index; transport, schools, energy ratings; national airfields & ports.

## Pricing

- **Free**: no card, no expiry, "not a trial" — national record search, map + policy layers, assistant; **50 searches/month, 6 sites, 20 AI queries**, no export/filtering, no site-history reports, no API.
- **Solo / Practice / Team**: quote-based ("Talk to us"). Search limits 1,000 / Unlimited / Unlimited; site-history reports 5 / 20 / 20-per-seat pooled; document register on all paid; AI queries 150 / 500 / 500-pooled; drafting & analysis paid-only; API on **Practice and Team**; shared workspace + roles only on **Team** (3+ seats). Limits reset monthly.
- Trust-building move: "Test it on a case you already know… the free account is enough."

## Stance & trust

- "Software should support professional judgement, not replace it." Explicitly does **not**: make planning decisions, submit applications, generate reports without professional review, or replace qualified planners.
- "An absence is shown differently from an answer… where the record does not say, the page says it does not say."
- Every figure keeps its source dataset and vintage; decision notices quoted with page ("Condition 7, Decision notice, p.4…").
- Security page: organisation/project isolation **enforced at the database level**; AI scoped to the active project, no cross-organisation reuse; client data ownership retained.

## Our angle vs EirePlan

EirePlan is the closest thing to our future infrastructure layer — and its **polygon site-history API is the direct analogue of our boundary-draw**. It is simultaneously a competitor (sites, precedents, constraints) and a potential data partner (freshness, tenure, capacity layers we lack). It deliberately does not do outcome prediction or planner-owned risk registers — those remain our space. Watch its API adoption: if practices start building on `eireplan.ie`, it becomes the platform to interoperate with.

## Source pages

- Home: https://eireplan.com/ — features: /features — data sources: /data-sources — how it works: /how-it-works
- Pricing: https://eireplan.com/pricing — security: /our-security — API: /docs (endpoints under /docs/endpoints-*)
- About: https://eireplan.com/about — stats: /insights
