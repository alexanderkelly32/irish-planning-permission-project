# PlanIntel.ie — distilled

*Distilled 2026-09-24 from the public-site scrape (`docs/planning_sites/planintel.ie.md`). Vendor claims, not verified facts.*

## Snapshot

**PlanIntel is a one-person, self-funded planning-evidence search engine** with an explicit no-prediction stance. It indexes the national dataset, OCRs council decision files, extracts refusal reasons with verbatim-quote verification, and sells cheap access (€19–39) plus a free AI chat. Its positioning line is the discipline we should borrow: **"Start with evidence, not a promise."**

- One person (Tashfeen), home-office hardware: a Dell workstation with a **2016-era NVIDIA Tesla P40 (24 GB)** running around the clock. "No office, no team, no funding."
- Stated scale: **493,447 applications indexed** (National Planning Applications dataset, data.gov.ie); **30 of 31 authorities** — Cork City not in the national dataset, disclosed; **203,315 council files read** to searchable text; **8,858 read by the extraction model**; **2,151 refusal reasons on record**.

## Pipeline (self-described, unusually candid)

1. County records pulled from council portals, scanned PDFs OCR'd, decisions/conditions/refusal reasons extracted into structured searchable form; every record links back to the council source.
2. Originally a **35B mixture-of-experts model**, slow on a 2016 GPU → the verified output was used to **fine-tune its own 4B model** trained specifically on Irish planning decision documents; ~10× faster; oversized documents still go to the big model.
3. **Quote verification**: every extracted quote is checked word-for-word against the OCR text; unverifiable quotes are flagged rather than shown as fact; low-confidence extractions marked on the page; unreadable documents say so instead of guessing.
4. Extraction runs **on demand** (when someone requests a record, brief or chat answer) rather than in bulk — the reasons count grows with use.

## Coverage state (live on the homepage, per county)

Each county card shows: applications indexed, refused count/rate, whether refusal reasons are live or generated on demand, decisions read, reasons on record, update date. Examples (20 Sep 2026): DLR 38,319 indexed / 5,192 refused (14%) / 619 decisions read / 193 reasons live; Fingal 20,059 / 2,558 (13%) / 3,519 read / **1,467 reasons**; Dublin City "Extracting now". Live refusal-reason counties: Carlow, Cavan, Clare, DLR, Fingal, Wicklow.

## Products & pricing

- **Free**: search, record pages, county refusal trends — no account.
- **AI chat**: 5 free questions/day; every answer linked to the record it came from.
- **Site risk brief**: €39 incl. VAT, one-off ("Check my site for €39").
- **Home**: €29/year; **Pro**: €19/month.
- Self-build guide ("Can I build a house on this land?") walks five checks in order — policy/zoning → rural housing need → access/sightlines → wastewater/services → constraints/precedent — and ends with "What precedent cannot tell you": it cannot confirm zoning, prove compliance with today's policy, test a wastewater design, certify sightlines, or guarantee a decision.

## The comparison page (worth reading directly)

"PlanIntel vs Precedent.ie: coverage compared" (/compare/precedent-ie) puts the two side by side with **live-generated PlanIntel numbers and dated quotes of Precedent's published figures** (read 19 Sep 2026). It distinguishes reasons-per-application vs reasons-as-individual-quotes, notes Precedent's 16,834 vs PlanIntel's 2,151, and explains why PlanIntel's grows on demand. That page is the template for the coverage-transparency table we should ship on our own site.

## Our angle vs PlanIntel

Zero commercial threat at €19/month — but it sets the **explainability floor** (verbatim verification, flagged uncertainty, dated counts) and the **pricing floor** (free search; €39 brief). Its explicit refusal to predict is public proof that *verifiable* outcome prediction is hard, which makes our documented holdout the moat. If we ever publish a model card, PlanIntel's honesty bar is the minimum to clear.

## Source pages

- Home: https://planintel.ie/ — how it reads records: /about — vs Precedent: /compare/precedent-ie
- Self-build guide: /can-i-build-a-house — AI chat: /chat — county pages: /ie/<county>…
