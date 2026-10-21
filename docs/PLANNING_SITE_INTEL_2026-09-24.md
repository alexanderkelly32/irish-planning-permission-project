# Planning-site intel: the five incumbents, from their own pages

**Collected 2026-09-24** with `collect_planning_sites.py` (robots.txt-honouring, sitemap-driven; raw text in `docs/planning_sites/` + `docs/planning_sites.zip`). All claims below are **vendor claims from public pages** — ND means not documented publicly, not "does not exist". Complements the longer strategic memo `Irish_Planning_Intelligence_Incumbent_Analysis_2026-09-24.md` (in Downloads; covers UK analogues, reviews, pricing arithmetic and pilot design).

Scrape coverage: precedent.ie 250 pages (49k queued), eireplan.com 78 pages (complete), archa.ie 20 pages (complete; 3 dead blog links), planintel.ie 250 pages (11k queued), planner.ie 1 page (home; `/about-us` returned HTTP 500; the product is waitlist-stage).

---

## How the five relate (one page)

Two products sell the **record + refusal reasons** (Precedent, PlanIntel); one sells the **workspace/API layer** (EirePlan); one sells **bespoke human-grade reports + AI-tool access** (Archa); one sells a **consumer approval-odds report** (Planner).

| | What it is | Prediction stance | Refusal-reason scale | Pricing anchor | Our angle vs it |
|---|---|---|---|---|---|
| **Precedent.ie** | Land-sourcing & planning-data platform | ND (research, not a published per-scheme probability) | 16,834 refusals explained, "93% of every refusal on record"; 203,449 apps | €195/login/month, 12-month min (from earlier read of /pricing) | Its breadth (zoning 27+ authorities, title, subsoil, grid) beats ours; our scheme-level probability + planner-owned register doesn't exist there |
| **EirePlan** | "The public record for sites in Ireland" — map + site workspaces + precedent search + **public API** | ND | Not a headline count; source-linked council docs on demand | Free tier (50 searches, 6 sites/mo); paid quote-based | Infrastructure/workspace rival; its API (incl. **site-history by GeoJSON boundary**) is the closest analogue to our boundary-draw |
| **Archa.ie** | B2B commissioned intelligence reports + **MCP connector** for AI tools | ND (decision-support, not odds) | Full-text planning docs joined with ownership/corporate chains | Fixed-scope quote per commission (€, before work; B2B only) | Buys time for funds/solicitors; corporate-chain ownership analysis is something we don't do at all |
| **PlanIntel.ie** | One-person verified-evidence search + AI chat | **Explicitly declines to predict** ("Start with evidence, not a promise") | 2,151 reasons on record, growing on demand; 493,447 apps indexed; verbatim-quote verification | Free search; €29/yr Home; €39 site brief; €19/mo Pro | Its quote-verification discipline is the explainability bar; cheaper but no probability, no register, no PDF decision record |
| **Planner.ie** | Consumer/agent approval-odds report | **Yes — "Ireland's first report to predict your approval odds"** | "millions of records" (unspecified) | €74.99 one-off; "1,000+ users"; waitlist CTA | Direct category competitor for the *score*, but no published holdout/calibration/methodology and no 10+ unit register or audit trail |

Nobody publicly documents a dated, out-of-sample-validated probability **for a specific 10+ unit scheme** with a collaborative risk register and planner override. That remains the unoccupied combination.

---

## Dossiers

### Precedent.ie — breadth leader

- Pitch: "every planning decision in the State… and the thing no register publishes — why applications actually get refused."
- Stated scale: **203,449 applications** (31 authorities), **16,834 refusals explained (93% of every refusal on record)**, register decisions from 2021.
- One-click site check runs six layers: zoning (objective + source plan), flood (OPW/CFRAM within 100 m), ecology (SAC/SPA/NHA/pNHA in/out), protected structures (not loaded for every authority — disclosed on-page), subsoil, planning history (every application within 200 m + appeals).
- Buyer personas: developers/land sourcers, planners/consultants, renewable-energy developers (spare-grid-capacity search), land agents.
- Free case lookup (no account) with ref normalisation ("23/5520" = "235520").
- Methodological tone: dated, checkable counts (e.g. Limerick: 461 refusals read as of 4 Sep 2026; refusal shares that explicitly "do not sum to 100"; "count, not a rate" discipline). This is the transparency bar we are competing against.
- Notable Limerick finding it publishes: traffic/road-safety in 44% of refusals — "the decisions are about the entrance."

### EirePlan — the workspace + API layer

