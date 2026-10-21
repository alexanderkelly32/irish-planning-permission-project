# Archa.ie — distilled

*Distilled 2026-09-24 from the public-site scrape (`docs/planning_sites/archa.ie.md`). Vendor claims, not verified facts.*

## Snapshot

**Archa is a B2B planning-intelligence bureau**: commissioned, fixed-scope written reports on any Irish site, plus a free-ish **MCP connector** that lets AI tools (Claude) query Irish planning data. Not SaaS and not a predictor — it sells sourced, decision-grade analysis to people who "cannot afford to be wrong."

- Tagline: "An intelligence report on any Irish site."
- Terms are **B2B-only**: the client warrants trade/business/professional use; Consumer Rights Act 2022 explicitly excluded.
- Process: brief via /contact → **scope + fixed € price within 48 hours** → work starts on written acceptance → delivered to an agreed date. "No commitment until scope agreed."

## What a report delivers

A bespoke written analysis joining **every public register that touches an Irish site**, each claim sourced back to the original document; supporting data tables and spatial visuals. Typical commissions cluster around four moments: **pre-acquisition due diligence, pre-planning strategy, response to a refusal, portfolio-level review**. Sites with no planning history still get a spatial profile; sites with records get deeper document-level evidence.

Seven themes joined at the planning-application reference:
1. **Planning application** (the key)
2. **Ownership & capital** — who really holds permissions: holding companies, SPVs, dissolved entities behind the applicant name, and the corporate chain above them *(unique among the five)*
3. **Planning history & appeals** — every decision, condition, refusal, appeal
4. Land & tax exposure (RZLT liability, zoning, pyrite/mica zones, flood maps, 30+ spatial overlays)
5. Permission viability (expiry dates, extension-of-duration eligibility, substantial-works test)
6. Regulatory-stack risk (policy changes applied mid-flight)
7. Administrative timeline (council decision-time benchmarks)

## Published signal analytics (each cited to source)

- **85%** of recycled RZLT sites change hands — small developers sell under pressure, institutional buyers acquire at discount ("The RZLT Paradox").
- **1-in-20** developers with expiring permissions files an extension — "22,769 residential permissions granted 2019–2021 sit in that window ≈ 170,000 units" ("The Silent Lapse").
- **9** policy changes applied mid-flight since 2019: NZEB, Part V doubling, SHD abolition, Defective Blocks Act, RZLT, nationwide RPZ, Residential Tenancies Amendment Act ("Rules Changed").
- Council timelines 2025: median decision **46 days (Dublin City) → 97 (Roscommon)**; 90th percentile **61 (Wexford) → 267 (Carlow)** — every commissioned report benchmarks a site against its council baseline and the p90 tail.
- Blog series covers the structural market: "Ireland Has a Viability Ceiling, Not a Planning Bottleneck", "Where Ireland Actually Builds", "The Scale Trap", "The Pivot: Ireland's Social Housing Is Now Majority Bought, Not Built".

## The MCP connector (`https://archa.ie/mcp`)

- Connect **Claude (Pro / Max / Team / Enterprise)** to Irish planning data via Model Context Protocol — one URL, OAuth 2.1 sign-in (Google/Microsoft), toggled per conversation.
- Capabilities advertised: search planning applications across all 31 councils; full application details (descriptions, decisions, dates, documents); plain-English questions; **generate precedent reports, risk assessments and summaries**; track decisions, appeals and conditions.
- Strategy read: bespoke reports for revenue, MCP access for reach into AI workflows.

## Pricing & terms

- Commissions: fixed-scope € quotes; payable on delivery unless otherwise scoped; **Revolut Business invoicing**; VAT per Irish rules with reverse-charge for EU business clients; perpetual, non-exclusive licence to use the report for its commissioned purpose — no resale/redistribution; briefs, addresses and client identities confidential.
- Named data sources: local-authority planning registers (CC-BY 4.0), An Bord Pleanála, Tailte Éireann (Land Registry/PSRA), Companies Registration Office, Ordnance Survey Ireland, CSO, EPA (list truncated in scrape).

## Our angle vs Archa

Archa sells what our brief aspires to be handed to a planner — but as a **human service**, priced per engagement, aimed at funds and solicitors. Its ownership/corporate-chain analysis and viability-signal framework ("85% of recycled RZLT sites change hands") are angles our product doesn't cover at all and could borrow as brief content. It is not a software competitor; it competes for the same due-diligence budget and sets a "how much would a human charge for this?" anchor for our pricing story.

## Source pages

- Home: https://archa.ie/ — commission: /contact — connect: /connect — terms: /terms — blog: /blog
