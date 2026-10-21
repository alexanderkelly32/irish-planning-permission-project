# Planner.ie — distilled

*Distilled 2026-09-24 from the public-site scrape (`docs/planning_sites/planner.ie.md`). Vendor claims, not verified facts.*

## Snapshot

**Planner.ie is the direct category competitor for the score**: "Ireland's first report to predict your approval odds for planning applications." A one-off consumer/professional report product at **€74.99**, currently waitlist-stage. Its site is thin — the scraper captured only the homepage; `/about-us` returned HTTP 500.

- Pitch stats: "1 in 7 planning applications in Ireland are refused. Don't let your project become one of them."
- Trust claims: "Backed by millions of records"; "Trusted by 1,000+ users" — vendor claims, no measurement period, no paid-customer definition.
- Audience: homebuyers, architects, estate agents; developers mentioned.

## The report (as advertised)

Four steps: enter address → "our system searches millions of Irish planning records" → "AI analyses key details" → receive report with "approval chances, risks to watch and tips to boost success."

Report contents:
- **Approval odds** (headline feature — the score)
- **Local planning comparables** — real applications near the property, "what has been approved or refused and why"
- **Smart recommendations** — based on council policies and common refusal reasons
- **Local area insights**; "planning data analytics"; "evidence-based predictions"

Claimed inputs: "verified Irish planning data, zoning policies and past council decisions." **No methodology, holdout, calibration, confidence intervals, model version or validation is published** — and no 10+ unit specific framing, no risk register, no override/audit, no PDF decision record.

## Pricing

- **€74.99 one-off report** — "one clear price… no subscriptions, no hidden fees."
- CTA is still **waitlist** ("Join the waitlist"), i.e. the product appears to be in controlled release despite the 1,000+ users claim.

## What's missing / to verify

- Any dated, out-of-sample validation (ours: 2024–25 holdout, n=35,713, AUC 0.792 / GE10 n=464, AUC 0.782).
- Calibration bands or confidence ranges (ours: per-band empirical CIs shown with every score).
- Refusal-ground explainability (ours: top-3 historical grounds with rationale).
- Planner ownership features (ours: register, owners, mitigations, override audit trail, PDF).
- Live 2026 data (ours is honest that the register is frozen at 2025-12-23 — the gap to close).

## Our angle vs Planner.ie

This is the "same score, no receipts" competitor. When its reports ship broadly, buy one, run the **same 10+ unit applications with the same information cutoff** through both, and record: predicted number, input burden, evidence shown, caveats, and the actual outcome. Its €74.99 transaction price and consumer positioning are a different segment to our €200/month professional product — but it legitimises the category, and its lack of published validation is exactly where we must keep leading.

## Source pages

- Home: https://planner.ie/ (only page captured — /about-us returned HTTP 500 during collection)