- Pitch: "The public record for sites in Ireland… with provenance for every result."
- Data: **35 source feeds across 6 layers**: (1) all 31 LA planning registers; (2) development plans/zoning/LAPs/plan objectives + RZLT final maps; (3) building control commencement/completion notices; (4) Property Price Register; (5) geoscience/environment (GSI aquifers/karst/landslides, EPA radon/noise/industrial/water-status, **urban wastewater capacity — plants and agglomerations**); (6) heritage & land (NMS monuments + SMZs, NIAH, protected structures & ACAs "where the authority publishes them", **Tailte Éireann cadastral parcels with freehold/leasehold tenure**, CSO 2022, Pobal HP deprivation, airfields/ports).
- Products: Map (zoning/precedent view modes, drawing + measurement tools), Sites (one workspace per address: "a site outlives its applications"), Precedent search (filter by authority/decision/status/type → open the council's own documents).
- **Public API** (`api.eireplan.ie`, Bearer): precedent search; site history by address/Eircode/coordinates; **site history by GeoJSON polygon boundary**; precedent detail with official links; normalized decision/status values.
- Traction signal: named integration "Speed-Deed — in production since 2026".
- Insights: per-authority stats pages (volume, grant rate, invalidation rate, decision times) + 2026 YTD vs same period last year.

### Archa.ie — bespoke intelligence reports + MCP

- Pitch: "An intelligence report on any Irish site" — "for decisions on Irish development that cannot afford to be wrong." B2B only (warrants non-consumer use; Consumer Rights Act 2022 excluded).
- Delivers a fixed-scope written report with sourced citations, data tables and spatial visuals; quoted in € before work; no charge until scope accepted; invoiced via Revolut Business; VAT rules stated. Typical briefs: pre-acquisition due diligence, pre-planning strategy, response to a refusal, portfolio review.
- Merges registers at the application reference: planning + appeals, **ownership & capital (who really holds permissions — holding companies, SPVs, dissolved entities, corporate chains)**, zoning & land tax, building control, sales, ecological/heritage designations, flood & subsidence, full text of planning documents.
- Published signal analytics (each cited to source): 85% of recycled RZLT sites change hands; 1-in-20 developers with expiring permissions file an extension ("22,769 permissions granted 2019–2021 ≈ 170,000 units" in that window); 9 policy changes mid-flight since 2019 (NZEB, Part V doubling, SHD abolition, Defective Blocks Act, RZLT, RPZ, RTAA); council timelines (2025 median 46 days Dublin City → 97 Roscommon; p90 61 Wexford → 267 Carlow).
- **MCP server** (`https://archa.ie/mcp`): connects Claude (Pro/Max/Team/Enterprise) to Irish planning data — plain-English queries, precedent reports and risk summaries via AI, OAuth 2.1 sign-in. Essentially: bespoke human reports for revenue + free-ish AI-tool access for reach.
- Data sources named: LA registers (CC-BY 4.0), ABP, Tailte Éireann, CRO, OSI, CSO, EPA (page truncated in scrape).

### PlanIntel.ie — one-person verified evidence, cheap

- Pitch: search + refusal explanations with source sentences, explicit no-prediction stance ("Start with evidence, not a promise"; "It cannot… guarantee a decision").
- Scale (self-published, live-generated): **493,447 applications indexed** (National Planning Applications dataset, data.gov.ie), **30 of 31 authorities** (Cork City not in the national dataset — disclosed), 203,315 council files read to searchable text, 8,858 read by the extraction model, **2,151 refusal reasons on record**; live refusal reasons for Carlow, Cavan, Clare, DLR, Fingal, Wicklow (grows on demand, not in bulk).
- Pipeline honesty: home-office GPU (Tesla P40, 24 GB); 35B MoE model → fine-tuned 4B local model (~10× faster) for document reading; **every quote checked word-for-word against the OCR text, unverifiable quotes flagged, unreadable records say so**.
- Pricing: free search/no account; Home €29/yr; site risk brief €39 incl. VAT; Pro €19/mo; AI chat free (5 questions/day).
- Publishes a **direct comparison page vs Precedent.ie** — coverage side-by-side with sources and dates. That page is a template for the coverage transparency we should ship.
- Self-build guide does the honest checklist (policy/zoning → rural need → access/sightlines → wastewater → constraints/precedent) with "what precedent cannot tell you".

### Planner.ie — the consumer odds claim

- Pitch: "Ireland's first report to predict your approval odds for planning applications"; "1 in 7 planning applications in Ireland are refused."
- Report contents: approval odds, local comparables ("approved or refused and why"), smart recommendations, area insights; built on "millions of real planning applications" and "zoning policies and past council decisions" (no methodology, no holdout, no calibration published).
- Pricing: **€74.99 one-off**, no subscriptions; "Trusted by 1,000+ users" (vendor claim); CTA still waitlist. `/about-us` returned HTTP 500 during collection — the site itself is thin.
- Audience: homebuyers, architects, estate agents; developers mentioned.

---

## Cross-cutting observations

1. **Refusal-reason extraction is the battleground.** Precedent claims 16,834 refusals explained (93% of record); PlanIntel 2,151 verified quotes (on-demand); EirePlan links council documents per result; we hold ~865 rationales in the recent 10+ bucket. Everyone is converging on the same underlying documents; the differentiators are coverage, verification discipline and how the reasons are presented.
2. **Coverage transparency is table stakes.** Precedent dates its counts and discloses per-authority gaps; PlanIntel publishes a live comparison vs Precedent; EirePlan keeps "source and vintage with every result." Our evidence-quality stamps are the same instinct — keep them visible.
3. **Two prediction stances only.** Planner.ie sells odds to consumers (no published validation). We sell odds to professionals (documented holdout). PlanIntel's explicit refusal to predict is the strongest signal that *verifiable* prediction is hard — and that a defensible one is worth protecting.
4. **Connectivity is the new surface.** EirePlan has a public API (incl. polygon site-history); Archa has an MCP endpoint so Claude can query Irish planning; PlanIntel has AI chat. The incumbent pack is already moving toward "planning data as a service for AI tools."
5. **Pricing floor/ceiling anchors:** €19–€39/month (PlanIntel) → €74.99 one-off (Planner) → €195/month ×12-month contract (Precedent) → bespoke € quotes (Archa, EirePlan paid). Our €200/month target sits beside Precedent, with no transaction-tier story yet.

## Scrape gaps to close later

- precedent.ie: pricing page not captured in the 250-page budget (case pages dominated the queue); re-run targeted at `/pricing` and `/features`.
- planner.ie: only the homepage (server errors on subpages); the product is waitlist-stage, so little is lost.
- archa.ie: source-list page truncated in scrape (EPA/CSO/etc. — page cut at 5 MB guard?); re-fetch `/contact` fully if needed.
- planintel.ie: council refusal-reason pages (per-county) exist for 6 counties — worth pulling one in full as a display benchmark.
