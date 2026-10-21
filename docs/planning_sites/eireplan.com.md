# Public text from eireplan.com

Collected: 2026-09-24T13:35:47.886572+00:00

Source: public HTML pages only. Navigation, forms and scripts are omitted. Check the original URLs before relying on claims.


---

# Page 1: EirePlan — the public record for sites in Ireland

Source URL: https://eireplan.com/

Skip to main content

D26B/0196/WEB

18 Greenfield Road, Mount Merrion, Dublin

LA DLR In Progress 2026

ED26/0024

42 Knockmeenagh Road, Clondalkin, D22

LA SDCC Refuse 2026

2660154

Griffinstown Kinnegad, Mullingar, Co. Westmeath

LA Westmeath In Progress 2026

2660202

Ballycullane Beg, Dungarvan, Co. Waterford

LA Waterford In Progress 2026

REF3626

Athgarvan, 41 Stillorgan Park, Blackrock, Dublin

LA DLR Refuse 2026

22646

Killarney, Co. Kerry

LA Kerry In Progress 2026

ED26/0022

16 Somerton View, Newcastle Road, Lucan, Dublin

LA SDCC Refuse 2026

SDZ25A/0031W

Dodsborough Cottages, Tandy's Lane, Adamstown, Lucan

LA SDCC Refuse 2025

LA Donegal LA Limerick LA Cork City LA Tipperary LA Mayo LA Waterford LA Kilkenny LA Sligo

## The public record for sites in Ireland.

Planning history, mapped ground context, services and transport, brought together around an address — with provenance for every result.

See how it works ↓

Everything you would want to know about a site is already public. It is just scattered across dozens of registers that were never built to talk to each other. We bring them together against one address, and show where every figure came from.

“

The planning data integrated seamlessly into our platform, and it’s become a core part of how we give sellers and buyers a clear view of a property.

Speed-Deed · in production since 2026

See the API they built on →

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

### Public records and mapped context,

resolved to one address.

Planning, ground, water, heritage, land and people. 35 source feeds, with source and vintage made clear.

© OpenStreetMap contributors

Case study

### St Stephen’s Green Shopping Centre

Thirteen applications since 2019. Seven granted, three refused, five carried to An Coimisiún Pleanála. The whole record, in one workspace.

Open the site

A real workspace, opened up. No account needed.

The agent

### Every site comes with a stack of paperwork.

Ask, and it does the reading.

It finds the applications that matter, opens the documents, and tells you what they say — and where it found it.

#### It reads the actual documents

One application can run to dozens of files. Ask why something was refused and it opens them, finds the passage, and gives it to you word for word with the page it came from.

#### It answers what a filter can't

What keeps getting refused around here? How long does this council really take? It works the question out, then shows you how it got there.

“What keeps getting refused on streets like this one?”

analytics_query

select refusal_ground, count (*) from decisions where authority = … group by 1

Read-only. It shows you the query it ran.

#### It already knows which site you mean

Open a site or an application and it is right there, working on that one file. No re-explaining where you are or pasting references back to it.

14 Oakley Road, Ranelagh

LA DCC 4 applications

Overview History Documents

Working on this site

Ask about this site…

Who uses it

Land and development teams Screening a pipeline of sites before bidding — what has been tried here, and what came back.

Estate and land agents Proving to a buyer what a site can carry, without waiting on a consultant's report.

Solicitors and conveyancers Checking the planning history behind a sale, with the decision notice attached.

Lenders and surveyors Security reviews that need the permission, the conditions and whether it was ever built.

Architects and self-builders Finding what was approved nearby, and the exact conditions that came with it.

Planning consultants Building and defending a case with the precedent and policy that support it, cited.

#### Planning & delivery

- Local authority planning registers

- Development plans & zoning

- Residential Zoned Land Tax maps

- Building control records

- Property Price Register

+ 3 related feeds

#### Ground & environment

- Geological Survey Ireland

- Environmental Protection Agency

- Urban wastewater capacity

+ 12 related feeds

#### Heritage & archaeology

- National Monuments Service

- National Inventory of Architectural Heritage

- Protected structures & conservation areas

+ 2 related feeds

#### Land & tenure

- Tailte Éireann cadastral parcels

#### People & place

- CSO Census 2022

- Pobal HP Deprivation Index

+ 2 related feeds

#### Access & transport

- National airfields & ports

+ 1 related feeds

Explore data provenance

For developers

### Already have a product?

Put the record inside it.

Everything on this page is a REST call away: search, decision detail, planning history around a point or a boundary, the policy library, and which authority a site falls in.

Read the docs Get an API key

One call, the whole site An eircode, an address or coordinates. Back comes every application on and around that site: references, decisions, dates, and the documents behind them.

Or skip to the finished report Ask the same endpoint for a PDF and hand your customer a complete planning-history report.

Keys are self-serve from the hub. Calls are metered against your plan’s credits.

cURL

1

2

3

4

5

6

7

8

# Every application on and around one site.

curl -G https://api.eireplan.ie/ext/v1/precedents/site-history \

-H "Authorization: Bearer $EIREPLAN_API_KEY" \

-d eircode= D06X285 \

-d radius_m= 250

# Same path ending in /report.pdf returns the finished PDF.

GET /ext/v1/precedents/site-history api.eireplan.ie

---

# Page 2: About EirePlan — the team behind Ireland's planning record

Source URL: https://eireplan.com/about

Skip to main content

About Eireplan

## Why Eireplan exists

Ireland's planning record is public, and it is kept in 31 separate council registers — each with its own search, its own fields and its own name for the same decision. A plain question about a site costs a morning and 31 browser tabs.

EirePlan is that record, assembled: every application from every planning authority in the State, normalised to one entry per site and joined to the national datasets that describe the ground underneath it.

### Why we built Eireplan

The idea came from preparing planning applications in Ireland, and from how much of that work went on re-finding things that were already public.

The registers do not disagree about the facts so much as about how to write them down. The same decision carries different wording depending on who issued it, one application type appears under several names across the 31 registers, and nothing joins an application to the site it sits on — so a place with a refusal, a redesign and an appeal reads as three unrelated entries.

The cost of that is measurable, but only once every register is in the same shape. Over August 2025 to July 2026 , 16.5 % of applications nationally were invalidated on completeness before anyone assessed them, and a decision took 71 days on average.

So that is what we built, and what we keep building: more than 370,000 applications from every planning authority in the State, 99.4 % of them placed on the map and joined to 33 national datasets. Figures as at 2026-08-19 .

### Our approach

Eireplan is built around a simple principle: software should support professional judgement, not replace it .

Planning decisions require nuance, local knowledge, and professional accountability. No tool should pretend otherwise.

We are a data company before we are a software company. The work is collecting the public record, reconciling 31 registers into one shape, joining it to the national datasets, and keeping every figure traceable to the body that published it. The interface is how you read it.

It is also why an absence is shown differently from an answer here. Where the record does not say, the page says it does not say, rather than closing the gap with something plausible.

#### What Eireplan deliberately does not do:

- · Make planning decisions or recommendations on strategy

- · Submit applications on behalf of users

- · Generate planning reports without professional review

- · Replace the need for qualified planning expertise

- · Act as a document store for your own drawings and consultant files — we read the documents the councils publish, not the ones you hold

### The team

Eireplan is developed by a team that combines planning experience with software engineering.

Our background includes direct involvement in Irish planning applications, from site assessments and policy research through to submission and decision tracking. We understand the operational realities of planning work, not just the theory.

We're building Eireplan because we believe planning professionals deserve tools that reflect the specificity of their work, rather than generic software adapted from other industries.

General access is open

EirePlan is available to planning teams across Ireland

### Our principles

The values that guide how we build and operate Eireplan.

#### Respect for professional judgement

Planning decisions belong to planners. Eireplan provides structure and information, the professional remains accountable.

#### Accuracy over speed

Correct policy references matter more than fast answers. We prioritise grounded, verifiable outputs.

#### Data confidentiality

Planning data is commercially sensitive. Projects are isolated by organisation, with no cross-client visibility.

#### Incremental improvement

We're not trying to disrupt planning. We're trying to make existing workflows more consistent and less error-prone.

#### Long-term trust

We're building for sustained professional use, not short-term adoption. Reliability and data responsibility come first.

#### Built for planning

Eireplan is designed specifically for Irish planning work, not adapted from generic project management or AI tools.

### Common questions

What the record covers, how current it is, and where it sits next to the official sources.

Where can I search planning applications across all of Ireland? EirePlan holds the registers of all 31 Irish planning authorities as one searchable record — more than 370,000 applications from 2016 onwards, 99.4% of them placed on a map, refreshed from the registers twice a week. Searching it does not require an account.

What does EirePlan do that a council's own planning register does not? A council register answers questions about that council, filed by application. EirePlan normalises all 31 registers into one entry per site, so a place that was refused, redesigned, resubmitted and appealed reads as one history rather than four unrelated entries, and it joins that history to 33 national datasets — zoning, heritage, environment, services and transport — resolved to the site rather than to the county it sits in.

How does EirePlan compare to MyPlan.ie? MyPlan.ie is the Department's national viewer and shows applications from the past ten years on a map; it is the official State source and the right place to go for that. EirePlan covers the same registers from 2016 onwards but differs in what it does with them: one record per site rather than per application, aggregate statistics per authority that nobody else publishes, the councils' own decision documents read and quoted with citations, and a free REST API over the whole record.

Is the planning data free to use? A free account gives you the national record to search, the map and policy layers, and the assistant. It is not a trial and it does not ask for a card. There is a free REST API over the same record, and aggregate figures may be reused with attribution to EirePlan provided the computation window is carried with them.

How current is the data, and can I check where it came from? The registers are collected twice a week and every figure on the site carries the window it was computed over and the body that published it. Over August 2025 to July 2026, 16.5% of applications nationally were invalidated on completeness before assessment and a decision took 71 days on average — both computed over the published registers, both traceable on the page that shows them.

General access

### Ready to see how Eireplan can support your practice?

Create your account and start using EirePlan with your team.

Get Access

---

# Page 3: Irish planning research and analysis — the EirePlan blog

Source URL: https://eireplan.com/blog

Skip to main content

## Irish planning research and analysis — the EirePlan blog

### Reports

Full-length research reports from EirePlan. Click a cover to download the PDF.

PDF

Report Apr 1, 2026

#### Evaluating the Feasibility of Using Planning Data to Monitor SDG Implementation in Ireland

Evidence from a twelve-month analysis of the Eireplan Precedents Database. Exploratory research report submitted to the SRIN 2026-2028 programme, mapping how planning application records can be repurposed as a measurement surface for Sustainable Development Goal implementation in Ireland.

report sdg precedents

Download PDF

### Featured Insights

Curated analysis and standout commentary from recent EirePlan publishing.

Featured May 19, 2026

#### Ireland is about to widen exempted development but the current Section 5 system can't even count itself

The Government has approved a major expansion of exempted development under the Planning and Development Act 2024 - modular back-garden homes up to 45 m², larger extensions, attic conversions, subdivision. Yet the Section 5 system that decides what is and isn't exempt today produces no clean national dataset. We map the legal baseline, the data gap, and what 31 local authorities actually publish.

section-5 exempted-development pda-2024

Read article

Featured Jan 20, 2026

#### Why We’re Building a Planning Knowledge Engine (Not Just Another AI Chatbot)

Eireplan is building a planning knowledge engine, not just another AI chatbot. Learn why context matters.

ai planning eireplan

Read article

Featured Jan 10, 2026

#### How the UK Uses AI to Cut Planning Validation Time (And What Ireland Can Learn)

UK councils are using AI to cut planning validation times. We explore the evidence and what Ireland can learn from their approach.

ai validation uk-planning

Read article

### All Articles

9 article s shown

May 19, 2026

#### Ireland is about to widen exempted development but the current Section 5 system can't even count itself

The Government has approved a major expansion of exempted development under the Planning and Development Act 2024 - modular back-garden homes up to 45 m², larger extensions, attic conversions, subdivision. Yet the Section 5 system that decides what is and isn't exempt today produces no clean national dataset. We map the legal baseline, the data gap, and what 31 local authorities actually publish.

section-5 exempted-development pda-2024

Read article

Apr 10, 2026

#### Ireland's Empty Buildings

In the middle of a housing crisis, Ireland has tens of thousands of empty buildings. We examine the scale, barriers, and what it would take to bring them back into use.

vacancy dereliction housing-crisis

Read article

Mar 24, 2026

#### What If Planners Had More Time?

When administrative work is handled by AI, planning professionals face a deceptively complex question: what do they choose to do next?

ai planning productivity

Read article

Mar 17, 2026

#### Beyond The Template

A commentary on how AI is removing entry-level busywork and why firms must reinvent junior training, mentorship, and talent development for Gen Z.

ai future-of-work gen-z

Read article

Feb 5, 2026

#### AI, Traceability, and the Reality of Planning Work in Ireland

As AI tools become more prevalent in planning, we explore the importance of traceability and the realities of planning work in Ireland.

AI digital-transformation Traceability

Read article

Feb 5, 2026

#### Explainable or Unusable: A Standard for AI in Planning

Explainable or Unusable: A Standard for AI in Planning

Across professional services, AI is being sold as faster, smarter, and more transformative than any tool that came before it. In planning, law,

AI digital-transformation Traceability

Read article

Feb 3, 2026

#### From Paper Registers to Planning Intelligence: What the US Gets Right (And What It Still Struggles With)

US planning systems are increasingly digital, yet fragmentation remains a challenge. We examine the US landscape and its lessons for Ireland.

us-planning digital-transformation gis

Read article

Jan 20, 2026

#### Why We’re Building a Planning Knowledge Engine (Not Just Another AI Chatbot)

Eireplan is building a planning knowledge engine, not just another AI chatbot. Learn why context matters.

ai planning eireplan

Read article

Jan 10, 2026

#### How the UK Uses AI to Cut Planning Validation Time (And What Ireland Can Learn)

UK councils are using AI to cut planning validation times. We explore the evidence and what Ireland can learn from their approach.

ai validation uk-planning

Read article

Table of contents

Filter by year

Filter by topic

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 4: AI, Traceability, and the Reality of Planning Work in Ireland - Eireplan

Source URL: https://eireplan.com/blog/post/AI_Planning_Traceability

Skip to main content

##### AI, Traceability, and the Reality of Planning Work in Ireland

As AI tools become more prevalent in planning, we explore the importance of traceability and the realities of planning work in Ireland.

This Blog Post was published on 5 February 2026

## When Intelligence Is Not the Problem

### AI, Traceability, and the Reality of Planning Work in Ireland

Anyone who has prepared a planning application in Ireland will recognise the pattern. The proposal itself may be straightforward, even well aligned with policy. The real work begins elsewhere: checking that every notice is dated correctly, that every plan uses the right colour code, that no obscure objective buried in a county development plan has been missed. Much of this effort is invisible in the final decision, yet it determines whether an application is even allowed to enter the system.

This is not a story of poor planning or irrational regulation. On the contrary, Irish planning professionals already operate within dense but defensible chains of logic. Decisions are grounded in statute, policy hierarchies, precedent and procedural safeguards. What is failing is not intelligence, human or artificial, but visibility. The system demands traceability, while many emerging AI tools offer abstraction without explanation.

That mismatch matters.

### A System Under Pressure, Not in Crisis

The Irish planning system is handling scale as well as complexity. In 2022, local authorities made 33,592 planning decisions from just over 32,300 valid applications, with similar volumes persisting year on year (Office of the Planning Regulator, 2024a). At the same time, statutory planning services cost approximately €161 million to operate in 2021, while fee income covered barely one sixth of that amount (Office of the Planning Regulator, 2024a). These are not signs of a lightly loaded system.

What is striking is where the pressure shows up. National invalidation rates rose from 15 percent in 2021 to 17.5 percent in 2022, meaning nearly one in six applications failed before substantive assessment (Office of the Planning Regulator, 2024a). In some authorities, the rate was far higher. Dublin City invalidated over a third of submissions in the same year, while other counties invalidated fewer than 3 percent.

These are not conceptual failures. County guidance makes clear that many invalidations stem from minor omissions: mislabelled maps, missing north points, incorrect notices, unsigned forms. The rules are explicit. The difficulty lies in navigating them consistently across authorities, formats and evolving guidance. Even local authorities acknowledge that officers may spend minutes per application simply scanning for completeness, multiplying into significant administrative burden at scale (Office of the Planning Regulator, 2024a).

### Complexity Without a Single Point of Truth

Planning professionals do not struggle because policy is unknowable. They struggle because it is fragmented.

Every application sits at the intersection of EU law, national policy, regional strategies, county development plans, local area plans and supplementary guidance. The Planning and Development Act 2024 alone runs to more than a thousand pages, consolidating and amending decades of legislation (Government of Ireland, 2024). Across 31 local authorities, those statutory foundations are layered with locally specific objectives and interpretations.

The information exists, but it is scattered. Different councils publish registers in different formats, operate on different IT systems and interpret similar requirements with subtle variation (Office of the Planning Regulator, 2024a). Consultants routinely cross reference multiple local authority archives, national policy documents and appeal decisions to answer what should be simple questions: What height applies here? Which assessments are required for this site? How have similar schemes been treated?

The result is a culture of defensive documentation. Reports are padded not because the issues are contentious, but because uncertainty about completeness carries unacceptable risk.

### Time Lost to Rework and Delay

Statutory timelines promise certainty. Most planning applications are meant to be decided within eight weeks. Appeals have formal objectives. In practice, delay is common and costly.

By mid 2024, nearly 1,000 planning appeals had exceeded the statutory objective period, with hundreds pending for more than a year and some for over two years (Office of the Planning Regulator, 2024b). In 2023, only 26 percent of appeals were resolved within the target timeframe, and the average decision time stretched to 48 weeks (Office of the Planning Regulator, 2024b).

These delays are not neutral. Research on renewable energy projects shows that planning and regulatory delay materially increases project costs and risks missing climate targets (Lynch, 2023). In the UK, preparation costs for major applications routinely run into hundreds of thousands of pounds before construction begins, magnifying the financial impact of rework and resubmission (Strategic Land Group, 2020; Home Builders Federation, 2023).

Yet only a small minority of Irish applications ever reach appeal. In 2022, appeals accounted for roughly 7.4 percent of decisions, and around 88 to 89 percent of applications nationally were granted (Office of the Planning Regulator, 2024a). The system is not paralysed by conflict. It is slowed by administration and uncertainty.

### Why Black Box AI Fails in Regulated Domains

Against this backdrop, it is tempting to see AI as a shortcut. Large language models can summarise documents, draft text and answer questions fluently. But fluency is not the same as fitness for purpose.

In planning, every conclusion must be defensible. Professionals are accountable not just for outcomes, but for the reasoning that leads to them. A tool that produces an answer without showing where it came from is not merely unhelpful. It is unusable.

This is where many AI tools falter. They optimise for speed and abstraction, when the domain demands traceability. Without visibility into sources, assumptions and logic, AI introduces risk rather than reducing it.

### Making Logic Chains Visible

A genuinely useful AI system must surface sources explicitly, integrate precedent in a structured way, and support early validation. The value lies not in automation for its own sake, but in reducing rework and uncertainty by making the system’s expectations legible.

### Intelligence as Infrastructure, Not Decision Maker

The most productive way to think about AI in planning is not as a decision maker, but as infrastructure. Its role is to organise, connect and expose information that already exists, allowing professionals to reason more efficiently within established frameworks.

### Conclusion

The core limitation of many AI tools in regulated domains is not intelligence, but opacity. Planning professionals do not need faster guesses. They need clearer logic chains.

Explainable AI is not an ethical aspiration. It is a practical necessity for accountability, trust and professional responsibility.

Share

### Read More

May 19, 2026

April 10, 2026

March 24, 2026

March 17, 2026

February 5, 2026

On this page

Share

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 5: Beyond The Template - Eireplan

Source URL: https://eireplan.com/blog/post/Beyond_The_Template

Skip to main content

##### Beyond The Template

A commentary on how AI is removing entry-level busywork and why firms must reinvent junior training, mentorship, and talent development for Gen Z.

This Blog Post was published on 17 March 2026

## Beyond The Template

#### Why AI Eliminating Entry-Level Busywork Might Be the Best Thing That Ever Happened to Junior Staff

A commentary on AI, Gen Z, and the reinvention of professional training

There is a conversation happening in offices and firms across every professional sector right now. It goes something like this: "We use AI for the repetitive stuff now." The tone is usually upbeat. Efficient. Progressive. What that sentence quietly glosses over, however, is that the "repetitive stuff" has historically been the entire job description of every graduate who walked through the door in their first two years of professional life.

AI's absorption of entry-level, process-driven work is not simply a workforce disruption story. It is also, if employers are brave enough to respond well, an overdue opportunity to reinvent how young professionals are actually trained. And it arrives at precisely the moment when Gen Z's disillusionment with traditional employment is already reshaping the labour market in ways that will be further accelerated by AI.

### The Lie We Told Graduates

Most planning, legal, financial, and consulting graduates are told, implicitly or explicitly, when they start work to put your head down, do the groundwork, learn the craft from the ground up, and the interesting stuff will come. What they actually receive is a keyboard, a library of old reports, and an instruction to use them as a template for the new one.

The copy-paste economy of junior work is not a secret. Reusing last year's environmental impact assessment structure for this year's site. Reformatting someone else's planning statement. Populating a spreadsheet that a manager will glance at for thirty seconds. The tasks are not without value in the abstract. They build familiarity with formats, processes, and industry language. But they provide almost none of the feedback, challenge, or meaning that transforms a graduate into a practitioner.

Many graduates leave those first years unable to answer a basic professional question: Am I any good at this? They have never been tested. They have only been processed.

"Gen Z workers consistently report that meaningful work, mentorship, and a sense of purpose matter more to them than any other workplace factor — yet the entry-level experience most firms offer provides almost none of these things."

### What the Research Actually Says About Gen Z at Work

Gen Z's relationship with traditional employment was already under strain before AI entered the picture. The data is consistent and striking.

Research consistently shows that Gen Z prioritises meaningful work, mentorship, and clear career progression above almost everything else when evaluating an employer. Large corporations have recognised this. Studies show that Gen Z respondents prefer working at large organisations over small ones because they are better positioned to offer structured career paths, mentoring programmes, and competitive development opportunities.

— Accenture Strategy Report on Gen Z Rising; multiple Gen Z workplace preference surveys, 2022–2024

Yet the majority of entry-level roles in small and medium-sized professional firms, the ones that have traditionally absorbed new graduates, offer none of this infrastructure. They offer volume. And volume, it turns out, is exactly what AI does better.

Approximately 50% of Gen Z aspires to start their own business, and survey after survey shows increasing disillusionment with the nine-to-five as a model. A rational response to an employment offer that fails to deliver what was promised.

— Multiple Gen Z entrepreneurship and career aspiration surveys, 2023–2024

The conditions were already there for a generational break with traditional employment pathways. AI is about to light a match.

### What the Anthropic Economic Index Tells Us About Young Workers Right Now

A landmark study published in March 2026 by researchers Maxim Massenkoff and Peter McCrory at Anthropic introduces a new measure of AI displacement risk: "observed exposure", that tracks not just what AI could theoretically do, but what it is actually doing in real professional settings.

The findings are sobering for anyone thinking carefully about workforce entry. The occupations with the highest current AI exposure (computer programmers (74.5% task coverage), customer service representatives (70.1%), data entry keyers (67.1%), and medical record specialists (66.7%)) are precisely the occupations that disproportionately absorb junior staff doing structured, repeatable work.

— Massenkoff & McCrory, "Labor Market Impacts of AI: A New Measure and Early Evidence," Anthropic, March 2026

More significantly, the study finds tentative but real evidence that hiring of young workers, specifically those aged 22 to 25, has already begun to slow in AI-exposed occupations. In the post-ChatGPT era, the study records an approximately 14% drop in the job-finding rate for young workers entering highly exposed roles compared to 2022 baselines.

— Massenkoff & McCrory, 2026, Figure 7

This finding echoes parallel research by Brynjolfsson, Chandar, and Chen (2025), which reports a 6–16% fall in employment in AI-exposed occupations among workers aged 22 to 25, attributing the decrease primarily to a slowdown in hiring rather than job losses among existing workers.

— Brynjolfsson et al., "Canaries in the Coal Mine? Six Facts About the Recent Employment Effects of Artificial Intelligence," Digital Economy, 2025

The canary in the coal mine, to borrow Brynjolfsson et al.'s evocative framing, is singing. The question is whether employers are listening... and if so, what they plan to do about it.

"The occupations most exposed to AI automation are, almost without exception, the ones that have historically served as the training ground for professional life. That is not a coincidence. It is a structural problem."

### The Gap Between Capability and Deployment — and Why It Matters

One of the most important findings in the Anthropic report is the gap between what AI can theoretically do and what it is currently doing in practice. Despite LLMs being theoretically capable of covering 90% of tasks in office and administrative occupations, actual observed coverage sits far below that ceiling, and the gap is narrowing.

— Massenkoff & McCrory, 2026, Figure 2

This means the displacement of entry-level work is not a future scenario. It is an ongoing, accelerating process. The tasks that graduates are currently being asked to do (reformatting documents, populating templates, producing first drafts of standardised reports) are being automated at pace. And yet the training models built around those tasks have not changed.

Firms that continue to onboard graduates as if AI does not exist are not preserving a valuable apprenticeship model. They are handing graduates a disappearing job description and calling it development.

### The Reinvention That Is Now Required

If the entry-level busywork is going, or has already largely gone, then the organisations that survive this transition well are the ones that ask a harder question: what does a junior professional actually need to learn, and how do we teach it without the scaffolding of repetitive tasks?

This is genuinely difficult. The volume model of junior training, whatever its flaws, did produce some real benefits: familiarity with document structures, exposure to a wide variety of project types, a slow-burn absorption of how a firm's work is organised. Replacing it requires intentionality. What might that look like?

Structured mentorship paired with AI review. Juniors work alongside AI tools to produce outputs, but are explicitly trained to critique, interrogate, and improve AI-generated work rather than simply submit it. This builds judgment rather than just output.

Early exposure to client interaction and problem framing. The tasks AI cannot easily replicate, such as understanding a client's actual concern, navigating ambiguity, building trust, can be introduced earlier when repetitive work is no longer consuming all of a junior's time.

Real feedback loops from day one. One of the most damaging features of traditional junior work is the absence of meaningful feedback. Did I do this well? What did the manager actually think? AI-assisted workflows can free up senior staff time for the kind of deliberate coaching that builds competent professionals faster.

Portfolios of judgment, not outputs. Rather than measuring a junior's first year by the number of reports filed, firms could measure the quality of decisions made, alternatives considered, and problems identified, skills that are both more valuable and more transferable than template-filling.

### The Brave Employers: Taking On Entry-Level Staff in the Age of AI

There will be an easy path and a hard one for employers over the next decade.

The easy path is to stop hiring juniors altogether. If AI can do the work, why pay a graduate to do it more slowly and with more mistakes? This logic is already being acted upon, as the hiring data suggests. It is short-sighted, but understandable.

The hard path is to hire juniors anyway, and to do the genuinely difficult work of reinventing how they are developed. This requires investment in mentorship infrastructure, willingness to redesign workflows, and a long-term view of what a firm needs to look like in ten years.

The employers who take the hard path will be building something that the firms who took the easy path will eventually need to buy back at a premium: a pipeline of professionals with genuine judgment, not just operational competence.

"The firms that take on entry-level staff in the age of AI are not being naive. They are making a long bet on human development at the precise moment everyone else has decided it is too complicated."

This matters especially for Gen Z. A generation that already approaches traditional employment with scepticism, that already leans toward entrepreneurship and autonomy, is not going to be retained by organisations that offer them a front-row seat to watching AI do their job. They will stay and thrive in organisations that treat their early years as a genuine investment in professional formation.

Research is already clear that small and medium-sized businesses are poorly positioned to meet this challenge. The infrastructure required, such as structured mentorship programmes, deliberate onboarding frameworks, meaningful feedback systems, is resource-intensive. This creates a structural advantage for larger organisations willing to invest, and a real risk that the gap between firms that develop talent well and those that do not will widen significantly.

— Multiple SMB workforce research reports, 2023–2024

### A Prediction

The Gen Z disillusionment with entry-level work that is already visible in the data will be significantly exacerbated by AI's absorption of the tasks that have defined those roles. The combination of a generation that already found junior work unrewarding and a technology that is now replacing the most automatable parts of it will accelerate departures from traditional employment pathways.

Firms that respond to this by quietly reducing graduate intake will not feel the consequences immediately. They will feel them in five to eight years, when the professionals who would have been their senior associates and directors either do not exist, have gone elsewhere, or have built their own practices.

The Anthropic Economic Index will continue to update. The gap between AI's theoretical capability and its observed workplace coverage will keep narrowing. The occupations being eroded are not mysterious. They are listed in plain sight, and they are the occupations that train the next generation of every profession that depends on knowledge work.

The question for every firm reading this is simple: are you going to reinvent how you develop people, or are you going to wait and see?

### Key Sources

- Massenkoff, M. & McCrory, P. (2026). Labor Market Impacts of AI: A New Measure and Early Evidence. Anthropic.

- Brynjolfsson, E., Chandar, B. & Chen, R. (2025). Canaries in the Coal Mine? Six Facts About the Recent Employment Effects of Artificial Intelligence. Digital Economy.

- Accenture Strategy. Gen Z Rising: The Next Generation of Talent. Accenture.

- Multiple Gen Z workplace preference and entrepreneurship surveys (2022–2024).

- SMB workforce research reports on Gen Z hiring infrastructure gaps (2023–2024).

Share

### Read More

May 19, 2026

April 10, 2026

March 24, 2026

February 5, 2026

On this page

Share

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 6: EirePlan — the public record for sites in Ireland

Source URL: https://eireplan.com/blog/post/Eireplan_SDG_Planning_Data_SRIN_2026_2028

Skip to main content

Unsupported article type: report

---

# Page 7: Explainable or Unusable: A Standard for AI in Planning - Eireplan

Source URL: https://eireplan.com/blog/post/Explainable_AI_in_Planning

Skip to main content

##### Explainable or Unusable: A Standard for AI in Planning

Explainable or Unusable: A Standard for AI in Planning

Across professional services, AI is being sold as faster, smarter, and more transformative than any tool that came before it. In planning, law,

This Blog Post was published on 5 February 2026

## Explainable or Unusable: A Standard for AI in Planning

Across professional services, AI is being sold as faster, smarter, and more transformative than any tool that came before it. In planning, law, regulation, and policy, the promise is familiar: reduce workload, accelerate decisions, surface insights hidden in complexity. And yet, for many practitioners, the lived experience of AI tools is far less convincing.

The primary failure is not that these systems are inaccurate. Nor that they lack ambition, computational power, or technical sophistication. The real failure is simpler and more fundamental: most AI tools cannot explain themselves in a way that aligns with professional accountability.

This is not a critique of planning systems, planning authorities, or professional practice. Planning already operates under clear standards of reasoning, documentation, and defensibility. The critique is of how AI is often applied to such systems: imported wholesale from consumer or experimental contexts, without adapting to the requirements of professional use.

If AI cannot show its workings, it cannot function as decision support. At best, it becomes an interesting side tool. At worst, it introduces new risks into workflows that depend on traceability and trust.

### Impressive outputs are not the same as usable tools

Modern AI systems are exceptionally good at producing outputs that look authoritative. They generate fluent text, confident summaries, and persuasive conclusions. In a demo, this can be compelling. In a professional workflow, it is often useless.

A planning professional does not need an answer that merely sounds correct. They need to know:

- where that answer came from

- what information was considered

- what was excluded or abstracted away

- how the conclusion could be defended if challenged

An AI tool that produces a polished paragraph without exposing its sources or reasoning is closer to a presentation engine than a professional instrument. It may save seconds in drafting, but it costs minutes, or hours, when the user has to reverse engineer the logic to check whether it can be relied upon.

In practice, many practitioners learn quickly that they cannot cite an AI output, cannot stand over it in correspondence, and cannot use it as evidence in a report. The result is predictable: the tool is sidelined, regardless of how impressive it looked on launch day.

### Why “trust the model” is not acceptable

In consumer contexts, “trust the model” is often treated as an acceptable abstraction. In planning, law, or regulation, it is not.

Planning decisions must be defensible. They are subject to appeal, judicial review, and public scrutiny. Even preparatory work, such as feasibility assessments, planning statements, and screening analyses, exists within an accountability chain. The professional signing off on a document remains responsible for its content, regardless of what software assisted in its preparation.

An AI system that asks users to accept its outputs on faith breaks that chain. It asks professionals to outsource judgement without outsourcing responsibility, an impossible bargain.

This is why black box AI creates risk rather than reducing it. If a conclusion cannot be explained, it cannot be defended. If it cannot be defended, it cannot be safely used.

In many cases, practitioners respond rationally. They treat AI suggestions as informal prompts, not as inputs they can rely on. The system becomes a brainstorming tool, not a decision support system. Its value collapses accordingly.

### The hidden cost of black box AI

Proponents of opaque models often argue that explainability is technically difficult, or that requiring it would limit model performance. In professional contexts, this misses the point.

The cost of opacity is not theoretical. It shows up as:

- duplicated work, as users manually verify AI outputs

- increased cognitive load, as professionals reconcile AI suggestions with known policy constraints

- institutional resistance, as organisations decline to integrate tools they cannot audit

- reputational risk, when outputs cannot be traced back to authoritative sources

In planning, these costs compound existing pressures. The system already involves complex legislation, layered policy hierarchies, and extensive documentation. AI that obscures its reasoning does not simplify this complexity. It adds another layer on top of it.

### What explainability actually means in practice

Explainability is often discussed in abstract terms: transparency, interpretability, ethical AI. In professional workflows, it is far more concrete.

At a minimum, usable AI systems must be able to show:

- Which documents were used

- Which policies or sources were abstracted

- How conclusions were derived

This does not require exposing model weights or internal embeddings. It requires exposing the logic flow: how inputs were filtered, compared, and synthesised into an output.

This mirrors how professionals already work. Planning reports do not merely state conclusions. They set out policy context, assess compliance, weigh considerations, and explain judgement calls. An AI system that cannot do the same is misaligned with the domain it claims to support.

### Explainability is not optional in regulated environments

There is a tendency to frame explainability as a “nice to have”, something to add once models are more mature. In regulated environments, this framing is backwards.

Explainability is the baseline requirement. Accuracy without traceability is insufficient. Speed without defensibility is irrelevant.

Crucially, this is not a technical limitation. It is a design choice.

Many AI products are built by optimising for demo impact: fast answers, confident language, minimal friction. Professional tools require a different optimisation target: clarity, auditability, and alignment with existing accountability structures.

Choosing explainability means accepting that some outputs will be more structured, more conditional, and less rhetorically polished. That is not a weakness. It is what makes them usable.

### Planning as a revealing case study

Planning is a particularly clear example because its standards are explicit. Decisions must be reasoned. Evidence must be cited. Judgement must be explainable to third parties, whether inspectors, courts, clients, or the public.

Planners already navigate complex information environments. They are accustomed to balancing policy objectives, interpreting precedent, and documenting rationale. The problem is not complexity. It is opacity.

AI, when applied well, should clarify this complexity: surface relevant policies, highlight constraints, and organise information in ways that support professional judgement. When applied poorly, it obscures the very reasoning it claims to accelerate.

This is why many planning professionals are sceptical of AI hype but open to practical tools. They do not need an oracle. They need a colleague who does the legwork and shows how it got there.

### A standard worth insisting on

If AI is to play a meaningful role in planning and other regulated fields, a clear standard should apply: explainable or unusable.

This is not a call to slow innovation or constrain ambition. It is a call to align AI systems with the realities of professional work. Systems that expose their reasoning will be trusted, adopted, and improved. Systems that do not will remain peripheral, regardless of how advanced they appear.

Useful AI behaves like a good colleague. It shows its working. It cites its sources. It makes its reasoning open to challenge, and therefore fit for use in accountable decision making.

Anything less is not decision support. It is just output.

Share

### Read More

May 19, 2026

April 10, 2026

March 24, 2026

March 17, 2026

February 5, 2026

On this page

Share

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 8: From Paper Registers to Planning Intelligence: What the US Gets Right (And What It Still Struggles With) - Eireplan

Source URL: https://eireplan.com/blog/post/From_Paper_Registers_To_Planning_Intelligence_What_The_US_Gets_Right

Skip to main content

##### From Paper Registers to Planning Intelligence: What the US Gets Right (And What It Still Struggles With)

US planning systems are increasingly digital, yet fragmentation remains a challenge. We examine the US landscape and its lessons for Ireland.

This Blog Post was published on 3 February 2026

Across the United States, planning systems are firmly in the midst of a digital transition. Most major jurisdictions now offer online access to planning registers, digital submission of applications, and publicly accessible zoning maps. Yet the evidence from US cities shows that digitisation, while widespread, has delivered uneven results. Systems are often fragmented, siloed, and limited to document access rather than analytical or decision-support capabilities. In only a small number of cases does digitisation begin to move toward what might reasonably be described as “planning intelligence”.

This article examines how digital planning operates in practice across the US, drawing on concrete examples from cities, counties, and regional authorities. It distinguishes between access-oriented digitisation and more integrated or intelligent systems, and considers what lessons this experience offers to Ireland and other jurisdictions with similarly complex planning frameworks.
Digital vs. Intelligent Plannin…

### The structure of the US planning system

Any assessment of US planning technology must begin with the structure of the planning system itself. Planning authority in the United States is highly decentralised. There is no national planning register, no unified data standard, and no mandated software platform. Instead, planning is administered at multiple levels: municipal, county, and in some cases regional authorities, each with discretion over processes and tools.

This institutional structure has direct technological consequences. Each jurisdiction selects its own software stack or vendors, often incrementally and department by department. Planning, zoning, building permits, environmental review, and inspections are frequently managed by different departments using different systems. Even within a single city, land-use approvals and building permits are often handled on entirely separate platforms, with limited real-time data exchange.

As a result, the US planning landscape is characterised by variability. Large cities such as New York, Los Angeles, and San Francisco have invested heavily in digital portals and open data tools. Smaller cities and towns may still rely on paper-based workflows or basic online forms. Regional bodies such as the Tahoe Regional Planning Agency operate under different constraints again, balancing cross-jurisdictional coordination with limited resources.

The research makes clear that this fragmentation is structural rather than incidental. It reflects governance arrangements, procurement practices, and the absence of national standards for planning data or digital workflows.
Digital vs. Intelligent Plannin…

### Where digitisation has succeeded

Despite these constraints, digitisation has delivered real and measurable benefits in many US jurisdictions, particularly in terms of transparency, accessibility, and procedural continuity.

New York City provides a strong example. Its Zoning Application Portal allows the public to search and review all active land-use applications, including drawings, environmental reports, and supporting documentation. Combined with the ZoLa interactive zoning map and downloadable GIS datasets, this represents a substantial improvement over paper-based registers and in-person file inspection. Similar advances are visible in Los Angeles County’s extensive public GIS portals, which allow users to explore zoning, land-use designations, and planning activity spatially.
Digital vs. Intelligent Plannin…

San Francisco’s Property Information Map integrates parcel data, zoning controls, permits, and planning approvals into a single public-facing interface. Applicants can submit and track permits online, and the public can interrogate planning data without engaging directly with city staff. In Atlantic City, the shift from entirely paper-based zoning permits to a unified digital platform has reduced processing times, improved inter-departmental visibility, and enabled remote working during the pandemic.

Across these cases, digitisation has succeeded most clearly where the goal is access: making information visible, searchable, and retrievable. Online submission and payment have reduced administrative friction. Digital registers have improved transparency. GIS tools have made spatial constraints legible to a wider audience.

These gains are not trivial. They change who can participate in planning processes, reduce reliance on physical offices, and lower barriers to information. The research consistently shows that moving from paper to digital records alone can shorten timelines and reduce lost or incomplete applications.
Digital vs. Intelligent Plannin…

### Where fragmentation persists

At the same time, the research documents persistent fragmentation beneath the surface of many “digital” systems. Chicago provides a particularly stark example. Applicants are required to navigate multiple online portals, Hansen, ProjectDox, and additional systems, none of which are fully synchronised. Comments may appear in one system but not another, requiring users to manually cross-check platforms. Some steps still revert to paper, such as mailing printed plans that were originally submitted digitally.
Digital vs. Intelligent Plannin…

This pattern is not unique. New York City’s planning and building permit systems operate separately, with limited real-time integration. Los Angeles’s BuildLA portal provides a unified front-end but connects to distinct back-end systems operated by different departments. San Francisco historically maintained separate databases for planning approvals and building permits, requiring custom integration or manual data transfer.

Fragmentation has concrete consequences. Applicants duplicate data entry. Staff act as intermediaries between systems rather than analysts. Errors and delays emerge not because information is unavailable, but because it is stored in incompatible or disconnected formats. In smaller jurisdictions, fragmentation can be even more pronounced, with legacy software or manual processes persisting alongside newer tools.

The research highlights that fragmentation is often the result of incremental digitisation: replacing paper with digital forms without rethinking workflows or data models. Digitisation, in these cases, reproduces existing silos rather than dissolving them.
Digital vs. Intelligent Plannin…

### Why digitisation alone does not create intelligence

A central finding across all cases is that digitisation does not, by itself, produce planning intelligence. Most systems present information but do not interpret it. They rely on planners, applicants, and the public to read, synthesise, and apply complex documents manually.

Zoning maps show designations but do not calculate development capacity. Planning registers host environmental impact statements but do not summarise key issues or flag inconsistencies. Online forms accept submissions but rarely assess their substantive compliance with policy or regulation.

This distinction becomes clear when comparing standard digital portals with emerging AI-assisted tools. In most cities, planners still spend significant time checking applications for completeness, identifying missing documents, or interpreting public submissions. These tasks are labour-intensive precisely because digital systems stop at storage and display.

The research explicitly notes that digitising a flawed or complex process can result in a flawed digital process. Chicago’s hybrid paper–digital workflows illustrate this clearly. Without integration or automation, digitisation can shift burdens rather than eliminate them.
Digital vs. Intelligent Plannin…

### Emerging trends toward integrated planning tools

While still limited in scope, several jurisdictions are beginning to experiment with tools that move beyond basic digitisation toward integrated or intelligent systems.

In California, cities such as Los Angeles, Lancaster, and San Jose have piloted AI-powered permit pre-check tools. These systems automatically assess uploaded plans against encoded zoning and building rules, flagging errors or omissions before human review. Early evidence suggests that these tools can significantly reduce incomplete applications and shorten approval timelines, particularly for standardised case types such as post-disaster rebuilding or accessory dwelling units.
Digital vs. Intelligent Plannin…

The Tahoe Regional Planning Agency has adopted AI to check applications for completeness and accuracy at intake, with longer-term ambitions to support scenario modelling and regional planning analysis. This represents one of the clearest examples in the research of intelligence being applied not just to process efficiency but to policy exploration.

Sandy Springs, Georgia illustrates a different trajectory: embedding AI across planning operations, from transcription of meetings to analysis of public consultation feedback. Here, intelligence is applied to qualitative data, helping planners identify recurring themes and concerns that would be difficult to synthesise manually at scale.

These examples share several characteristics. Intelligence is used to augment, not replace, human decision-making. Tools focus first on routine, high-volume tasks. Deployment is incremental and often framed as pilot programmes. Importantly, these cases remain exceptions rather than the norm across the US.
Digital vs. Intelligent Plannin…

### Lessons for Ireland

Several lessons emerge from the US experience that are directly relevant to Ireland and comparable jurisdictions.

First, digitisation delivers clear benefits but does not automatically resolve structural inefficiencies. Without integration, digital planning systems risk reproducing departmental silos and manual coordination burdens.

Second, transparency and intelligence are distinct goals. Making planning information accessible is necessary but insufficient if users must still interpret large volumes of complex material unaided.

Third, the absence of shared standards is a critical constraint. US cities repeatedly reinvent similar systems, limiting interoperability and comparative analysis. This fragmentation makes it harder to build higher-order tools that operate across jurisdictions.

Fourth, early evidence suggests that targeted intelligence, particularly in validation, compliance checking, and summarisation, can yield disproportionate benefits. These gains are most apparent where application volumes are high and requirements are standardised.

Finally, the US cases caution against assuming that AI adoption is inevitable or uniform. Progress is uneven, data on outcomes remains limited, and many tools are confined to pilots or narrow use cases. Gaps in evaluation and long-term governance remain evident.

For Ireland, the implication is not that US systems should be replicated, but that their experience clarifies the difference between being digital and being intelligent. Digitisation is a foundation. Intelligence requires deliberate design, integration, and institutional alignment.

The US planning system demonstrates both the possibilities and the limits of digitisation. It shows how far access and transparency can be improved, but also how easily digital tools can stall short of meaningful intelligence. For jurisdictions grappling with rising complexity and constrained resources, the lesson is clear: the next phase of planning reform is not about putting more documents online, but about enabling systems to interpret, connect, and support decisions in ways that paper, and PDFs, never could.

Share

### Read More

May 19, 2026

April 10, 2026

March 24, 2026

March 17, 2026

February 5, 2026

On this page

Share

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 9: How the UK Uses AI to Cut Planning Validation Time (And What Ireland Can Learn) - Eireplan

Source URL: https://eireplan.com/blog/post/How_The_UK_Uses_AI_To_Cut_Planning_Validation_Time

Skip to main content

##### How the UK Uses AI to Cut Planning Validation Time (And What Ireland Can Learn)

UK councils are using AI to cut planning validation times. We explore the evidence and what Ireland can learn from their approach.

This Blog Post was published on 10 January 2026

## Why validation is a bottleneck in planning systems

Planning validation is a procedural step, but its effects are systemic. Before any application can be assessed on planning merits, it must first be checked for completeness and compliance with statutory requirements. This includes verifying that all mandatory forms are completed, the correct plans are submitted, fees are accurate, and location- and policy-specific requirements are met.

Research undertaken in the UK shows that this stage absorbs a disproportionate amount of professional time relative to its complexity. Analysis led by the Alan Turing Institute found that manual validation typically takes between 30 and 60 minutes per application. At a national scale, this equates to approximately 250,000 hours of local authority staff time each year spent on validation alone .

The same research highlights that invalid applications are not an edge case but a structural feature of the system. Over one-third of planning applications in England are initially submitted as invalid. Importantly, this is not due to complex planning judgement, but to relatively mundane errors: incomplete forms, missing plans, incorrect fees, or omissions such as north arrows on drawings. A collaborative pilot study led by Agile Datum demonstrated that around 80% of invalid applications could be traced back to just twelve recurring error types .

The operational consequence is a feedback loop of delay. Applicants often wait weeks for validation, only to be told that a minor omission requires resubmission. Officers must then re-check the amended application, further extending timelines and increasing workload. Validation, in effect, becomes a bottleneck that constrains the entire planning pipeline.

### What the UK research shows about AI-assisted validation

UK research and pilots over the past five years have focused narrowly on whether this bottleneck can be reduced through targeted automation. The emphasis has not been on replacing planners, but on supporting routine checks that are rule-based and repetitive.

Early evidence comes from local authority pilots. In 2019, the London Borough of Redbridge worked with Agile Datum on one of the first AI-assisted validation trials. The council reported that up to 80% of validation tasks could be automated. Average validation turnaround fell from approximately three weeks to 24 hours, and officer time savings were estimated at around 60 minutes per application, equating to roughly £250,000 in annual staff cost savings .

More recent pilots have reinforced these findings. In 2024, Enfield Council trialled an AI-driven “Planning Insights” tool focused on completeness checks and information gathering. According to reported pilot results, the system achieved 100% accuracy in retrieving site-specific constraints such as Article 4 directions and planning history. Tasks that previously took several hours were reduced to 20–45 seconds, allowing officers to redirect attention to more complex elements of casework .

At a national level, the UK government has also invested in document processing. In 2025, trials of the “Extract” tool, developed with Google DeepMind, were undertaken across three councils, including Hillingdon and Exeter. Extract digitised and classified legacy planning documents in approximately three minutes per file, compared to one to two hours of manual effort. The government has stated an intention to roll this tool out across English planning authorities by 2026, with the stated aim of significantly reducing the time spent on validation checks .

Taken together, these initiatives show that AI is being used in the UK to address a specific and well-defined problem: identifying missing, inconsistent or incorrect information at the point of submission, and extracting structured data from unstructured documents.

### How human oversight is preserved in UK pilots

A consistent feature across UK pilots is the explicit preservation of human oversight and accountability. None of the documented systems make autonomous validation decisions in isolation.

This is most clearly articulated in the 2025 pilot at Leeds City Council , which introduced an AI-assisted workspace known as “Xylo Core”. The system uses large language models to analyse application documents, flag potential issues, suggest relevant policy references, and draft correspondence. However, every AI-generated output must be reviewed by a planning officer. Officers retain full authority to accept, modify or reject the AI’s suggestions, and no decision is made without human sign-off. An audit log records both AI outputs and human decisions, ensuring traceability and transparency .

This approach aligns with national governance guidance. In 2024, the Planning Inspectorate issued guidance stating that if AI is used to draft or alter content in planning submissions or appeals, this must be disclosed. Crucially, responsibility for factual accuracy remains with the human submitter, who must affirm that the content is lawful and accurate. AI assistance, under this framework, does not dilute accountability; it reinforces it through explicit attribution .

Professional commentary reinforces this stance. Planning bodies and practitioners consistently stress that planning is a discretionary system requiring contextual judgement, ethical consideration and democratic accountability. AI tools are therefore framed as decision-support mechanisms rather than decision-makers, with human planners retaining responsibility for interpretation and outcomes .

### What has not been automated and why

Equally instructive is what UK pilots have deliberately chosen not to automate. None of the documented systems attempt to replace professional judgement on matters such as design quality, policy balance, community impact or material considerations. These aspects of planning involve subjective evaluation and value-based trade-offs that cannot be reduced to checklist logic.

Even within validation, automation is scoped carefully. AI systems focus on detecting absence, inconsistency or mismatch, such as whether a required plan is missing or whether the written description aligns with submitted drawings. They do not determine whether an application should be deemed acceptable in planning terms.

The research also highlights evidence gaps. Many pilots remain time-limited or geographically specific, and long-term performance data has not yet been widely published in peer-reviewed form. Adoption across the UK is uneven: some councils report extensive experimentation, while others have confirmed that they are not using any AI tools in planning workflows. As a result, there is limited national-level data on error rates, bias, or unintended consequences of AI-assisted validation .

This caution reflects an understanding that premature automation of discretionary functions could undermine trust in the planning system. The UK experience suggests that restraint has been a deliberate design choice rather than a technical limitation.

### Evidence-based lessons for Ireland

For Irish planners and policymakers, the UK evidence offers lessons, but not a template to be copied wholesale.

First, the research shows that validation is a structurally inefficient stage that lends itself to targeted automation. The types of errors identified in UK applications, missing documents, incomplete forms, incorrect fees, are not unique to that system. Where such errors are repetitive and rule-based, AI-assisted checks can reduce officer workload without encroaching on professional judgement.

Second, the UK experience demonstrates that human-in-the-loop design is not an optional safeguard but a foundational requirement. Systems that preserve officer control, require review of AI outputs, and maintain audit trails are more likely to align with planning law, professional ethics and public accountability.

Third, the evidence cautions against overextension. UK pilots have succeeded precisely because they focus on narrow, well-defined tasks. There is no empirical support, at present, for automating evaluative planning judgement, and UK institutions have been explicit about the limits of AI in this regard.

Finally, the research underscores the importance of transparency and governance. Clear disclosure of AI use, explicit retention of human responsibility, and ongoing evaluation are central to maintaining trust. The absence of comprehensive long-term data also suggests that any Irish exploration of similar tools would need to proceed incrementally, with evaluation embedded from the outset.

In sum, the UK experience does not suggest that AI will “fix” planning systems. It does, however, provide concrete evidence that carefully scoped, human-supervised tools can reduce avoidable delay at the validation stage. For Ireland, the lesson is not about technological ambition, but about disciplined application: using AI where the evidence supports it, and resisting it where professional judgement must remain paramount.

Share

### Read More

May 19, 2026

April 10, 2026

March 24, 2026

March 17, 2026

February 5, 2026

On this page

Share

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 10: Ireland is about to widen exempted development but the current Section 5 system can't even count itself - Eireplan

Source URL: https://eireplan.com/blog/post/Ireland_Widens_Exempted_Development_Section_5_Cant_Count

Skip to main content

##### Ireland is about to widen exempted development but the current Section 5 system can't even count itself

The Government has approved a major expansion of exempted development under the Planning and Development Act 2024 - modular back-garden homes up to 45 m², larger extensions, attic conversions, subdivision. Yet the Section 5 system that decides what is and isn't exempt today produces no clean national dataset. We map the legal baseline, the data gap, and what 31 local authorities actually publish.

This Blog Post was published on 19 May 2026

## Ireland is about to widen exempted development but the current Section 5 system can't even count itself

### TL;DR

- The Government has approved, and intends to lay under the Planning and Development Act 2024, regulations that significantly expand exempted development (modular back-garden homes up to 45 m², larger extensions, attic conversions including rooflights, subdivision and STL reversion). Positive resolutions by both Houses of the Oireachtas are required before signing. The existing Section 5 declaration system cannot reliably tell us how many such decisions Ireland already makes each year.

- Across the 31 local authorities, Section 5 publication is fragmented and inconsistently labelled. A clear discrete, discoverable Section 5 register exists at SDCC, Cork City, Cork County, Meath, Kildare, Waterford, Longford, Donegal and Tipperary. At several other authorities Section 5 declarations are merged into the main planning register without a distinct prefix, and at others no separate searchable register was located in our spot survey.

- Without a clean baseline, neither Government, nor the OPR, nor planning lawyers, nor automated decision-support tools can empirically measure the impact of the 2026 expansion, and judicial review exposure (253 new JRs against An Coimisiún Pleanála in the 18 months to June 2025, broken down by Fine Gael TD Colm Burke as 147 in 2024 and 106 in H1 2025) makes this data gap a live operational risk.

### Key Findings

- The 2026 expansion is real, advanced and contested. On 21 April 2026, Cabinet approved a memo from Minister for Housing James Browne TD and Minister of State for Planning John Cummins TD providing for planning exemption of modular back-garden units up to 45 m², extensions up to 45 m² (up from 40 m²), subdivision, attic conversions including rooflights, front- and rear-garden bicycle and bin storage, and Rent-a-Room treatment of the new modular units. Regulations are to be laid under the Planning and Development Act 2024 and require positive resolutions by both Houses of the Oireachtas before signature.

- The legal architecture is mid-transition. PDA 2024 (signed 17 October 2024) is being commenced in phases through SI orders (S.I. No. 662 of 2024, then a sequence of five Commencement Orders made in 2025, culminating in S.I. No. 633 of 2025 on 31 December 2025); An Bord Pleanála was replaced by An Coimisiún Pleanála on 18 June 2025 under Part 17 of the Act, brought into effect by S.I. No. 256 of 2025; exempted development under PDA 2024 will be defined entirely in regulations rather than on the face of the Act.

- The Section 5 mechanism is substantively unchanged for now. An €80 declaration is sought from the planning authority (4-week decision target); a refused or contested declaration may be referred to An Coimisiún Pleanála (formerly An Bord Pleanála) on payment of a fee (€210); documents must be displayed online for at least 8 weeks under s.5(7B) PDA 2000. The replacement procedure in section 10 of PDA 2024 narrows applicant standing to a "relevant person" (owner; eligible maritime applicant under s.85(2); occupier with owner's consent; another person with owner's consent; qualifying environmental NGO meeting five criteria; prescribed person) or a statutory undertaker.

- The published national data is fragmentary. An Coimisiún Pleanála's annual reports do not isolate Section 5 referrals. The 2021 and 2022 Appendices report 118 and 105 "Referrals" received respectively, but the figure is folded back into a generic "Other Case Types" line (944 received and 887 disposed in 2023; 463 received and 606 disposed in 2024, both confirmed from the 2024 Annual Report). There is no national, time-series count of Section 5 outcomes.

- 31 LA practice varies enormously. SDCC publishes every Section 5 declaration on its planning portal using an "ED…" prefix (the OPR's August 2024 review confirms the website meets s.5(7B) by holding declarations beyond the eight-week minimum). Cork City uses "R…-yy"; Cork County uses "D…yy"; Meath uses hybrid prefixes "RS/LS/TS/PS" (format confirmed; mapping to municipal districts not explicitly stated by the council); Kildare uses "ED 1234"; Donegal and Tipperary each publish a dedicated Section 5 page; DCC's online presentation conflates exempted-development files into the standard planning register without a distinct prefix; for several other LAs no discrete discoverable Section 5 register was located in our spot survey.

- The political and professional reaction is sharp. Labour leader Ivana Bacik called the units "shed-sits"; Labour housing spokesperson Conor Sheehan TD warned of "a shadow rental market with no protections for tenants"; Social Democrats leader Holly Cairns TD said the proposal risked throwing renters "to the wolves" and amounted to "a return to tenement conditions"; the Irish Planning Institute, while not opposing the principle, has accused Government of "tinkering" with planning regulations and called for the draft guidelines to be published.

- The data-quality problem matters for JR and enforcement. Fine Gael TD Colm Burke obtained figures showing 253 JRs against An Coimisiún Pleanála in the 18 months to June 2025 (147 commencing in 2024, 106 in the first six months of 2025), versus a prior four-year average that, per Burke, "was less than 100 per annum, approximately eight per month". The Irish Times (1 December 2025) reported legal costs to be capped at "just under €41,000 for a standard case up to the end of a first instance hearing in the High Court", with €53,350 for complex and €65,800 for very complex JRs. Poor classification of Section 5 outcomes amplifies this exposure.

### Details

#### 1. The statutory and regulatory spine of Section 5

Section 5 of the Planning and Development Act 2000 (No. 30 of 2000) provides that any person may, on payment of the prescribed fee, request in writing from the relevant planning authority a declaration as to whether a particular development is or is not development, or is or is not exempted development. The planning authority must issue the declaration within four weeks (subject to extensions where further information is sought); a person dissatisfied may, within four weeks of the declaration, refer the question to An Coimisiún Pleanála (formerly An Bord Pleanála) for review under s.5(3) PDA 2000. The planning authority itself may refer (s.5(4)). Subsection 5(7B), inserted by later amendment, requires the documents to be placed on the authority's or the Board's website for a minimum period of eight weeks from the date of the issue of the declaration.

The class catalogue of exempted development sits in Schedule 2 of the Planning and Development Regulations 2001 (S.I. No. 600 of 2001): Part 1 — Exempted Development (General); Part 2 — Exempted Development (Advertisements); Part 3 — Exempted Development (Rural areas); Part 4 — Classes of Use (change-of-use exemptions). Conditions and limitations for each class sit in column 2 of the relevant Part rather than in a separate Part. Article 9, headed "Restrictions on exemption", lists twelve specific de-exempting circumstances under Article 9(1)(a) (contravention of, or inconsistency with a use specified in, a planning permission; formation/widening of access to a road with carriageway over 4 m; traffic hazard; building over the building line; works under a public road; interference with landscape/views of special amenity value; archaeological, geological, historical, scientific or ecological interference; works to an unauthorised structure or unauthorised use; demolition that would preclude an existing use objective; fencing/enclosure of land in habitual public recreational use; obstruction of a public right of way; ACA exterior works that would materially affect the area's character), plus restrictions for Special Amenity Area Orders (9(1)(b)), EIA-required development (9(1)(c)), and major-accident-hazard establishments (9(1)(d)). Protected-structure restrictions sit separately in section 57 PDA 2000 and Article 6(2)(b)(iii) of the Regulations.

The chronology of subsequent amendments is dense. Material instruments include:

- S.I. No. 83/2007 — first wave of post-2000 adjustments to the 2001 Regulations.

- S.I. No. 235/2008 — broader exemption recalibration.

- S.I. No. 599/2014 — short-term letting adjustments.

- S.I. No. 30/2018 — vacant commercial-to-residential change-of-use exemption (Article 10(6) of the 2001 Regulations), Rebuilding Ireland-driven.

- S.I. No. 235/2019 — Planning and Development Act 2000 (Exempted Development) (No. 2) Regulations 2019 (operational 1 July 2019), introducing the rent-pressure-zone short-term letting regime alongside s.38 of the Residential Tenancies (Amendment) Act 2019.

- S.I. No. 75/2022 — extended the 2018 vacant commercial-to-residential exemption to 31 December 2025 and added Class 12 (former public houses).

- S.I. No. 492/2022 — Planning and Development (Solar Safeguarding Zone) Regulations 2022, fixing 43 Solar Safeguarding Zones.

- S.I. No. 493/2022 — Planning and Development Act 2000 (Exempted Development) (No. 3) Regulations 2022, removing the 12 m²/50% roof cap on rooftop domestic solar, with effect 5 October 2022.

- S.I. No. 376/2023 — Planning and Development (Exempted Development) (No. 4) Regulations 2023, change-of-use exemptions for International Protection accommodation.

- 2025 Regulations — Planning and Development (Exempted Development (Act of 2000)) Regulations 2025 (agriculture: stand-alone slurry storage up to 1,000 m³ per structure exempt subject to a 1,500 m³ farm aggregate; animal housing increased 200→300 m² and 300→450 m²) and the (No. 2) Regulations 2025 extending the vacant-commercial-to-residential exemption to 31 December 2028. Up to the end of 2024, local authorities nationally received 1,457 notifications covering 3,429 units under the vacant-to-residential exemption (Department of Housing, reply to Heneghan PQ 43828/25, 29 July 2025).

#### 2. The Planning and Development Act 2024 and its phased commencement

PDA 2024 (No. 34 of 2024) was signed by President Higgins on 17 October 2024. Unlike PDA 2000, the new Act does not itself enumerate exempted development; all exemption classes are to be prescribed by separate regulations. The Government's PDA 2024 Implementation Plan (March 2025) sets out a review of all 100+ regulations made under PDA 2000 (≈1,200 pages of regulation), with exempted development singled out as "a small number of areas for which major revision of existing regulations or entirely new regulations are required".

Commencement has been phased: the first commencement order, S.I. No. 662 of 2024 (2 December 2024), was followed by S.I. Nos. 239, 256, 379, 452 and 633 of 2025, culminating on 31 December 2025. Part 17 (re-naming An Bord Pleanála as An Coimisiún Pleanála) was commenced on 18 June 2025 by S.I. No. 256 of 2025 (Planning and Development Act 2024 (Commencement) (No. 2) Order 2025, sealed 17 June 2025). Section 180 and Chapter 1 of Part 9 (judicial review) were commenced on 1 August 2025 by S.I. No. 379 of 2025. PDA 2024 reforms the Section 5 procedure: the replacement provision sits at section 10 of the 2024 Act (headed "Declaration on development, exempted development, etc.") and confines standing to a "relevant person" or a statutory undertaker. Under section 10(1), "relevant person" means: (a) the owner of the land; (b) a person eligible to apply for maritime development permission under section 85(2); (c) the occupier of the land who carries out (or proposes to carry out) the act or operation, or makes (or proposes to make) the change of use, with the owner's consent; (d) any other person doing so with the owner's consent; (e) a qualifying environmental NGO (a registered Irish company at least one year old, with environmental-protection objects in its constitution that it has pursued for at least one year, with at least ten members, and which has passed a prior authorising resolution); or (f) a prescribed person. The procedure can also now be used to confirm whether particular works fall within an existing permission — a useful expansion noted by Matheson's planning team.

#### 3. The April 2026 Cabinet memo and the residential exemption expansion

On 21 April 2026, Cabinet approved the "Exempted Development Regulations for Residential Dwellings" memo brought jointly by Minister Browne and Minister of State Cummins. Conditions include:

- Owner-occupier must reside in the principal dwelling.

- Detached modular unit up to 45 m² to the rear, with a separate entrance and a minimum distance from the main house.

- At least 25 m² of garden must remain.

- Compliance with the Building Regulations is required.

- Rent-a-Room scheme (€14,000 tax-free annual rental income) extended to such units, to be operationalised by Tánaiste and Minister for Finance Simon Harris TD in the Budgetary process.

- Larger extensions (up to 45 m²), subdivision, attic conversions including rooflights, bicycle/bin storage exemptions (four adult bicycles or three wheelie bins; front and rear).

Minister Browne (21 April 2026): "Since taking up my responsibilities as Minister for Housing, I have been laser focused on cutting red tape, reducing bureaucracy and streamlining systems to get Ireland building better and faster… we are making the system easier for citizens while freeing up planning resources for more complex priorities."

Minister Cummins (21 April 2026): "As Minister of State for Planning, my priority has always been to remove things from the planning system that don't need to be there. I have already introduced Agriculture exemptions, and now I am bringing forward these residential exemptions, which will give people autonomy over making small changes to their homes without needing planning permission."

The April 2026 memo follows a four-week public consultation that closed on 26 August 2025 with 922 submissions; "Over half of submissions by the public, of which are predominantly supportive, relate to the proposal to exempt modular-style homes up to 45sq/m to the rear of the dwelling" (Department of Housing press release, "Progress towards Exempted Development Regulations"). Regulations require positive resolutions by both Houses of the Oireachtas before signing; as at May 2026 they have not yet been laid.

Revenue confirmed in May 2026 that a modular home built on the grounds of an existing dwelling will be liable for Local Property Tax in its own right where the structure is "permanent in nature and suitable for use as a separate dwelling in its own right" (Revenue statement to Ipav CEO Genevieve McGuirk, reported by RTÉ News, 13 May 2026; Irish Times, 13 May 2026). Section 2A of the LPT Act defines "residential property" as "any building which is in use as, or is suitable for use as, a dwelling" and excludes structures "not permanently attached to the ground".

#### 4. The data-fragmentation problem

(a) National aggregation. There is no centralised national database of Section 5 declarations. The LGMA-led ePlanning portal (planning.localgov.ie / eplanning.ie) built by Annertech and recognised at the 16 October 2025 Public Sector Digital Transformation Awards in the Round Room at the Mansion House (winning "Most Collaborative Public Sector Project"; Annertech press release, 21 October 2025) as a "massive, six-year project" bringing together "central government departments and 30 local authorities", does not, at the time of writing, provide a single classified, downloadable national Section 5 dataset. The CSO Planning Permissions Background Notes state that the series "only provides coverage where development is subject to the requirement to obtain planning permission" — since exempted development is by statutory definition not subject to that requirement, it falls outside the CSO statistic. MyPlan.ie publishes GIS zoning and policy data but not Section 5 outcomes.

(b) An Coimisiún Pleanála's referral statistics. ACP/ABP annual reports do not isolate Section 5 referrals as their own line. The 2021 Annual Report Appendices record 118 "Referrals" received that year; the 2022 Appendices record 105. The 2024 Annual Report reports "Other Case Types" with 944 received / 887 disposed in 2023 and 463 received / 606 disposed in 2024 — a broader category that subsumes Section 5 referrals along with s.34 and s.254 referrals and other miscellaneous case types. A clean year-by-year Section 5-only series cannot be assembled from current open data and the absence is itself a publishable finding.

(c) Local authority publication practice. A spot survey of all 31 LAs reveals stark inconsistency:

Local Authority Discrete Section 5 register published? Reference convention Notes

Dublin City Council No — declarations merged into main planning register No dedicated S5 prefix surfaced Single largest LA caseload; EirePlan's internal classification flags misclassification

Dún Laoghaire-Rathdown No discrete register confirmed Generic EirePlan flags conflation between Section 5 and other declaration types

South Dublin Yes — every S5 declaration available on the planning portal "ED…" prefix (e.g. ED20/0021) OPR review (August 2024) confirms compliance with s.5(7B)

Fingal No discrete register confirmed Generic

Cork City Yes — published list "R…-yy" (e.g. R1038-26) List view; no advanced filter

Cork County Yes — "Exempted Development Applications and Decisions" register "D…yy" (e.g. D246.23) Status field "Exempt"/"Not Exempt"

Galway City No discrete register confirmed Generic OPR review subject (2022)

Galway County No discrete register confirmed Generic OPR review subject (2026)

Limerick City & County No discrete register confirmed Generic

Waterford City & County Yes — published "Section 5 Register" "Exempted Developments" list Explicit register page

Kildare Yes — Section 5 / SI 30 lists "ED 1234" (e.g. ED 1243; combined references like EDSI30-001-2023 also appear)

Meath Yes — "Section 5 Declarations Issued" page Hybrid prefixes "RS/LS/TS/PS" (e.g. RS526035); mapping to municipal districts not explicitly stated by council

Longford Yes — Section 5 Declarations list Generic

Donegal Yes — dedicated "Section 5 Declarations" page Generic

Tipperary Yes — dedicated Section 5 page on the Planning Exemption Certificate route Generic

Wicklow, Wexford, Kerry, Clare, Mayo, Sligo, Louth, Cavan, Monaghan No discoverable discrete register at the time of writing Generic Absence not confirmed via AIE/FOI

EirePlan's internal estimate, that roughly 1,400 Section 5 cases are surface-discoverable nationally on public planning portals against a plausible true population of 15,000–25,000 since 2000, is consistent with this fragmented picture. We cannot fully verify the precise EirePlan figures from public sources (they require systematic scraping and de-duplication across 31 portals), but the OPR's published reviews and direct inspection of council websites confirm the underlying pattern: the public Section 5 record is partial, inconsistently labelled, and not nationally aggregated.

(d) The OPR's published reviews. None of the published OPR section-31AS reviews to date contains a dedicated thematic chapter on Section 5 register practice. But several touch on directly adjacent issues:

- SDCC review (August 2024): "All Section 5 declarations issued since 2006 are available on the Council's website, meeting the requirements of section 5(7B) of the Act (that Section 5 declarations and associated documents should be available on an authority's website for inspection for a minimum period of eight weeks)."

- Meath review (May 2024): comments on the council's publication and weekly-list practice.

- Roscommon review (March 2025): comments on register transparency.

- Waterford review (September 2023): comments on GIS publication.

#### 5. Section 5 in the case law

A Section 5 declaration is not a development consent; it is a determination, made on the facts before the planning authority, of whether a particular activity constitutes development or qualifies as exempted development under Part I of the PDA 2000 (per the Court of Appeal in Narconon Trust v An Bord Pleanála [2021] IECA 307). The Court of Appeal in Narconon held that where a planning authority has issued an unappealed Section 5 declaration, ABP/ACP cannot effectively re-decide the same question on the same facts via a subsequent referral. In the same case Collins J observed that the proceedings "highlight significant deficiencies in the section 5 procedure", noting the four-week window, the absence of public participation, and the inadequacy of JR as a substitute for hearing rights.

#### 6. Why the data gap matters for the 2026 expansion

The Government's stated objective in expanding exempted development is to "free up planning resources for more complex priorities" and accelerate small-scale residential delivery. That is a plausible aim. But the policy bet depends on at least five empirical assumptions which the current Section 5 data cannot test:

- Baseline volumes. How many Section 5 declarations Ireland already issues each year, by class of works? Without a clean national series, the Department of Housing cannot calibrate the regulatory dose of exemption, particularly the substitution effect between Section 5 declarations and the new "no-declaration-needed" regime.

- Compliance. How often do works claimed to be exempt prove not to be on inspection? The Section 5 declaration is voluntary; many homeowners proceed without one. Local authority enforcement units sit on data that is not centrally collated. The Planner (16 May 2025) reported Wexford County Council alone had 415 live alleged-breach investigations at end-2024.

- Substitution effects. The SDCC finding above, that Section 5 is increasingly being used in place of Section 57 declarations for protected structures, illustrates the behavioural shifts that go undetected without proper classification.

- Regional take-up. Without a comparable register, there is no way to measure differential uptake of the new 45 m² exemption across rural vs urban LAs, or to detect concentration risks (e.g., overlooked-garden disputes in Dublin terraces vs detached rural sites).

- JR and enforcement defence. With 253 new JRs against ACP in the 18 months to June 2025 (Fine Gael TD Colm Burke, citing figures obtained directly from An Coimisiún Pleanála and reported in The Irish Times on 1 December 2025: 147 commencing in 2024 and 106 in the first six months of 2025, "17 cases per month since the start of 2025") and JR costs proposed to be capped at "just under €41,000 for a standard case", €53,350 for complex cases and €65,800 for very complex cases (Irish Times, 1 December 2025; Irish Examiner, 1 March 2026), the cost of poor record-keeping is no longer hypothetical.

Implication for AI and decision-support tools. Any automated reasoning over Irish exempted-development questions must train on or be evaluated against a corpus of historical Section 5 declarations. Where that corpus is incomplete (ACP's referrals not separable from "Other Case Types"), inconsistently classified (DCC, DLR), and partially unpublished (several of the 31 LAs), the ceiling on assistive accuracy is set by the data, not the model. A widening exemption regime built on top of an under-documented baseline compounds this risk.

#### 7. Comparative context: what good publication looks like

The contrast with other Irish public registers is striking. The Planning Application Register on the LGMA platform (planning.localgov.ie), the National Planning Application Database (housinggovie ArcGIS), MyPlan.ie's GIS zoning viewer, the Companies Registration Office, the Land Registry, and the Property Price Register all offer national, searchable, downloadable datasets. Section 5 declarations, the most legally consequential form of exempt-development determination, sit outside this paradigm. The statutory minimum under s.5(7B) PDA 2000 (eight weeks online display) appears in practice to function as a maximum in many LAs.

### Caveats

- EirePlan's internal figures. EirePlan's estimate of ~1,400 publicly discoverable Section 5 cases against a true population of 15,000–25,000 is not independently verifiable from public sources. We have reproduced the underlying fragmentation pattern from OPR reviews and direct inspection of LA portals, but readers should treat the precise figures as EirePlan's internal analysis rather than as a State-published statistic.

- ACP referral series. "Referrals" in ACP/ABP appendices include Section 5 referrals but also Section 34, Section 254 and other referrals. A discrete Section 5-only series is unavailable in current open data; the 2021 and 2022 appendices are the only years where a "Referrals" line is broken out at all, and from 2023 onward the figure is folded into "Other Case Types".

- 31-LA matrix. For several of the LAs listed in the final row of the table, absence of a discoverable register is not the same as absence of publication. The journalist may wish to issue AIE/FOI requests to those authorities to confirm. The position is dynamic — Donegal and Tipperary, which earlier iterations of this work had listed as missing, in fact maintain dedicated Section 5 pages.

- Quotes and dates. Ministerial and opposition quotes are taken from primary sources (gov.ie, RTÉ, Irish Times, party press statements). PDA 2024 commencement order numbers have been verified against the Irish Statute Book revised Acts edition (lawreform.ie).

- Modular policy is still pre-legislative. The exempted-development regulations have not yet been laid; the 21 April 2026 Cabinet decision approves the policy memo. Both Houses of the Oireachtas must pass positive resolutions before the regulations can be signed (Department of Housing, "Progress towards Exempted Development Regulations"). All references to the 45 m² exemption being "in force" should therefore be qualified as proposed.

- OPR reviews on Section 5 are indirect. None of the published OPR review reports contains a stand-alone thematic chapter on Section 5; the quotes used in this dossier are the closest published findings on register transparency, GIS publication, weekly-list publication, and the substitution of Section 5 for Section 57. A thematic OPR review on Section 5 specifically would close the most important evidentiary gap.

### Sources

Primary legislation and statutory instruments

- Planning and Development Act 2000 (revised), Law Reform Commission — https://revisedacts.lawreform.ie/eli/2000/act/30/section/5/revised/en/html

- Planning and Development Act 2024 (revised), Law Reform Commission — https://revisedacts.lawreform.ie/eli/2024/act/34/revised/en/html

- S.I. No. 600/2001 — Planning and Development Regulations 2001

- S.I. No. 75/2022 — Planning and Development Act (Exempted Development) Regulations 2022

- S.I. No. 493/2022 — Planning and Development Act 2000 (Exempted Development) (No. 3) Regulations 2022

- S.I. No. 662/2024 — PDA 2024 (Commencement) Order 2024 (first commencement order)

- S.I. No. 256/2025 — PDA 2024 (Commencement) (No. 2) Order 2025 (Part 17 / An Coimisiún Pleanála) — sealed 17 June 2025, commenced Part 17 on 18 June 2025

- S.I. No. 379/2025 — PDA 2024 (Commencement) (No. 3) Order 2025 (Chapter 1 of Part 9, judicial review)

- S.I. No. 452/2025 — PDA 2024 (Commencement) (No. 4) Order 2025

- S.I. No. 633/2025 — PDA 2024 (Commencement) (No. 5) Order 2025

- Department of Housing — Solar Planning Exemptions — https://www.gov.ie/en/department-of-housing-local-government-and-heritage/publications/solar-planning-exemptions/

- Department of Housing — Regulations on Agriculture Exempted Development (2025) — https://www.gov.ie/en/department-of-housing-local-government-and-heritage/press-releases/regulations-on-agriculture-exempted-development-and-extension-for-change-of-use-from-vacant-commercial-to-residential-properties-for-another-3-years-signed/

- Department of Housing — PDA 2024 Commencement Circular No 2A re An Coimisiún Pleanála — https://www.gov.ie/en/department-of-housing-local-government-and-heritage/circulars/pda-2024-commencement-circular-no-2a-re-an-coimisi%C3%BAn-plean%C3%A1la-updated-2-july-2025/

- Department of Housing — reply to Heneghan PQ 43828/25 (vacant-to-residential notifications), 29 July 2025 — https://www.oireachtas.ie/en/debates/question/2025-07-29/1640/

2026 exemption package and consultation

- Department of Housing — Progress towards Exempted Development Regulations — https://www.gov.ie/en/department-of-housing-local-government-and-heritage/press-releases/progress-towards-exempted-development-regulations/

- RTÉ — Proposed exemptions for modular homes brought to Cabinet (21 April 2026) — https://www.rte.ie/news/2026/0421/1569267-ireland-politics/

- RTÉ — Renters thrown 'to wolves' over modular homes – Cairns (21 April 2026) — https://www.rte.ie/news/2026/0421/1569403-modular-homes-reaction/

- RTÉ — Modular homes in gardens liable for local property tax, Revenue says (13 May 2026) — https://www.rte.ie/news/ireland/2026/0513/1573241-modular-homes-tax/

- Irish Times — Owners of back-garden modular homes face second local property tax charge, says Revenue (13 May 2026) — https://www.irishtimes.com/property/residential/2026/05/13/owners-of-back-garden-modular-homes-will-have-to-pay-local-property-tax-on-them-says-revenue/

- Irish Times — Property industry experts weigh in on back-garden modular homes (13 May 2026) — https://www.irishtimes.com/property/residential/2026/05/13/property-industry-experts-weigh-in-on-back-garden-modular-homes-from-tax-to-potential-income/

- Anglo Celt — Planning exemptions for modular homes brought to Cabinet (21 April 2026) — https://www.anglocelt.ie/2026/04/21/planning-exemptions-for-modular-homes-brought-to-cabinet/

- Labour — Government risks "shed-sits" as modular home plan rushed through Cabinet (21 April 2026) — https://labour.ie/news/2026/04/21/government-risks-shed-sits-as-modular-home-plan-rushed-through-cabinet/

- IPI — Irish Planning Institute calls on government to stop 'tinkering' with planning regulations (16 April 2026) — https://ipi.ie/2026/04/16/irish-planning-institute-calls-on-government-to-stop-tinkering-with-planning-regulations/

An Coimisiún Pleanála / An Bord Pleanála

- ABP Annual Report 2021 — https://www.pleanala.ie/getmedia/ad0a2dee-9721-4673-8f08-7d8cccddc5e8/Annual-Report-2021-EN.pdf

- ABP Annual Report 2024 — https://www.pleanala.ie/getmedia/aaad96a0-5b88-4cb6-b382-5387fce6c4e8/An-Bord-Pleanala-Annual-Report-2024-EN_1.pdf

- An Coimisiún Pleanála — https://www.pleanala.ie/en-ie/home

Office of the Planning Regulator reviews

- OPR Reviews Programme — https://www.opr.ie/reviews-programme/

- OPR — South Dublin County Council review (August 2024)

- OPR — Meath County Council review (May 2024)

- OPR — Roscommon County Council review (March 2025)

- OPR — Waterford City & County Council review (September 2023)

Local authority Section 5 / exempted development pages (selected)

- South Dublin County Council — https://www.sdcc.ie/en/services/planning-building-control/planning-applications/exempted-development/

- Cork City Council — https://www.corkcity.ie/en/council-services/services/planning/planning-application-process/exempted-development/

- Cork County Council — https://www.corkcoco.ie/en/resident/planning-and-development/exempted-development-applications-and-decisions

- Dublin City Council — Section 5 Declaration — https://www.dublincity.ie/planning-and-land-use/planning-application-rules-and-exemptions/section-5-declaration-check-if-development-requires-planning-permission

- Dún Laoghaire-Rathdown County Council — https://www.dlrcoco.ie/planning-applications/exempt-development

- Meath County Council — https://www.meath.ie/council/council-services/planning-and-building/planning-permission/do-you-need-planning-permission/section-5-declarations-issued

- Waterford City & County Council — Section 5 / Exempted Development information — https://waterfordcouncil.ie/documents/planning-forms/

- Waterford City & County Council — Section 5 Register (live PDF, dated February 2026; direct HTTP fetch may return 403 due to WAF bot-protection but the register is operational) — https://waterfordcouncil.ie/app/uploads/2026/02/Section-5-Register.pdf

- Kildare County Council — https://kildarecoco.ie/AllServices/Planning/LicencesandDeclarations/Section5SI30/

- Longford County Council — https://www.longfordcoco.ie/services/planning/exempted-development-section-5-/

- Donegal County Council — https://www.donegalcoco.ie/en/services/planning/development-management/publications-notifications-and-planning-registers/section-5-declarations

- Tipperary County Council — https://www.tipperarycoco.ie/planning-and-building/planning-exemption-certificate/section-5s

Case law commentary

- Courts Service — Narconon Trust v An Bord Pleanála [2021] IECA 307 (Collins J. judgment) — https://www.courts.ie/view/Judgments/cbcc0391-c44e-407f-a7f2-797382dbd48b/1cc2fa3f-8034-47b9-8c29-071af5c49f0d/2021_IECA_307%20(Collins%20J).pdf/pdf

- A&L Goodbody — Court of Appeal rejects "collateral challenge" to Section 5 declaration (Narconon) — https://www.algoodbody.com/insights-publications/court-of-appeal-rejects-collateral-challenge-to-section-5-declaration

- Addleshaw Goddard — Court of Appeal Clarifies the Position in Respect of Conflicting Section 5 Declaration — https://www.addleshawgoddard.com/en/insights/insights-briefings/2022/real-estate/court-of-appeal-clarifies-the-position-in-respect-of-conflicting-section-5-declaration/

- Matheson — Irish Planning Legislation Overhauled – Yet To Be Implemented — https://www.matheson.com/insights/irish-planning-legislation-overhauled-yet-to-be-implemented/

- Michael Furminger BL — Exempt Development Under PDA 2024 — https://michaelfurminger.substack.com/p/exempt-development-under-pda-2024

Judicial review context

- Fine Gael — Over 250 judicial reviews taken since 2024 – Burke — https://www.finegael.ie/over-250-judicial-reviews-taken-since-2024-burke/

- Irish Times — Legal fees to be capped at €41,000 in standard judicial review cases (1 December 2025) — https://www.irishtimes.com/ireland/housing-planning/2025/12/01/legal-fees-to-be-capped-at-41000-in-standard-judicial-review-cases-for-successful-planning-objectors/

- Irish Examiner — Government's plan to cap judicial review fees 'an attack on lawyers' (1 March 2026; headline phrase is a direct quote from Bar Council chair Seán Guerin SC) — https://www.irishexaminer.com/news/politics/arid-41802251.html

Digital/infrastructure

- Annertech — Digital Transformation award for trailblazing ePlanning portal (21 October 2025; "Most Collaborative Public Sector Project", Public Sector Digital Transformation Awards 2025) — https://www.annertech.com/blog/digital-transformation-award-trailblazing-eplanning-portal

- MyPlan.ie — https://www.myplan.ie/

- CSO — Planning Permissions Background Notes — https://www.cso.ie/en/methods/surveybackgroundnotes/planningpermissions/

Comparative

- The Planner — Ireland round-up: Wexford planning breaches (16 May 2025) — https://www.theplanner.co.uk/2025/05/16/ireland-round-wexford-planning-breaches-waterfords-north-quays-glass-bottle-site

Compiled May 2026; corrections incorporated 19 May 2026. Treat the EirePlan internal figures (~1,400 discoverable cases vs 15,000–25,000 estimated true population) as the author's own analysis pending public dataset release.

Share

### Read More

April 10, 2026

March 24, 2026

March 17, 2026

February 5, 2026

On this page

Share

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 11: Ireland's Empty Buildings - Eireplan

Source URL: https://eireplan.com/blog/post/Irelands_Empty_Buildings

Skip to main content

##### Ireland's Empty Buildings

In the middle of a housing crisis, Ireland has tens of thousands of empty buildings. We examine the scale, barriers, and what it would take to bring them back into use.

This Blog Post was published on 10 April 2026

## Ireland's Empty Buildings

In the middle of a housing crisis, Ireland has tens of thousands of empty buildings. That uncomfortable fact has become one of the defining paradoxes of Irish public life, visible on every main street, in every small town, and in the upper floors above shops in the centre of Dublin. So why does the vacancy persist, and what it would actually take to bring these buildings back into use?

This article looks at what the evidence says about the scale of the problem, the real barriers to redevelopment, how much of it genuinely requires a full professional planning team, and whether better access to information could help ordinary owners understand what is and isn't possible with the building in front of them.

### The problem, by the numbers

Ireland has no single agreed figure for vacancy, and that is itself part of the story. Three sources measure three different things:

- Census 2022 recorded 163,433 vacant dwellings (around 8% of the housing stock), but the CSO itself cautions that this figure "should not be used as a measure of long-term vacancy," as it includes properties between lettings, under renovation, for sale, or where the owner was deceased or in care ( CSO, Census 2022 Profile 2 - Housing in Ireland ).

- CSO's electricity-based measure - dwellings consuming less than 180kWh per quarter for four consecutive quarters - gives a much lower figure of 70,149 vacant homes (3.2%) at end 2024 ( CSO, Residential Vacancy Based on Metered Electricity Consumption 2024 ; Irish Times, 24 March 2026 ).

- GeoDirectory's Q2 2025 report recorded 80,328 vacant and 19,821 derelict residential properties ( GeoDirectory Residential Buildings Report Q2 2025 ).

Commercial vacancy tells a grimmer story. GeoDirectory's Q4 2025 report recorded a 14.6% national commercial vacancy rate - the highest since tracking began in 2013 , covering 30,687 units ( GeoDirectory, February 2026 ). Dublin has Ireland's lowest residential vacancy at around 1.1%, but its commercial vacancy sits at 13.5%, with Dublin 2 and Dublin 8 both above 17%.

Then there is the enforcement gap. Local authority Derelict Sites Registers contained just 2,140 sites at the end of 2024 - a tiny fraction of GeoDirectory's 20,000-plus derelict residential count. The Anois/#DerelictIreland campaign documented 700 derelict properties within 2km of Cork city centre against only 95 on the official register ( Irish Examiner ). In 2023, just €604,621 in derelict sites levies was collected nationally, and 17 of 31 councils collected nothing at all ( Irish Times, 19 March 2025 ; TheJournal.ie, March 2025 ).

### Why aren't these buildings being fixed?

The barriers are not one problem but several, and they interact.

Money is the biggest barrier. The most important evidence here is the Society of Chartered Surveyors Ireland's Real Cost of Renovation Report (March 2023), which assessed twenty vacant and derelict properties across the country and found that only five were financially viable to renovate without grant support . Even with maximum Croí Cónaithe grants, only one additional property became viable. The viability gap is most acute outside Dublin, where market values are lower but renovation costs are broadly the same ( SCSI, 2023 ; Irish Times, 22 March 2023 ). Eighty per cent of surveyors surveyed said it was harder for borrowers to access finance for renovation than for a standard purchase, because banks generally will not lend against a property that isn't habitable ( IFSC, 2023 ).

Construction VAT sits at 13.5% under an EU derogation, with no reduced rate for long-vacant properties. National rebuild costs rose a further 7% in 2025 ( SCSI House Rebuilding Guide, 2025 ), and Ireland's construction workforce remains well below the level needed to meet both new-build and retrofit demand simultaneously.

Regulation is the second barrier, but a more targeted one than is often assumed. Over half of surveyors in the SCSI study said building regulations - particularly Part B (fire safety) and Part M (disability access) - were "too restrictive" for older properties, where meeting modern standards in narrow historic shells can be physically very difficult ( SCSI, 2023 ). Ireland has over 40,000 Protected Structures nationally, including more than 8,000 in Dublin, and for these buildings even internal works can require planning permission if they materially affect character ( RIAI ; Dublin Civic Trust ).

Ownership is the third. Probate delays routinely run six to eighteen months, and the Law Society has documented "seven deadly delays" in conveyancing that can stall sales of inherited vacant properties ( Law Society of Ireland, 2024 ). The government's CPO Activation Programme entered 11,186 properties between 2023 and 2024, but compulsory purchase typically takes around 18 months and is constitutionally constrained ( gov.ie ).

Information is the fourth, and the most overlooked. A prospective renovator currently has to consult MyPlan.ie for zoning, the relevant local authority's planning portal for application history, buildingsofireland.ie for heritage designations, floodinfo.ie for flood risk, landdirect.ie for title, the Building Control Management System for regulations history, An Bord Pleanála for appeals, GeoDirectory for vacancy data, and the derelict sites register. Each has a different interface and a different update cycle. Research led by Prof Rob Kitchin at Maynooth University documents how Ireland's planning data sits across dozens of non-interoperable systems, making it hard even for professionals to build a full picture of any one site ( Kitchin et al., "Genealogy of a data ecosystem," Digital Geography & Society , 2025 ).

### Not every vacant building needs a planning team

This is where the conversation tends to flatten out, because the word "planning" gets used as a catch-all for regulatory difficulty. It's worth being specific.

Under the Planning and Development Act 2000 and the exempted development regulations, a very wide range of works can be carried out on an existing dwelling without any planning application at all: internal alterations that don't affect external appearance, rear extensions up to 40 square metres (cumulative since 1964), garages and sheds up to 25 square metres, solar panels, chimneys, and repainting or replastering consistent with neighbouring buildings ( Citizens Information ). Converting vacant commercial premises to residential has also been exempt from planning permission since 2018, subject to conditions, under SI 30/2018 as extended by SI 75/2022. By May 2025, that exemption alone had generated 1,457 notifications creating 3,429 new homes through a simple notification process rather than a full application ( gov.ie ).

The upshot is that for something like two-thirds of vacant residential buildings in Ireland, ordinary houses and flats needing internal renovation, planning permission simply isn't the barrier. The real obstacles are finance, finding a builder, and knowing what you're looking at. A further slice of vacant commercial buildings can move to residential use via notification rather than full application. Full planning complexity concentrates on two categories: non-exempt change of use, and works to protected structures or buildings in Architectural Conservation Areas, which together probably account for 5-10% of visible vacancy but are disproportionately represented on the main streets where dereliction is most obvious.

None of this is to say the system is easy, or that people should proceed without professional advice. For protected structures, for anything involving structural work, and for any non-trivial change of use, an architect and ideally a conservation specialist are essential, not optional. But there is a meaningful difference between a project that requires a full planning team and one that a well-informed owner can take on with a good builder, a surveyor, and clear information about what rules apply.

### What the government is doing

The Vacant Property Refurbishment Grant (Croí Cónaithe) has become the quiet success story: €247 million paid across 4,514 completed homes by the end of 2025, with 3,066 grants paid in 2025 alone - a 127% increase on the previous year ( Anglo Celt, February 2026 ; gov.ie ). The grant is paid in arrears, which remains a real problem for people without savings, but the Local Authority Purchase and Renovation Loan launched in July 2024 now helps bridge that gap for first-time buyers.

Other schemes have fared much worse. The Repair and Leasing Scheme delivered just 9 homes in its first year against an 800-home target ( RTÉ ). The Living City Initiative, a tax incentive for refurbishing pre-1915 buildings, attracted only 242 applications in Dublin over an entire decade, described in the Irish Times as "shockingly poor" uptake ( Irish Times, 16 October 2025 ). The URDF Revolving Vacancy Fund of €150 million had purchased just 47 homes after its first year.

A Derelict Property Tax administered by Revenue rather than local authorities is planned from around 2027, following the logic that Revenue collects around 95% of the Local Property Tax while councils collected roughly 10% of the derelict sites levy ( gov.ie ). A new Vacant Above the Shop Grant of up to €140,000 launched in March 2026.

### What if the information were in one place?

This is the question that sits underneath everything above. Research from Maynooth University describes Ireland's planning data as a fragmented ecosystem in which individual applications can be processed but cross-system intelligence, the kind of picture needed to understand a specific site's constraints, history, and opportunities, is extraordinarily difficult to assemble ( Kitchin et al., 2025 ). The Office of the Planning Regulator's own Digital Planning and Analytics Strategy 2023-2025 commits to building "a single point of access to digital datasets held disparately by various bodies and organisations."

International comparators suggest consolidation works. Scotland's eDevelopment.scot processes 95% of all planning applications through one portal, with estimated savings of over £100 million for applicants. England's PlanX platform has delivered significant time savings on applications and large increases in community involvement in pilot areas. The Netherlands' Omgevingsloket, launched in January 2024, lets any citizen check the rules that apply at a specific address and determine whether they need a permit at all.

The point is not that technology replaces expertise. It is the opposite. When someone can see, in one place, that a building they're interested in is not a protected structure, is not in a flood zone, has a clean planning history, and sits in a zone where residential use is permitted, they can make an informed judgement about whether the next step is a builder, architect or planner, and if it's a planner, what questions to ask. When the constraints are significant, it is a protected structure, it is in an ACA, it does have a refusal history, that same information tells them early that they need specialist advice before they sink money into a purchase. The Town Centre First policy ( gov.ie ) explicitly calls for "improved data sources, defined measurement requirements and research on cost benefit analysis" as part of its approach to town centre revival.

For professionals, the same consolidation cuts the hours spent assembling site histories from half a dozen portals. For curious members of the public who have inherited an old family home, or who walk past the same boarded-up building on the way to work every day and wonder what it would take, it answers the first and most paralysing question: where do I even start?

### Conclusion

Ireland's vacancy problem is a financial viability problem for properties outside the big cities, a legal-ownership problem for inherited and absentee-owned homes, a regulatory problem for protected structures and complex change-of-use cases, and an information problem that sits on top of all of them and makes everything harder than it needs to be.

The encouraging news is that the majority of vacant homes don't need heroic planning interventions, but money, a builder, and clarity. Grant take-up is finally accelerating. Enforcement is shifting to Revenue. Exempted development rules are being reviewed. And the work of researchers and campaigners, from the SCSI's costings to Anois's street-level surveys to Maynooth's data research, is steadily reframing vacancy as a solvable problem rather than an inevitable feature of the Irish landscape.

The final barrier, and perhaps the most tractable, is simply knowing what you're looking at. Better access to consolidated map data, site history, and constraint information doesn't replace the architect, the surveyor, or the planner. It helps people understand when to call them, and gives those professionals a stronger starting point when they pick up the phone.

#### Key sources

- CSO, Census 2022 Profile 2 - Housing in Ireland and Residential Vacancy Based on Metered Electricity Consumption 2024

- GeoDirectory/EY, Residential Buildings Report Q2 2025 and Commercial Buildings Report Q4 2025

- Society of Chartered Surveyors Ireland, Real Cost of Renovation Report (March 2023) and House Rebuilding Guide (2025)

- RIAI, Old House New Home and guidance on protected structures

- Heritage Council, Collaborative Town Centre Health Check Programme

- Department of Housing, Local Government and Heritage, Vacant Homes Action Plan 2023-2026 , Bringing Back Homes Manual , Town Centre First Policy

- Kitchin, R. et al., "Genealogy of a data ecosystem: The digitalisation of planning development and control in Ireland, 2000-2024," Digital Geography & Society (2025)

- Stokes & O'Callaghan (TCD), Taking Stock of Dublin's Vacant Sites and Properties (2021)

- Office of the Planning Regulator, Digital Planning and Analytics Strategy 2023-2025

- Irish Times, Irish Examiner, TheJournal.ie, RTÉ and Anglo Celt reporting (2023-2026), as cited inline

Share

### Read More

May 19, 2026

March 24, 2026

March 17, 2026

February 5, 2026

On this page

Share

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 12: What If Planners Had More Time? - Eireplan

Source URL: https://eireplan.com/blog/post/What_If_Planners_Had_More_Time

Skip to main content

##### What If Planners Had More Time?

When administrative work is handled by AI, planning professionals face a deceptively complex question: what do they choose to do next?

This Blog Post was published on 24 March 2026

## What If Planners Had More Time?

#### When administrative work is handled by AI, planning professionals face a deceptively complex question: what do they choose to do next?

### The Hours Hidden in Plain Sight

A planner in a busy private consultancy can spend a significant portion of their working day on tasks that have nothing to do with planning judgement: checking submission checklists against each local authority's individual requirements, cross-referencing policy references to make sure they haven't been superseded, hunting through a shared drive for the correct version of a drawing. These tasks are not trivial. A single omission on a submission checklist can invalidate an application before it is even assessed, but they are also not what planners spent years in education to do.

Ireland's planning system processes more than 33,000 applications annually within an increasingly complex legislative and policy framework. Refusal rates have doubled over the last decade. Yet the underlying workflow of research, compliance, document assembly, validation, etc., etc., remains largely manual. The time cost is real and it accumulates quietly, project by project.

AI tools purpose-built for planning work, such as EirePlan, are beginning to automate these structural and administrative elements: verifying policy against current legislation at the date of submission, generating site-specific pre-submission checklists that replicate how a planning authority reviews incoming applications, and maintaining a versioned document workspace with a full audit trail. The promise is straightforward: hours returned to the professional each week.

But this raises a question that is less straightforward: what does a planner actually do with that time?

"Generative AI gave people the ability to do more of what they want to do and less of what they have to." — MIT Initiative on the Digital Economy

### What the Research Shows

The question of how professionals use time recovered through AI has attracted serious attention from researchers, and the emerging picture is more varied and more cautionary than the promotional story typically told about workplace AI.

#### The Time Savings Are Real

A 2024 survey by the Adecco Group covering more than 35,000 workers across 27 countries found that AI tools save workers an average of one hour per day. Those figures are consistent across sectors: workers in energy and clean technology reported savings of 75 minutes a day; those in financial services, 57 minutes. Research published by the Federal Reserve Bank of St. Louis in early 2025 found that workers who use generative AI save approximately 5.4% of their working hours. That's around 2.2 hours per week for someone working full time.

For planning professionals, where much of the repetitive workload is document-heavy and research-intensive, the potential savings are likely at the higher end. Anthropic's own analysis of AI-assisted tasks found that compiling information from reports saw time savings of approximately 95%, while document drafting of reports, memos, and statements saw savings of around 87%.

Sources: Adecco Group Global Workforce Report 2024; Federal Reserve Bank of St. Louis, 'The Impact of Generative AI on Work Productivity', February 2025; Anthropic Economic Index, 'Estimating Productivity Gains', 2024.

#### What People Actually Did With the Extra Time

The Adecco research found that workers split broadly into three camps. Around 28% directed their extra time toward more creative work; 26% used it for strategic thinking; and 27% said it helped them achieve a better work-life balance. However, 23% reported simply tackling the same workload at the same pace, and 21% spent more of their recovered time on personal activities during the working day.

A 2025 survey by Indeed's Hiring Lab, drawing on responses from more than 80,000 workers across eight countries including Ireland, found that workers most commonly used saved time to take on additional tasks and projects, or to improve the quality of their existing work. About a third of US respondents said they redirected time toward work-life balance improvements; nearly a quarter said they used it for breaks and stress management.

Research published in the Harvard Business Review in March 2025 offered a more sober view: that time freed by AI does not automatically flow toward high-value work. Without deliberate intention, and without managerial or organisational structures that actively redirect it, recovered hours can dissipate into low-value activity or simple downtime. As one analysis summarised the finding: the windfall can evaporate into idle tinkering, low-value busywork, or outright downtime.

A separate study tracking around 200 employees at a US technology company over eight months found that after adopting AI tools, workers moved faster, took on a wider range of tasks, and extended their work into more hours of the day, even without being asked to do so. The enthusiasm was real, but so were the consequences. Workloads quietly expanded to overwhelming levels, and cognitive fatigue and weaker decision-making followed. The tool delivered efficiency. The organisation had not thought through what efficiency was for.

Sources: Adecco Group Global Workforce Report 2024; Indeed Hiring Lab, December 2025; Harvard Business Review, 'How Is Your Team Spending the Time Saved by Gen AI?', March-April 2025; Inc., 'AI Promised to Save Time. Researchers Find It's Doing the Opposite', February 2026.

#### The Shift Toward What Professionals Actually Want to Do

The more optimistic strand of research points in a consistent direction: when AI handles structural and routine work, knowledge workers tend to migrate toward the parts of their role they find most meaningful. A study of software developers using GitHub's Copilot tool, conducted by researchers at the MIT Initiative on the Digital Economy, found that developers given AI assistance did more core coding work and fewer non-coding tasks. In other words, they shifted toward the work they were actually trained for.

The study's lead researcher, Frank Nagle, put it simply: generative AI gave people the ability to do more of what they want to do and less of what they have to. There was a secondary finding worth noting for any collaborative profession: developers also spent less time conferring with peers, which raised questions about the value of the human interaction that routine collaboration enables. Efficiency, it turned out, had social costs as well as benefits.

Source: MIT Sloan Management Review / MIT Initiative on the Digital Economy, 'Generative AI Changes How Employees Spend Their Time', March 2025.

### Four Things Irish Planners Might Do With More Time

Irish planning professionals are not generic knowledge workers. They are graduates of professionally accredited programmes, typically a minimum of four years of higher education, increasingly five or more, trained in sustainable development, community engagement, environmental law, climate policy, urban design, and the social dimensions of place. The Irish Planning Institute describes the primary function of planning as envisioning sustainable futures for places and working in partnership with others to bring about change in meaningful and effective ways.

That is a substantial brief. What happens when the administrative weight is lifted, even partially?

#### 1. Higher-Quality Professional Judgement

The most immediate use of recovered time is also the most obvious: applying more careful professional judgement to the work already on the desk. In a practice environment where planners are under pressure from volume, the temptation is to produce compliant applications rather than excellent ones. With time available for deeper review, revisiting the site context, reassessing design quality, stress-testing the policy argument, the standard of professional advice can rise.

This is not a small thing. The Irish planning system awards significant weight to professional opinion in assessments. Better-prepared applications are less likely to attract requests for further information, less likely to be refused, and less likely to generate appeals. The downstream benefits extend to clients and, ultimately, to the quality of built development.

Research from Microsoft's 2025 Work Trend analysis found that 85% of workers using AI tools said AI helped them focus on more important work, and 84% credited it with boosting their creativity. The most mature AI users, those who had integrated the tools deeply into their workflows, were viewed as more innovative by their colleagues and reported feeling more energised and motivated.

Source: Microsoft Work Trend Index 2025, cited in Speakwise Knowledge Worker Productivity Statistics 2026.

#### 2. Richer Community and Stakeholder Engagement

Community engagement is formally required in Irish planning processes, but the quality of that engagement varies enormously. When it competes with the volume demands of application preparation, it is often reduced to its minimum statutory form: a notice posted, a meeting held, a response filed.

Planners trained in recent years have a sophisticated understanding of what meaningful community engagement looks like. They know the research on participatory planning, on the gap between consultation and genuine co-design, and on the long-term costs of development that does not carry community trust. The Irish Planning Awards have consistently recognised planning projects that go significantly beyond statutory requirements in their engagement work with communities, minority groups, and young people.

Time is the resource that separates minimum compliance from genuine engagement. A planner with hours freed from policy verification and document assembly can do more — attend more meetings, develop better-quality visual materials, take time to listen, and revise applications in response to what they hear. The American Planning Association's PAS Report 604 on AI in planning identified community engagement as precisely one of the areas where AI-recovered time was most likely to yield meaningful professional returns.

Sources: Irish Planning Institute, 2025 Irish Planning Awards shortlist; American Planning Association, PAS Report 604: Planning With Artificial Intelligence, 2023.

#### 3. Investing in Climate and Sustainability Work

Ireland's planning system operates within an ambitious policy environment. The Climate Action Plan, the Housing for All Strategy, the EU Green Deal, and alignment with the UN Sustainable Development Goals together represent a profound shift in what planning is expected to deliver. TU Dublin's planning programme describes its graduates as joining a global transition; UCC's MPlan emphasises climate justice as one of planning's central contemporary questions.

The gap between what planning graduates are trained to engage with and what day-to-day practice often allows is real. Climate adaptation analysis, biodiversity assessment, sustainable mobility integration, and long-term resilience planning, all take time that is often consumed by the mechanics of application preparation.

The APA's report on AI in planning argued that climate change, income inequality, affordable housing, and other pressing issues require enhanced approaches based on evidence and meaningful public discourse, and that AI is yet another tool planners should be leveraging to enhance problem-solving. The tool, in other words, is most valuable when it frees the planner to engage with the substantive challenges of 21st-century planning rather than the administrative burdens of 20th-century process.

Sources: TU Dublin, BSc Spatial Planning and Environmental Management programme description; American Planning Association, 'AI in Planning: Why Now Is the Time', Planning Magazine, Winter 2022.

#### 4. Growing the Practice

For principals and senior planners in private practice, time recovered from administration opens a more commercial possibility: capacity to take on more work, or to develop services that were previously unaffordable to offer. A practice that can process compliance and documentation more efficiently can serve more clients, respond to enquiries more quickly, and compete on quality rather than simply on available hours.

There is also a professional development dimension. Atlassian research found that mature AI users are 1.5 times more likely to reinvest recovered time into learning new skills. For a profession facing rapid change in planning law, digital tools, and the complexity of environmental and climate obligations, the ability to invest in continued learning rather than simply keeping up with workload has real long-term value.

The Thomson Reuters Future of Professionals survey, drawing on more than 2,200 professionals in law, tax, and related knowledge fields, found that 42% of respondents wanted to spend more time on engaging, creative work, and nearly 60% wanted their profession to focus more on work-life balance. The pattern of aspiration is consistent: when administrative burden lifts, professionals want to move toward the substantive, the human, and the meaningful.

Sources: Atlassian AI Collaboration research, 2025; Thomson Reuters Future of Professionals Report 2024, cited in Fortune, July 2024.

### The Real Question Is Intentionality

The research is clear on one thing: time saved does not automatically become time well spent. The Harvard Business Review analysis, and the study of the technology company whose employees quietly worked longer rather than better, both point to the same conclusion. Recovered time is a resource. Like any resource, it requires deliberate allocation.

For planning practices and individual planners, this means thinking in advance about what the extra hours are for. Is it for a more thorough pre-submission review process? More time at public consultation meetings? A dedicated slot each week for professional development? A capacity to take on a category of work that was previously impractical?

The answer will differ by practice size, individual role, and the kinds of projects a practice works on. What matters is that the question is asked. AI tools like EirePlan are designed to handle the structural and administrative elements of application preparation — policy verification, pre-submission validation, document control, precedent research. That is a significant weight off a professional's working day.

What planners do with the weight removed is, in the end, a professional question, and a human one. In Ireland, planners were trained to envision sustainable futures. The question AI poses, obliquely but insistently, is whether the daily structure of practice has been leaving enough room to do that.

"The potential of AI lies in assisting with recurring data and analysis-intensive tasks — and helping the profession step back and identify opportunities for process improvement." — American Planning Association

### References

Adecco Group (2024). Working through change: Adapting to an AI-driven world of work. Global Workforce Report.

American Planning Association (2022). AI in Planning: Why Now Is the Time. Planning Magazine, Winter 2022.

American Planning Association (2023). PAS Report 604: Planning With Artificial Intelligence.

American Planning Association (2025). Can AI Empower Planners to Accomplish More with Less? Planning Magazine, June 2025.

Anthropic (2024). Estimating Productivity Gains. Anthropic Economic Index.

Atlassian (2025). AI Can Help Knowledge Workers Fix These Five Frustrations. Harvard Business Review (sponsored content), April 2025.

Bick, A., Blandin, A., and Deming, D. (2025). The Impact of Generative AI on Work Productivity. Federal Reserve Bank of St. Louis. February 2025.

Haas School of Business, University of California Berkeley (2026). Cited in: Inc., AI Promised to Save Time. Researchers Find It's Doing the Opposite. February 2026.

Harvard Business Review (2025). How Is Your Team Spending the Time Saved by Gen AI? March–April 2025.

Harvard Business Review (2025). The Gen AI Playbook for Organizations. November–December 2025.

Indeed Hiring Lab / Aoki, Y. (2025). Workers Use Time Saved by AI to Improve Their Roles. December 2025.

Irish Planning Institute (2023). About Planning.

Irish Planning Institute (2025). 2025 Irish Planning Awards Shortlist.

Microsoft Research (2025). The Future of AI in Knowledge Work: Tools for Thought at CHI 2025. April 2025.

MIT Initiative on the Digital Economy / Nagle, F. et al. (2025). Generative AI Changes How Employees Spend Their Time. MIT Sloan Management Review, March 2025.

Thomson Reuters (2024). Future of Professionals Report. Cited in Fortune, July 2024.

TU Dublin (2025). BSc in Spatial Planning and Environmental Management (TU835).

University College Cork (2025). MPlan in Planning and Sustainable Development.

Share

### Read More

May 19, 2026

April 10, 2026

March 17, 2026

February 5, 2026

On this page

Share

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 13: Why We’re Building a Planning Knowledge Engine (Not Just Another AI Chatbot) - Eireplan

Source URL: https://eireplan.com/blog/post/Why_We_Are_Building_A_Planning_Knowledge_Engine

Skip to main content

##### Why We’re Building a Planning Knowledge Engine (Not Just Another AI Chatbot)

Eireplan is building a planning knowledge engine, not just another AI chatbot. Learn why context matters.

Read this post on LinkedIn

This Blog Post was published on 20 January 2026

Planning professionals are rightly sceptical of artificial intelligence.

In recent years, generic AI tools have been presented, often loudly, as universal problem solvers: systems that can “answer any question”, “draft any document”, or “replace professional judgement”. For those working in planning, development, and infrastructure, such claims are not merely unconvincing; they are fundamentally misaligned with the realities of the planning system.

Planning is not a domain of generic answers. It is a domain of hierarchy, precedent, geography, time, and accountability. It is governed by statute, shaped by policy layers, and ultimately decided by human actors who are accountable to the law, the courts, and the public.

At Eireplan, we are not building an AI chatbot and hoping it will somehow understand planning. We are building a planning knowledge engine: a structured, verifiable intelligence layer designed to support planners, not replace them, within the constraints and responsibilities of the Irish planning system.

This distinction matters.

### The Limits of Generic AI in Planning

Large language models are impressive at producing fluent text. They are far less reliable at answering questions where correctness depends on contextual validity rather than linguistic plausibility.

In planning, this problem is acute.

A generic AI system does not inherently understand:

- the legal hierarchy between primary legislation, ministerial guidelines, regional strategies, development plans, and local area plans;

- the fact that policy applicability varies by local authority, zoning, and site context;

- that policy interpretation is time-bound, with superseded plans and transitional provisions;

- or that a “reasonable-sounding” answer is professionally useless if it cannot be traced to a specific policy, section, or decision.

For a planner, an answer without provenance is not an answer. It is a risk.

This is why general-purpose AI tools, however capable they may appear, are ill-suited to professional planning work when used in isolation. They are not designed to reason over policy hierarchies, nor to distinguish between current and historical frameworks, nor to surface uncertainty where interpretation is contested.

Most importantly, they cannot carry accountability. Planners do.

### Planning Is a Structured Knowledge System, Not a Textual One

The Irish planning system is often described as complex, but complexity is not the core challenge. The deeper issue is structure .

Planning knowledge is inherently layered:

- Law establishes the statutory basis and procedural requirements.

- National policy sets strategic objectives and mandatory considerations.

- Regional strategies translate those objectives spatially.

- Local development plans and LAPs apply policy at site and area level.

- Decisions and appeals interpret and test these layers in practice.

Each layer constrains the one below it. Each operates within defined temporal boundaries. None can be treated as interchangeable text.

A system that treats planning documents as a flat corpus to be summarised or paraphrased will inevitably collapse these distinctions. The result may look coherent, but it is epistemically unsound.

A planning knowledge engine, by contrast, must preserve structure first and generate language second.

### Why Verifiability Is Non-Negotiable

In regulated professions, confidence does not come from eloquence. It comes from traceability.

Any tool used in planning must be able to answer a simple follow-up question:

“Where does that come from?”

Verifiability is not an optional feature. It is the basis on which professional advice is defended, whether to a client, a local authority, An Bord Pleanála, or a court.

This is where generic AI systems struggle most. Even when they produce correct answers, they often cannot reliably explain why those answers are correct in a way that maps cleanly onto statutory or policy sources.

Eireplan is designed on the opposite premise: that every substantive output must be anchored to identifiable sources, specific policies, sections, decisions, or datasets, within their proper temporal and geographic scope. Where uncertainty exists, it must be surfaced, not smoothed over.

This approach reflects the realities highlighted in official analyses of the Irish planning system, which show rising complexity, increasing workloads, and significant invalidation rates linked to procedural and documentation issues
PLANNING SOLUTION.

### Temporal and Geographic Context Are Not Edge Cases

One of the most common failure modes of generic AI tools in planning is their treatment of time and place as secondary details.

In practice, they are central.

A development plan that expired last year is not “mostly relevant”. A policy that applies in one county but not another cannot be treated as a general principle. Transitional provisions matter. Material contraventions matter. Ministerial guidelines issued after plan adoption matter.

Planning decisions are not made in the abstract; they are made on specific sites, under specific plans, at specific moments in time.

A planning knowledge engine must therefore be capable of:

- distinguishing current policy from superseded policy;

- understanding spatial applicability down to zoning and site context;

- and reflecting how interpretation evolves through decisions and appeals.

This is not something that can be reliably inferred from language alone. It requires structured data, explicit modelling of policy relationships, and constant maintenance as the planning framework evolves.

### AI Does Not Replace Planners, and Should Not Try To

It is worth stating this plainly: AI does not replace planners.

Nor should it.

Planning is not a clerical exercise. It involves professional judgement, negotiation, ethical responsibility, and public accountability. These are not deficiencies to be automated away; they are the core of the profession.

The appropriate role of AI in planning is supportive, not substitutive.

Used well, AI can:

- reduce repetitive research across legislation, policy, and precedent;

- assist with structuring and cross-checking documentation;

- surface relevant considerations that might otherwise be missed under time pressure;

- and help professionals focus their expertise where it matters most.

Used poorly, AI can obscure responsibility, encourage over-confidence, and introduce subtle but serious errors into regulated processes.

Eireplan is built on the assumption that human accountability remains central. Any output generated within the platform is intended to be reviewed, edited, and ultimately owned by the planner. The system supports reasoning; it does not stand in for it.

### From Chat Interfaces to Knowledge Infrastructure

Much of the current discourse around AI focuses on conversational interfaces. While dialogue is a useful mode of interaction, it is not a substitute for underlying intelligence.

A chat interface without a robust knowledge architecture behind it is, at best, a convenience layer. At worst, it is a confidence amplifier for unverified information.

Eireplan’s focus is therefore not on conversation for its own sake, but on building a planning-native intelligence layer that can be queried, explored, and cited. Natural language is simply one way of accessing that layer, not the defining feature.

This distinction is subtle but important. We are less interested in whether a system can “sound right” and more concerned with whether it can be right in context .

### Human Accountability as a Design Principle

Every planning application, report, or submission ultimately bears a human name. That name carries professional and legal responsibility.

A planning tool that blurs this line, by presenting AI outputs as authoritative or self-sufficient, undermines professional practice rather than supporting it.

For this reason, Eireplan is designed to reinforce, not dilute, accountability. It makes sources explicit, assumptions visible, and gaps identifiable. It does not hide complexity behind fluent prose.

In doing so, it aligns with how experienced planners already work: assembling evidence, interpreting policy, exercising judgement, and standing over their conclusions.

### A Measured View of What Comes Next

There is genuine potential for AI to improve how planning knowledge is accessed and applied. The pressures facing the Irish planning system, volume, complexity, time constraints, are real and well-documented. Tools that reduce friction without compromising rigour are not a luxury; they are increasingly necessary.

But progress in this space will be incremental, not spectacular. It will come from careful integration into professional workflows, respect for regulatory realities, and a clear understanding of where automation ends and judgement begins.

Eireplan is being built with that restraint in mind.

We are not trying to replace planners, override decision-makers, or short-circuit due process. We are building infrastructure: a knowledge engine that reflects how planning actually works, and that supports professionals in doing their work with greater clarity, confidence, and accountability.

In a system as consequential as planning, that is ambition enough.

Share

### Read More

May 19, 2026

April 10, 2026

March 24, 2026

March 17, 2026

February 5, 2026

On this page

Share

### Ready to start using EirePlan?

Create your account and start working in a planning-native workspace for Irish planning teams.

Get Access Get access

---

# Page 14: St Stephen's Green Shopping Centre — a real site workspace, opened up

Source URL: https://eireplan.com/case-study/stephens-green

Skip to main content

A real workspace, opened up. Sites are normally private to the team that creates them.

Create your own

Every application, date, decision and appeal reference on this page is from the public planning register, read on 10 August 2026. Basemap © OpenStreetMap contributors, rendered with Protomaps.

---

# Page 15: Eireplan Cookie Policy - Eireplan

Source URL: https://eireplan.com/cookies

Skip to main content

##### Eireplan Cookie Policy

What Eireplan stores on your device, why, and how to control it. Nothing outside the strictly necessary set loads until you have accepted it.

This Privacy Policy was published on 31 August 2026

Version: cookies-2026-08-31 Last updated: 31 August 2026 Contact: privacy@eireplan.ie

### The short version

We do not track you. There is no advertising cookie, no analytics cookie, no tracking pixel and no third party script on this website.

The only things we store on your device are the ones the site cannot work without: keeping you signed in, and protecting your session against forgery. Because there is nothing optional, there is nothing to consent to, and that is why you are not shown a cookie banner.

If you are not signed in, we store nothing on your device at all.

### Why there is no banner

Regulation 5 of the European Communities (Electronic Communications Networks and Services) (Privacy and Electronic Communications) Regulations 2011 requires your prior consent before anything is stored on, or read from, your device. It contains one exception: storage that is strictly necessary to provide a service you have expressly requested.

Everything we store falls inside that exception. A banner asking permission for something we are not doing would be noise, and worse, it would train you to click through consent requests without reading them.

This is a deliberate position rather than an oversight. We previously loaded a product analytics tool that set a tracking identifier on every visitor. We removed it.

### What we store

Name What it does Type Expires

Firebase authentication tokens Keeps you signed in and protects your session. Written only after you sign in First party, local storage and cookie Until you sign out, refreshed during use

Session and anti-forgery tokens Stops a third party site making requests as you First party cookie End of session

That is the complete list. If it changes, this table changes with it, and if anything optional is ever added, a consent banner comes back before it loads.

### Third party resources

Loading a font, a script or an image from another company's server discloses your IP address to that company, even when no cookie is involved. An IP address is personal data, so this needs a lawful basis in the same way a cookie does. It is the part of cookie compliance most sites miss.

We serve every font, stylesheet and script from our own domain. Visiting our pages tells no third party anything about you.

Maps are drawn from tiles we host ourselves. If you search for an address while signed in, that address is sent to a geocoding provider so it can be found on the map. That happens only when you actively search, it is necessary to perform the search you asked for, and it is described in section 6 of the Privacy Policy.

### How we understand usage instead

We still need to know which parts of the product are used, in order to improve them. We do that on our servers, from requests you have already sent us as a signed-in customer, rather than by placing anything on your device.

This is a better arrangement for both of us. It requires no banner, it cannot be broken by an ad blocker, and the data never leaves our infrastructure. It is covered by section 3 of the Privacy Policy, under legitimate interests, and you can object to it there.

Anonymous visitors to this website are not measured individually at all.

### Your browser controls

You can clear cookies and site data at any time in your browser settings. Doing so will sign you out, because the sign-in token is one of the things stored.

Because we set nothing that requires consent, "Do Not Track" and Global Privacy Control signals do not change what we do. There is nothing for them to switch off.

### Changes to this policy

If we ever add something that requires consent, we will update the tables above, raise the version identifier at the top, and ask for your consent before that thing loads for the first time. Not afterwards.

### Contact

Questions about this policy: privacy@eireplan.ie

You may also complain to the Data Protection Commission, 6 Pembroke Row, Dublin 2, D02 X963, Ireland, at www.dataprotection.ie .

---

# Page 16: Eireplan Data Processing Terms - Eireplan

Source URL: https://eireplan.com/data-processing

Skip to main content

##### Eireplan Data Processing Terms

The Article 28 terms that apply when you upload personal data about other people into Eireplan. Incorporated into the Terms of Service, so no separate agreement is needed.

This Terms of Service was published on 31 August 2026

Version: dpa-2026-08-31 Last updated: 31 August 2026 Contact: privacy@eireplan.ie

These Data Processing Terms form part of the Terms of Service and satisfy Article 28(3) of the General Data Protection Regulation. They apply automatically, with no separate signature, whenever you upload or enter personal data about other people into EirePlan.

You do not need to negotiate a separate data processing agreement with us. If your organisation requires one on its own paper, contact privacy@eireplan.ie .

### 1. When these terms apply, and who is who

Planning work involves other people's personal data. An application names an applicant. A submission names an objector. A report names a neighbour, a landowner, a consultant. When you put that material into EirePlan, two roles arise:

- You are the controller. You decide why the data is there and what happens to it. You are responsible for having a lawful basis, for telling those people what you are doing through your own privacy notice, and for the accuracy of what you upload.

- We are the processor. We hold and process it on your behalf, and only as you instruct.

Where we process personal data about you as our customer, for example your account, your billing and your use of the platform, we are the controller and the Privacy Policy applies instead. These terms do not cover that.

Where we process the public planning register for our own purposes, we are the controller of that processing, on the basis set out in section 15 of the Privacy Policy. These terms do not cover that either, and nothing here makes you responsible for it.

### 2. Our instructions

We will process personal data only on your documented instructions, which are:

- The Terms of Service and these terms.

- Your use of the platform's features, which is itself an instruction to carry out the processing that feature performs.

- Any further written instruction you give us that we agree to.

This includes transfers to a third country, which are covered by section 7.

If we are required by European Union or Irish law to process personal data other than on your instructions, we will tell you before doing so, unless that law prohibits us from telling you.

We will tell you if, in our opinion, an instruction infringes data protection law. We may suspend the instruction until it is resolved. We are not obliged to give you legal advice, and telling you is not a warranty that your other instructions comply.

### 3. Confidentiality

We will keep personal data confidential. Everyone we authorise to process it is bound by a duty of confidentiality that survives the end of their engagement, and is given access only to what their role requires.

### 4. Security

We implement the technical and organisational measures set out in Annex 2, which are appropriate to the risk under Article 32. We may change them, provided the level of protection is not reduced.

You are responsible for the security decisions within your control, including who you invite into your organisation, what role you give them, the strength of your own credentials, and the security of the devices you use.

### 5. Sub-processors

You give general authorisation for us to engage sub-processors. The current list is in Annex 3, and it is the same list published in the Privacy Policy.

We will give at least 30 days notice in the Privacy Policy before adding or replacing a sub-processor. You may object on reasonable data protection grounds within that period by writing to privacy@eireplan.ie . If we cannot resolve your objection, you may terminate the affected part of the service and receive a pro rata refund of fees paid in advance. Continuing to use the service after the notice period is acceptance.

We impose data protection obligations on each sub-processor that are no less protective than these terms, and we remain fully liable to you for their performance.

### 6. Helping you meet your obligations

Data subject requests. If a person contacts us directly about data you control, we will not respond substantively. We will tell you promptly and leave the response to you. Taking into account the nature of the processing, we will help you respond, by providing the tools in the platform to search, export, correct and delete, and by reasonable further assistance where the tools are not enough.

Breach notification. If we become aware of a personal data breach affecting data we process for you, we will tell you without undue delay, and in any event within 48 hours of becoming aware. We will give you the information you need to meet your own obligation under Article 33, including the nature of the breach, the categories and approximate number of people and records affected, the likely consequences, and the measures taken. We will not notify your supervisory authority or your data subjects on your behalf unless you ask us to in writing.

Impact assessments. We will give you reasonable assistance with data protection impact assessments and prior consultations under Articles 35 and 36, as they relate to our processing.

### 7. International transfers

Personal data you upload is stored in Ireland and processed by applications running in Belgium.

Some sub-processors in Annex 3 operate from outside the European Economic Area. For each of those, transfers are made under the European Commission's Standard Contractual Clauses, incorporated by reference into our agreement with that sub-processor and into these terms, and where applicable under the EU to US Data Privacy Framework. We have carried out transfer impact assessments and apply supplementary measures including encryption in transit and minimisation of what is sent.

Where the Standard Contractual Clauses apply between you and us, Module Two, controller to processor, applies, the governing law is Irish law, the forum is the courts of Ireland, and the annexes to those clauses are the annexes below.

### 8. Deletion and return

You can export your data from the platform at any time.

On termination, we will make your data available for export for 30 days. After that period we will delete it, including from our systems and those of our sub-processors, within a further 30 days, except to the extent that European Union or Irish law requires us to keep it, in which case we will keep it only for as long as required and will continue to protect it under these terms.

Encrypted backups are overwritten on a rolling cycle of up to 30 days. Data in a backup is not restored to live systems after deletion.

We will confirm deletion in writing on request.

### 9. Audit

We will make available the information reasonably necessary to demonstrate compliance with Article 28, and will contribute to audits.

In practice, we will first provide written responses to a reasonable security questionnaire, and any current certifications or reports we hold. If that is genuinely insufficient for you to meet a regulatory obligation, you may audit us, on 30 days written notice, no more than once a year unless a regulator requires otherwise or a breach has occurred, during business hours, subject to confidentiality, without access to other customers' data, and at your cost.

### 10. Liability

Liability under these terms is subject to the limitations in clause 20 of the Terms of Service, except where that is not permitted by Article 82 or by the Standard Contractual Clauses, which give data subjects rights that no contract between us can limit.

Nothing in these terms limits a data subject's right to compensation, or a supervisory authority's powers.

### 11. Order of precedence

Where these terms conflict with the Terms of Service on the subject of processing personal data on your behalf, these terms prevail. Where they conflict with the Standard Contractual Clauses, those clauses prevail.

### Annex 1: Details of the processing

Subject matter. Provision of the EirePlan planning platform.

Duration. For as long as your account is open, plus the deletion periods in section 8.

Nature and purpose. Hosting, storage, organisation, retrieval, indexing, search, structuring, analysis, text extraction from documents, AI assisted summarisation and drafting, report generation, backup, and support, all in order to provide the platform to you.

Types of personal data. Determined by what you upload. Typically: names, postal addresses, eircodes, email addresses, telephone numbers, professional roles and affiliations, signatures, correspondence, and any personal data contained within planning documents, drawings, reports, submissions and decisions.

Categories of data subject. Applicants, agents, architects, engineers, consultants, objectors and observers, neighbours and third parties named in submissions, landowners, your own staff, and your clients.

Special category data. Not expected. The platform is not designed for it and you should not upload it. If you do, you remain responsible for the additional conditions in Articles 9 and 10.

### Annex 2: Technical and organisational measures

Encryption. TLS for all data in transit. Encryption at rest for the database, file storage and backups.

Access control. Multi-factor authentication on production systems. Role based access within the platform at organisation and project level. Administrative access limited to those who require it and logged. Credentials and secrets held in a managed secret store, never in source control.

Separation. Customer data is separated by organisation and project, enforced in the application layer, which is the only path to the database. The database denies direct access by default and is not reachable from the public internet by client applications.

Resilience and recovery. Managed database with point in time recovery. Automated backups retained on a rolling cycle. Infrastructure defined in code so that services can be rebuilt.

Monitoring. Application and access logging, error reporting, and automated dependency vulnerability alerts.

Development. Code review before merge, automated testing and build checks, and separated preproduction and production deployments.

People. Access limited to the smallest number of people necessary, each bound by confidentiality.

Vulnerability reporting. A published contact at security@eireplan.ie and a commitment not to pursue good faith researchers.

### Annex 3: Sub-processors

Sub-processor Purpose Location

Supabase, on Amazon Web Services Database and file storage Ireland

Google Cloud Platform Application hosting Belgium

Google Firebase Authentication Identity and sign-in European Union and United States

Cloudflare Website delivery, DNS, network protection Global edge network

OpenRouter Routing to large language model providers United States

OpenAI Text embeddings for search United States

Resend Transactional email United States

Stripe Payment processing Ireland and United States

Google Maps Platform Geocoding of addresses you search United States

Product usage is measured on our own servers rather than by a third party analytics provider, so no analytics processor appears in this list.

---

# Page 17: Where Irish planning and site data comes from

Source URL: https://eireplan.com/data-sources

Skip to main content

## Where Irish planning and site data comes from

The EirePlan data layer

## 35 source feeds.

One clear view.

Ireland's planning data is fragmented. EirePlan brings it together into a consistent, traceable evidence layer built for faster site decisions.

35

distinct feeds across 6 intelligence layers

From record to signal

Collected

Disconnected records assembled around a site.

Normalised

Different formats resolved into one consistent model.

Traceable

Source and vintage retained with every result.

01

#### Local authority planning registers

Application references, descriptions, dates, decisions and document links published by all 31 planning authorities.

02

#### Development plans & zoning

Published plan areas, zoning context and policy references relevant to a site's planning setting.

03

#### Residential Zoned Land Tax maps

The published final-map parcels, used to show whether a site sits inside the tax's scope.

04

#### Building control records

Published commencement and completion notices that distinguish permission from delivery activity.

05

#### Property Price Register

Residential sales filed for stamp-duty purposes since 2010, used as county-level market context.

01

#### Geological Survey Ireland

Published aquifer, karst, landslide, geomorphology, physiography and survey-coverage mapping. Landslide susceptibility is queried per site rather than mirrored.

02

#### Environmental Protection Agency

Radon risk areas, strategic noise contours, licensed industrial and waste facilities, and water-framework status.

03

#### Urban wastewater capacity

Published treatment-plant and agglomeration records, used for early service-capacity screening.

01

#### National Monuments Service

Recorded monuments and Sites and Monuments Record zones, used for proximity and overlap findings.

02

#### National Inventory of Architectural Heritage

Surveyed buildings of architectural interest near a site.

03

#### Protected structures & conservation areas

Record of Protected Structures and Architectural Conservation Areas, where the authority publishes them.

01

#### Tailte Éireann cadastral parcels

Registered parcels and their freehold or leasehold tenure, fetched for a site when asked, to show how a boundary sits against title.

01

#### CSO Census 2022

Small-area and electoral-division statistics on population, housing, tenure, commuting and work.

02

#### Pobal HP Deprivation Index

The published relative and absolute affluence-deprivation measures for every electoral division.

01

#### National airfields & ports

Published airfield and port locations, used for distance findings around a site.

The result

### Evidence you can move on.

One address brings planning history, mapped context, infrastructure and movement into focus.

Get access

---

# Page 18: EirePlan API documentation

Source URL: https://eireplan.com/docs

Skip to main content

API Reference

API Reference EirePlan for developers

### Your first call

How authentication works

Every request carries your key as a bearer token against the https://api.eireplan.ie base. Keys are self-serve from the hub.

cURL

curl https://api.eireplan.ie /ext/v1/precedents/site-history \ -H "Authorization: Bearer $EIREPLAN_API_KEY" \ -G -d eircode= D06X285 -d radius_m= 250

### Every route

Relative to https://api.eireplan.ie /ext/v1 .

- GET /precedents Search the register

- GET /precedents/{id} One application in full

- GET /precedents/site-history Everything around a point

- POST /precedents/site-history/polygon Everything inside a boundary

- GET /precedents/site-history/report.pdf The finished report

- GET /knowledge/docs The policy library

- GET /local-authority Which council a site falls in

Introduction

- Getting Started

Authentication

Endpoints

- Precedents API

- Knowledge API

- Local Authority Lookup

Something missing or wrong? support@eireplan.ie

---

# Page 19: Authentication — EirePlan API docs

Source URL: https://eireplan.com/docs/authentication

Skip to main content

API Reference

API Reference EirePlan for developers

All external API endpoints use Bearer token authentication.

### # Base URL

https://api.eireplan.ie

### # Authorization Header

http

Authorization : Bearer ek_your_api_key_here

### # Example Request

curl "https://api.eireplan.ie/ext/v1/knowledge/docs?limit=10" \ -H "Authorization: Bearer ek_your_api_key_here"

### # Best Practices

- Keep keys server-side where possible.

- Never embed production keys in public frontend code.

- Rotate keys if exposed.

- Use separate keys per environment and integration.

---

# Page 20: Knowledge API — EirePlan API docs

Source URL: https://eireplan.com/docs/endpoints-knowledge

Skip to main content

API Reference

API Reference EirePlan for developers

Use the knowledge API to discover planning policy documents, guidelines, and related reference material across Ireland. This API is designed for integrations that need to search the knowledge base first and then inspect one document in more detail.

### # What This API Covers

- National, regional, and local planning policy documents.

- Filterable document discovery by jurisdiction, document type, and policy domain.

- Direct follow-up requests for full document metadata and resource links.

### # Resource Shape

The core resource is a knowledge document under /ext/v1/knowledge/docs .

- Use the list request to browse and filter the document catalog.

- Use the detail request when you already have a doc_id .

- Expect document metadata to be returned under fields like metadata.document_title , metadata.document_type , and metadata.current_status .

### # Requests In This API

Request Method Path What it does

List Knowledge Docs GET /ext/v1/knowledge/docs Search and filter the knowledge base with pagination.

Get Knowledge Document GET /ext/v1/knowledge/docs/:docId Fetch one document with full metadata and resource links.

### # Typical Workflow

- Call List Knowledge Docs with filters such as jurisdiction or policy_domain .

- Read the returned doc_id from the matching result.

- Call Get Knowledge Document with that doc_id to retrieve the complete record.

### # Shared Response Patterns

Field or pattern Meaning

doc_id Stable document identifier you can reuse for follow-up requests.

metadata.* Structured policy document metadata.

base_url Official external source page for the document.

pdf_url Direct PDF link when available on detail responses.

limit , offset , has_more Pagination hints on list responses.

### # Example Sequence

bash

curl "https://api.eireplan.ie/ext/v1/knowledge/docs?jurisdiction=National&limit=5" \ -H "Authorization: Bearer ek_your_api_key_here"

Use one of the returned doc_id values to continue with:

bash

curl "https://api.eireplan.ie/ext/v1/knowledge/docs/7af4c2d9-87ea-4887-8d8f-95e20b25a1a5" \ -H "Authorization: Bearer ek_your_api_key_here"

Continue to the request pages above for parameter-by-parameter detail and full response schemas.

---

# Page 21: EirePlan — the public record for sites in Ireland

Source URL: https://eireplan.com/docs/endpoints-knowledge-detail

Skip to main content

D26B/0196/WEB

18 Greenfield Road, Mount Merrion, Dublin

LA DLR In Progress 2026

ED26/0024

42 Knockmeenagh Road, Clondalkin, D22

LA SDCC Refuse 2026

2660154

Griffinstown Kinnegad, Mullingar, Co. Westmeath

LA Westmeath In Progress 2026

2660202

Ballycullane Beg, Dungarvan, Co. Waterford

LA Waterford In Progress 2026

REF3626

Athgarvan, 41 Stillorgan Park, Blackrock, Dublin

LA DLR Refuse 2026

22646

Killarney, Co. Kerry

LA Kerry In Progress 2026

ED26/0022

16 Somerton View, Newcastle Road, Lucan, Dublin

LA SDCC Refuse 2026

SDZ25A/0031W

Dodsborough Cottages, Tandy's Lane, Adamstown, Lucan

LA SDCC Refuse 2025

LA Donegal LA Limerick LA Cork City LA Tipperary LA Mayo LA Waterford LA Kilkenny LA Sligo

## The public record for sites in Ireland.

Planning history, mapped ground context, services and transport, brought together around an address — with provenance for every result.

See how it works ↓

Everything you would want to know about a site is already public. It is just scattered across dozens of registers that were never built to talk to each other. We bring them together against one address, and show where every figure came from.

“

The planning data integrated seamlessly into our platform, and it’s become a core part of how we give sellers and buyers a clear view of a property.

Speed-Deed · in production since 2026

See the API they built on →

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

### Public records and mapped context,

resolved to one address.

Planning, ground, water, heritage, land and people. 35 source feeds, with source and vintage made clear.

© OpenStreetMap contributors

Case study

### St Stephen’s Green Shopping Centre

Thirteen applications since 2019. Seven granted, three refused, five carried to An Coimisiún Pleanála. The whole record, in one workspace.

Open the site

A real workspace, opened up. No account needed.

The agent

### Every site comes with a stack of paperwork.

Ask, and it does the reading.

It finds the applications that matter, opens the documents, and tells you what they say — and where it found it.

#### It reads the actual documents

One application can run to dozens of files. Ask why something was refused and it opens them, finds the passage, and gives it to you word for word with the page it came from.

#### It answers what a filter can't

What keeps getting refused around here? How long does this council really take? It works the question out, then shows you how it got there.

“What keeps getting refused on streets like this one?”

analytics_query

select refusal_ground, count (*) from decisions where authority = … group by 1

Read-only. It shows you the query it ran.

#### It already knows which site you mean

Open a site or an application and it is right there, working on that one file. No re-explaining where you are or pasting references back to it.

14 Oakley Road, Ranelagh

LA DCC 4 applications

Overview History Documents

Working on this site

Ask about this site…

Who uses it

Land and development teams Screening a pipeline of sites before bidding — what has been tried here, and what came back.

Estate and land agents Proving to a buyer what a site can carry, without waiting on a consultant's report.

Solicitors and conveyancers Checking the planning history behind a sale, with the decision notice attached.

Lenders and surveyors Security reviews that need the permission, the conditions and whether it was ever built.

Architects and self-builders Finding what was approved nearby, and the exact conditions that came with it.

Planning consultants Building and defending a case with the precedent and policy that support it, cited.

#### Planning & delivery

- Local authority planning registers

- Development plans & zoning

- Residential Zoned Land Tax maps

- Building control records

- Property Price Register

+ 3 related feeds

#### Ground & environment

- Geological Survey Ireland

- Environmental Protection Agency

- Urban wastewater capacity

+ 12 related feeds

#### Heritage & archaeology

- National Monuments Service

- National Inventory of Architectural Heritage

- Protected structures & conservation areas

+ 2 related feeds

#### Land & tenure

- Tailte Éireann cadastral parcels

#### People & place

- CSO Census 2022

- Pobal HP Deprivation Index

+ 2 related feeds

#### Access & transport

- National airfields & ports

+ 1 related feeds

Explore data provenance

For developers

### Already have a product?

Put the record inside it.

Everything on this page is a REST call away: search, decision detail, planning history around a point or a boundary, the policy library, and which authority a site falls in.

Read the docs Get an API key

One call, the whole site An eircode, an address or coordinates. Back comes every application on and around that site: references, decisions, dates, and the documents behind them.

Or skip to the finished report Ask the same endpoint for a PDF and hand your customer a complete planning-history report.

Keys are self-serve from the hub. Calls are metered against your plan’s credits.

cURL

1

2

3

4

5

6

7

8

# Every application on and around one site.

curl -G https://api.eireplan.ie/ext/v1/precedents/site-history \

-H "Authorization: Bearer $EIREPLAN_API_KEY" \

-d eircode= D06X285 \

-d radius_m= 250

# Same path ending in /report.pdf returns the finished PDF.

GET /ext/v1/precedents/site-history api.eireplan.ie

---

# Page 22: EirePlan — the public record for sites in Ireland

Source URL: https://eireplan.com/docs/endpoints-knowledge-list

Skip to main content

D26B/0196/WEB

18 Greenfield Road, Mount Merrion, Dublin

LA DLR In Progress 2026

ED26/0024

42 Knockmeenagh Road, Clondalkin, D22

LA SDCC Refuse 2026

2660154

Griffinstown Kinnegad, Mullingar, Co. Westmeath

LA Westmeath In Progress 2026

2660202

Ballycullane Beg, Dungarvan, Co. Waterford

LA Waterford In Progress 2026

REF3626

Athgarvan, 41 Stillorgan Park, Blackrock, Dublin

LA DLR Refuse 2026

22646

Killarney, Co. Kerry

LA Kerry In Progress 2026

ED26/0022

16 Somerton View, Newcastle Road, Lucan, Dublin

LA SDCC Refuse 2026

SDZ25A/0031W

Dodsborough Cottages, Tandy's Lane, Adamstown, Lucan

LA SDCC Refuse 2025

LA Donegal LA Limerick LA Cork City LA Tipperary LA Mayo LA Waterford LA Kilkenny LA Sligo

## The public record for sites in Ireland.

Planning history, mapped ground context, services and transport, brought together around an address — with provenance for every result.

See how it works ↓

Everything you would want to know about a site is already public. It is just scattered across dozens of registers that were never built to talk to each other. We bring them together against one address, and show where every figure came from.

“

The planning data integrated seamlessly into our platform, and it’s become a core part of how we give sellers and buyers a clear view of a property.

Speed-Deed · in production since 2026

See the API they built on →

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

### Public records and mapped context,

resolved to one address.

Planning, ground, water, heritage, land and people. 35 source feeds, with source and vintage made clear.

© OpenStreetMap contributors

Case study

### St Stephen’s Green Shopping Centre

Thirteen applications since 2019. Seven granted, three refused, five carried to An Coimisiún Pleanála. The whole record, in one workspace.

Open the site

A real workspace, opened up. No account needed.

The agent

### Every site comes with a stack of paperwork.

Ask, and it does the reading.

It finds the applications that matter, opens the documents, and tells you what they say — and where it found it.

#### It reads the actual documents

One application can run to dozens of files. Ask why something was refused and it opens them, finds the passage, and gives it to you word for word with the page it came from.

#### It answers what a filter can't

What keeps getting refused around here? How long does this council really take? It works the question out, then shows you how it got there.

“What keeps getting refused on streets like this one?”

analytics_query

select refusal_ground, count (*) from decisions where authority = … group by 1

Read-only. It shows you the query it ran.

#### It already knows which site you mean

Open a site or an application and it is right there, working on that one file. No re-explaining where you are or pasting references back to it.

14 Oakley Road, Ranelagh

LA DCC 4 applications

Overview History Documents

Working on this site

Ask about this site…

Who uses it

Land and development teams Screening a pipeline of sites before bidding — what has been tried here, and what came back.

Estate and land agents Proving to a buyer what a site can carry, without waiting on a consultant's report.

Solicitors and conveyancers Checking the planning history behind a sale, with the decision notice attached.

Lenders and surveyors Security reviews that need the permission, the conditions and whether it was ever built.

Architects and self-builders Finding what was approved nearby, and the exact conditions that came with it.

Planning consultants Building and defending a case with the precedent and policy that support it, cited.

#### Planning & delivery

- Local authority planning registers

- Development plans & zoning

- Residential Zoned Land Tax maps

- Building control records

- Property Price Register

+ 3 related feeds

#### Ground & environment

- Geological Survey Ireland

- Environmental Protection Agency

- Urban wastewater capacity

+ 12 related feeds

#### Heritage & archaeology

- National Monuments Service

- National Inventory of Architectural Heritage

- Protected structures & conservation areas

+ 2 related feeds

#### Land & tenure

- Tailte Éireann cadastral parcels

#### People & place

- CSO Census 2022

- Pobal HP Deprivation Index

+ 2 related feeds

#### Access & transport

- National airfields & ports

+ 1 related feeds

Explore data provenance

For developers

### Already have a product?

Put the record inside it.

Everything on this page is a REST call away: search, decision detail, planning history around a point or a boundary, the policy library, and which authority a site falls in.

Read the docs Get an API key

One call, the whole site An eircode, an address or coordinates. Back comes every application on and around that site: references, decisions, dates, and the documents behind them.

Or skip to the finished report Ask the same endpoint for a PDF and hand your customer a complete planning-history report.

Keys are self-serve from the hub. Calls are metered against your plan’s credits.

cURL

1

2

3

4

5

6

7

8

# Every application on and around one site.

curl -G https://api.eireplan.ie/ext/v1/precedents/site-history \

-H "Authorization: Bearer $EIREPLAN_API_KEY" \

-d eircode= D06X285 \

-d radius_m= 250

# Same path ending in /report.pdf returns the finished PDF.

GET /ext/v1/precedents/site-history api.eireplan.ie

---

# Page 23: Local Authority Lookup — EirePlan API docs

Source URL: https://eireplan.com/docs/endpoints-local-authority

Skip to main content

API Reference

API Reference EirePlan for developers

Resolve a location to the Irish local authority whose statutory area contains it.

The answer comes from a point-in-polygon test against the statutory administrative
boundaries, not from proximity to nearby planning applications — so it is exact,
including for sites close to a council boundary.

### # Request

GET /ext/v1/local-authority

Supply either a coordinate pair or an eircode or an address.

### # Query Parameters

Parameter Type Required Description

lat number Conditional Latitude in WGS84 (EPSG:4326). Must be sent together with lon .

lon number Conditional Longitude in WGS84 (EPSG:4326). Must be sent together with lat .

eircode string Conditional Irish eircode, with or without the inner space. Matched exactly — eircodes are not fuzzy-matched.

address string Conditional Free-text address, geocoded before lookup.

Coordinates are the cheapest and most precise input: they are used as given. An eircode or address is geocoded first, which introduces the geocoder's own
positional error.

### # Example Request

curl "https://api.eireplan.ie/ext/v1/local-authority?lat=53.4597&lon=-6.2181" \ -H "Authorization: Bearer ek_your_api_key_here"

### # Response Structure

Field Type Description

local_authority string Authority name, e.g. Fingal County Council .

la_code string Stable machine-readable code, e.g. fingal . Prefer this for storage and comparisons.

lat number Latitude actually used for the lookup.

lon number Longitude actually used for the lookup.

formatted_address string Present only when an eircode or address was geocoded.

approximate boolean true when the point fell outside every boundary and was matched to the nearest authority within ~500 m instead. See below.

vintage string The boundary set used, e.g. 2024 .

source string Attribution for the underlying dataset.

### # Example Response

json

{ "local_authority" : "Fingal County Council" , "la_code" : "fingal" , "lat" : 53.4597 , "lon" : -6.2181 , "approximate" : false , "vintage" : "2024" , "source" : "Tailte Éireann — Local Authorities, National Statutory Boundaries, Ungeneralised (2024), CC-BY 4.0" }

### # Authority Codes

There are 31 statutory local authorities. la_code values are lowercase, with no
separators:

carlow , cavan , clare , corkcity , corkcounty , dlr , donegal , dublincity , fingal , galwaycity , galwaycounty , kerry , kildare , kilkenny , laois , leitrim , limerick , longford , louth , mayo , meath , monaghan , offaly , roscommon , sligo , southdublin , tipperary , waterford , westmeath , wexford , wicklow

Note that corkcity and corkcounty , and galwaycity and galwaycounty , are
separate authorities. dlr is Dún Laoghaire–Rathdown; limerick and waterford are the combined city-and-county authorities.

### # What This Endpoint Does Not Tell You

It is not a consenting-body lookup. It answers whose administrative area a
location sits in. The body that actually decides a given application may differ:
appeals go to An Bord Pleanála, strategic infrastructure development goes directly
to An Bord Pleanála under section 37E, and foreshore consents go to MARA.

The boundary set has a date. Boundaries change. Cork City's area was extended
substantially on 31 May 2019, so for a location in that area the 2024 boundaries
return Cork City Council even though an application decided there before that date
was decided by Cork County Council. Use the vintage field to record which set
produced an answer.

approximate: true deserves a second look. It means the point was not inside
any boundary and was attached to the closest one within roughly 500 m. That
happens legitimately for coastal sites, piers, and reclaimed land, and also when
a geocoded position is slightly off. Treat it as a hint, not a verdict.

### # Errors

Status Meaning

400 No usable location supplied, lat sent without lon (or vice versa), or coordinates that are not valid numbers or out of range.

401 Missing or invalid API key.

422 The eircode or address could not be geocoded, or the location does not fall within any Irish local authority.

504 The upstream geocoder timed out.

This endpoint never guesses. If a location cannot be resolved to an authority it
returns 422 rather than a nearby or likely answer.

### # Attribution

Derived from Tailte Éireann's Local Authorities — National Statutory Boundaries —
Ungeneralised (2024) , licensed under CC-BY 4.0. The source field is returned on
every successful response; retain it, or credit Tailte Éireann, where you surface
the result.

---

# Page 24: Precedents API — EirePlan API docs

Source URL: https://eireplan.com/docs/endpoints-precedents

Skip to main content

API Reference

API Reference EirePlan for developers

Use the precedents API to search planning applications and retrieve full precedent records. This API is useful when you need to discover relevant cases first and then fetch a complete record for one result.

### # What This API Covers

- Search across planning applications and decisions.

- Filter by authority, status, decision, and text query.

- Retrieve a single precedent with richer detail, geometry flags, and official links.

### # Resource Shape

The core resource is a precedent under /ext/v1/precedents .

- Use the search request to find candidate precedents.

- Use the detail request once you have a precedent id .

- Expect search responses to be lighter than detail responses.

### # Requests In This API

Request Method Path What it does

Search Precedents GET /ext/v1/precedents Search and filter precedent records with pagination support.

Site History GET /ext/v1/precedents/site-history Retrieve planning history around an address, eircode, or coordinates.

Site History by Boundary POST /ext/v1/precedents/site-history/polygon Retrieve planning history inside a site boundary you supply as GeoJSON.

Get Precedent Details GET /ext/v1/precedents/:id Fetch one precedent record with full detail and official links.

### # Typical Workflow

- Call Search Precedents with a text query or authority filter.

- If you need nearby planning context for a specific site, call Site History — or Site History by Boundary when you hold the site's extent rather than just its address.

- Capture the returned precedent id .

- Call Get Precedent Details to fetch the full record for that result.

### # Shared Response Patterns

Field or pattern Meaning

id Stable precedent identifier for follow-up requests.

planning_ref Official planning reference from the local authority.

local_authority Responsible council or authority.

decision_norm , status_norm Normalized values for reliable filtering.

next Cursor for the next search page on list responses.

### # Example Sequence

bash

curl "https://api.eireplan.ie/ext/v1/precedents?q=apartment&limit=5" \ -H "Authorization: Bearer ek_your_api_key_here"

Use one of the returned id values to continue with:

bash

curl "https://api.eireplan.ie/ext/v1/precedents/5f8fcb68-2be1-4ce7-8ef4-6a29c2fb4aa8" \ -H "Authorization: Bearer ek_your_api_key_here"

Continue to the request pages above for full parameter references and detailed response schemas.

---

# Page 25: EirePlan — the public record for sites in Ireland

Source URL: https://eireplan.com/docs/endpoints-precedents-detail

Skip to main content

D26B/0196/WEB

18 Greenfield Road, Mount Merrion, Dublin

LA DLR In Progress 2026

ED26/0024

42 Knockmeenagh Road, Clondalkin, D22

LA SDCC Refuse 2026

2660154

Griffinstown Kinnegad, Mullingar, Co. Westmeath

LA Westmeath In Progress 2026

2660202

Ballycullane Beg, Dungarvan, Co. Waterford

LA Waterford In Progress 2026

REF3626

Athgarvan, 41 Stillorgan Park, Blackrock, Dublin

LA DLR Refuse 2026

22646

Killarney, Co. Kerry

LA Kerry In Progress 2026

ED26/0022

16 Somerton View, Newcastle Road, Lucan, Dublin

LA SDCC Refuse 2026

SDZ25A/0031W

Dodsborough Cottages, Tandy's Lane, Adamstown, Lucan

LA SDCC Refuse 2025

LA Donegal LA Limerick LA Cork City LA Tipperary LA Mayo LA Waterford LA Kilkenny LA Sligo

## The public record for sites in Ireland.

Planning history, mapped ground context, services and transport, brought together around an address — with provenance for every result.

See how it works ↓

Everything you would want to know about a site is already public. It is just scattered across dozens of registers that were never built to talk to each other. We bring them together against one address, and show where every figure came from.

“

The planning data integrated seamlessly into our platform, and it’s become a core part of how we give sellers and buyers a clear view of a property.

Speed-Deed · in production since 2026

See the API they built on →

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

### Public records and mapped context,

resolved to one address.

Planning, ground, water, heritage, land and people. 35 source feeds, with source and vintage made clear.

© OpenStreetMap contributors

Case study

### St Stephen’s Green Shopping Centre

Thirteen applications since 2019. Seven granted, three refused, five carried to An Coimisiún Pleanála. The whole record, in one workspace.

Open the site

A real workspace, opened up. No account needed.

The agent

### Every site comes with a stack of paperwork.

Ask, and it does the reading.

It finds the applications that matter, opens the documents, and tells you what they say — and where it found it.

#### It reads the actual documents

One application can run to dozens of files. Ask why something was refused and it opens them, finds the passage, and gives it to you word for word with the page it came from.

#### It answers what a filter can't

What keeps getting refused around here? How long does this council really take? It works the question out, then shows you how it got there.

“What keeps getting refused on streets like this one?”

analytics_query

select refusal_ground, count (*) from decisions where authority = … group by 1

Read-only. It shows you the query it ran.

#### It already knows which site you mean

Open a site or an application and it is right there, working on that one file. No re-explaining where you are or pasting references back to it.

14 Oakley Road, Ranelagh

LA DCC 4 applications

Overview History Documents

Working on this site

Ask about this site…

Who uses it

Land and development teams Screening a pipeline of sites before bidding — what has been tried here, and what came back.

Estate and land agents Proving to a buyer what a site can carry, without waiting on a consultant's report.

Solicitors and conveyancers Checking the planning history behind a sale, with the decision notice attached.

Lenders and surveyors Security reviews that need the permission, the conditions and whether it was ever built.

Architects and self-builders Finding what was approved nearby, and the exact conditions that came with it.

Planning consultants Building and defending a case with the precedent and policy that support it, cited.

#### Planning & delivery

- Local authority planning registers

- Development plans & zoning

- Residential Zoned Land Tax maps

- Building control records

- Property Price Register

+ 3 related feeds

#### Ground & environment

- Geological Survey Ireland

- Environmental Protection Agency

- Urban wastewater capacity

+ 12 related feeds

#### Heritage & archaeology

- National Monuments Service

- National Inventory of Architectural Heritage

- Protected structures & conservation areas

+ 2 related feeds

#### Land & tenure

- Tailte Éireann cadastral parcels

#### People & place

- CSO Census 2022

- Pobal HP Deprivation Index

+ 2 related feeds

#### Access & transport

- National airfields & ports

+ 1 related feeds

Explore data provenance

For developers

### Already have a product?

Put the record inside it.

Everything on this page is a REST call away: search, decision detail, planning history around a point or a boundary, the policy library, and which authority a site falls in.

Read the docs Get an API key

One call, the whole site An eircode, an address or coordinates. Back comes every application on and around that site: references, decisions, dates, and the documents behind them.

Or skip to the finished report Ask the same endpoint for a PDF and hand your customer a complete planning-history report.

Keys are self-serve from the hub. Calls are metered against your plan’s credits.

cURL

1

2

3

4

5

6

7

8

# Every application on and around one site.

curl -G https://api.eireplan.ie/ext/v1/precedents/site-history \

-H "Authorization: Bearer $EIREPLAN_API_KEY" \

-d eircode= D06X285 \

-d radius_m= 250

# Same path ending in /report.pdf returns the finished PDF.

GET /ext/v1/precedents/site-history api.eireplan.ie

---

# Page 26: EirePlan — the public record for sites in Ireland

Source URL: https://eireplan.com/docs/endpoints-precedents-search

Skip to main content

D26B/0196/WEB

18 Greenfield Road, Mount Merrion, Dublin

LA DLR In Progress 2026

ED26/0024

42 Knockmeenagh Road, Clondalkin, D22

LA SDCC Refuse 2026

2660154

Griffinstown Kinnegad, Mullingar, Co. Westmeath

LA Westmeath In Progress 2026

2660202

Ballycullane Beg, Dungarvan, Co. Waterford

LA Waterford In Progress 2026

REF3626

Athgarvan, 41 Stillorgan Park, Blackrock, Dublin

LA DLR Refuse 2026

22646

Killarney, Co. Kerry

LA Kerry In Progress 2026

ED26/0022

16 Somerton View, Newcastle Road, Lucan, Dublin

LA SDCC Refuse 2026

SDZ25A/0031W

Dodsborough Cottages, Tandy's Lane, Adamstown, Lucan

LA SDCC Refuse 2025

LA Donegal LA Limerick LA Cork City LA Tipperary LA Mayo LA Waterford LA Kilkenny LA Sligo

## The public record for sites in Ireland.

Planning history, mapped ground context, services and transport, brought together around an address — with provenance for every result.

See how it works ↓

Everything you would want to know about a site is already public. It is just scattered across dozens of registers that were never built to talk to each other. We bring them together against one address, and show where every figure came from.

“

The planning data integrated seamlessly into our platform, and it’s become a core part of how we give sellers and buyers a clear view of a property.

Speed-Deed · in production since 2026

See the API they built on →

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

### Public records and mapped context,

resolved to one address.

Planning, ground, water, heritage, land and people. 35 source feeds, with source and vintage made clear.

© OpenStreetMap contributors

Case study

### St Stephen’s Green Shopping Centre

Thirteen applications since 2019. Seven granted, three refused, five carried to An Coimisiún Pleanála. The whole record, in one workspace.

Open the site

A real workspace, opened up. No account needed.

The agent

### Every site comes with a stack of paperwork.

Ask, and it does the reading.

It finds the applications that matter, opens the documents, and tells you what they say — and where it found it.

#### It reads the actual documents

One application can run to dozens of files. Ask why something was refused and it opens them, finds the passage, and gives it to you word for word with the page it came from.

#### It answers what a filter can't

What keeps getting refused around here? How long does this council really take? It works the question out, then shows you how it got there.

“What keeps getting refused on streets like this one?”

analytics_query

select refusal_ground, count (*) from decisions where authority = … group by 1

Read-only. It shows you the query it ran.

#### It already knows which site you mean

Open a site or an application and it is right there, working on that one file. No re-explaining where you are or pasting references back to it.

14 Oakley Road, Ranelagh

LA DCC 4 applications

Overview History Documents

Working on this site

Ask about this site…

Who uses it

Land and development teams Screening a pipeline of sites before bidding — what has been tried here, and what came back.

Estate and land agents Proving to a buyer what a site can carry, without waiting on a consultant's report.

Solicitors and conveyancers Checking the planning history behind a sale, with the decision notice attached.

Lenders and surveyors Security reviews that need the permission, the conditions and whether it was ever built.

Architects and self-builders Finding what was approved nearby, and the exact conditions that came with it.

Planning consultants Building and defending a case with the precedent and policy that support it, cited.

#### Planning & delivery

- Local authority planning registers

- Development plans & zoning

- Residential Zoned Land Tax maps

- Building control records

- Property Price Register

+ 3 related feeds

#### Ground & environment

- Geological Survey Ireland

- Environmental Protection Agency

- Urban wastewater capacity

+ 12 related feeds

#### Heritage & archaeology

- National Monuments Service

- National Inventory of Architectural Heritage

- Protected structures & conservation areas

+ 2 related feeds

#### Land & tenure

- Tailte Éireann cadastral parcels

#### People & place

- CSO Census 2022

- Pobal HP Deprivation Index

+ 2 related feeds

#### Access & transport

- National airfields & ports

+ 1 related feeds

Explore data provenance

For developers

### Already have a product?

Put the record inside it.

Everything on this page is a REST call away: search, decision detail, planning history around a point or a boundary, the policy library, and which authority a site falls in.

Read the docs Get an API key

One call, the whole site An eircode, an address or coordinates. Back comes every application on and around that site: references, decisions, dates, and the documents behind them.

Or skip to the finished report Ask the same endpoint for a PDF and hand your customer a complete planning-history report.

Keys are self-serve from the hub. Calls are metered against your plan’s credits.

cURL

1

2

3

4

5

6

7

8

# Every application on and around one site.

curl -G https://api.eireplan.ie/ext/v1/precedents/site-history \

-H "Authorization: Bearer $EIREPLAN_API_KEY" \

-d eircode= D06X285 \

-d radius_m= 250

# Same path ending in /report.pdf returns the finished PDF.

GET /ext/v1/precedents/site-history api.eireplan.ie

---

# Page 27: EirePlan — the public record for sites in Ireland

Source URL: https://eireplan.com/docs/endpoints-precedents-site-history

Skip to main content

D26B/0196/WEB

18 Greenfield Road, Mount Merrion, Dublin

LA DLR In Progress 2026

ED26/0024

42 Knockmeenagh Road, Clondalkin, D22

LA SDCC Refuse 2026

2660154

Griffinstown Kinnegad, Mullingar, Co. Westmeath

LA Westmeath In Progress 2026

2660202

Ballycullane Beg, Dungarvan, Co. Waterford

LA Waterford In Progress 2026

REF3626

Athgarvan, 41 Stillorgan Park, Blackrock, Dublin

LA DLR Refuse 2026

22646

Killarney, Co. Kerry

LA Kerry In Progress 2026

ED26/0022

16 Somerton View, Newcastle Road, Lucan, Dublin

LA SDCC Refuse 2026

SDZ25A/0031W

Dodsborough Cottages, Tandy's Lane, Adamstown, Lucan

LA SDCC Refuse 2025

LA Donegal LA Limerick LA Cork City LA Tipperary LA Mayo LA Waterford LA Kilkenny LA Sligo

## The public record for sites in Ireland.

Planning history, mapped ground context, services and transport, brought together around an address — with provenance for every result.

See how it works ↓

Everything you would want to know about a site is already public. It is just scattered across dozens of registers that were never built to talk to each other. We bring them together against one address, and show where every figure came from.

“

The planning data integrated seamlessly into our platform, and it’s become a core part of how we give sellers and buyers a clear view of a property.

Speed-Deed · in production since 2026

See the API they built on →

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

### Public records and mapped context,

resolved to one address.

Planning, ground, water, heritage, land and people. 35 source feeds, with source and vintage made clear.

© OpenStreetMap contributors

Case study

### St Stephen’s Green Shopping Centre

Thirteen applications since 2019. Seven granted, three refused, five carried to An Coimisiún Pleanála. The whole record, in one workspace.

Open the site

A real workspace, opened up. No account needed.

The agent

### Every site comes with a stack of paperwork.

Ask, and it does the reading.

It finds the applications that matter, opens the documents, and tells you what they say — and where it found it.

#### It reads the actual documents

One application can run to dozens of files. Ask why something was refused and it opens them, finds the passage, and gives it to you word for word with the page it came from.

#### It answers what a filter can't

What keeps getting refused around here? How long does this council really take? It works the question out, then shows you how it got there.

“What keeps getting refused on streets like this one?”

analytics_query

select refusal_ground, count (*) from decisions where authority = … group by 1

Read-only. It shows you the query it ran.

#### It already knows which site you mean

Open a site or an application and it is right there, working on that one file. No re-explaining where you are or pasting references back to it.

14 Oakley Road, Ranelagh

LA DCC 4 applications

Overview History Documents

Working on this site

Ask about this site…

Who uses it

Land and development teams Screening a pipeline of sites before bidding — what has been tried here, and what came back.

Estate and land agents Proving to a buyer what a site can carry, without waiting on a consultant's report.

Solicitors and conveyancers Checking the planning history behind a sale, with the decision notice attached.

Lenders and surveyors Security reviews that need the permission, the conditions and whether it was ever built.

Architects and self-builders Finding what was approved nearby, and the exact conditions that came with it.

Planning consultants Building and defending a case with the precedent and policy that support it, cited.

#### Planning & delivery

- Local authority planning registers

- Development plans & zoning

- Residential Zoned Land Tax maps

- Building control records

- Property Price Register

+ 3 related feeds

#### Ground & environment

- Geological Survey Ireland

- Environmental Protection Agency

- Urban wastewater capacity

+ 12 related feeds

#### Heritage & archaeology

- National Monuments Service

- National Inventory of Architectural Heritage

- Protected structures & conservation areas

+ 2 related feeds

#### Land & tenure

- Tailte Éireann cadastral parcels

#### People & place

- CSO Census 2022

- Pobal HP Deprivation Index

+ 2 related feeds

#### Access & transport

- National airfields & ports

+ 1 related feeds

Explore data provenance

For developers

### Already have a product?

Put the record inside it.

Everything on this page is a REST call away: search, decision detail, planning history around a point or a boundary, the policy library, and which authority a site falls in.

Read the docs Get an API key

One call, the whole site An eircode, an address or coordinates. Back comes every application on and around that site: references, decisions, dates, and the documents behind them.

Or skip to the finished report Ask the same endpoint for a PDF and hand your customer a complete planning-history report.

Keys are self-serve from the hub. Calls are metered against your plan’s credits.

cURL

1

2

3

4

5

6

7

8

# Every application on and around one site.

curl -G https://api.eireplan.ie/ext/v1/precedents/site-history \

-H "Authorization: Bearer $EIREPLAN_API_KEY" \

-d eircode= D06X285 \

-d radius_m= 250

# Same path ending in /report.pdf returns the finished PDF.

GET /ext/v1/precedents/site-history api.eireplan.ie

---

# Page 28: EirePlan — the public record for sites in Ireland

Source URL: https://eireplan.com/docs/endpoints-precedents-site-history-boundary

Skip to main content

D26B/0196/WEB

18 Greenfield Road, Mount Merrion, Dublin

LA DLR In Progress 2026

ED26/0024

42 Knockmeenagh Road, Clondalkin, D22

LA SDCC Refuse 2026

2660154

Griffinstown Kinnegad, Mullingar, Co. Westmeath

LA Westmeath In Progress 2026

2660202

Ballycullane Beg, Dungarvan, Co. Waterford

LA Waterford In Progress 2026

REF3626

Athgarvan, 41 Stillorgan Park, Blackrock, Dublin

LA DLR Refuse 2026

22646

Killarney, Co. Kerry

LA Kerry In Progress 2026

ED26/0022

16 Somerton View, Newcastle Road, Lucan, Dublin

LA SDCC Refuse 2026

SDZ25A/0031W

Dodsborough Cottages, Tandy's Lane, Adamstown, Lucan

LA SDCC Refuse 2025

LA Donegal LA Limerick LA Cork City LA Tipperary LA Mayo LA Waterford LA Kilkenny LA Sligo

## The public record for sites in Ireland.

Planning history, mapped ground context, services and transport, brought together around an address — with provenance for every result.

See how it works ↓

Everything you would want to know about a site is already public. It is just scattered across dozens of registers that were never built to talk to each other. We bring them together against one address, and show where every figure came from.

“

The planning data integrated seamlessly into our platform, and it’s become a core part of how we give sellers and buyers a clear view of a property.

Speed-Deed · in production since 2026

See the API they built on →

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Planning applications

- Commencement notices

- Development plan zoning

- Local area plans

- Plan objective areas

- Council zoning maps

- Residential Zoned Land Tax

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Licensed industrial facilities

- Radon risk areas

- Strategic noise contours

- Wastewater agglomerations

- Wastewater treatment plants

- River catchments

- Water quality pressures

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Waterbody status

- Bedrock aquifers

- Karst landforms

- Landslide records

- Landslide susceptibility

- LiDAR survey coverage

- Physiographic units

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Quaternary geomorphology

- Architectural conservation areas

- Protected structures

- Architectural heritage survey

- Recorded monuments

- Monument protection zones

- Cadastral parcels

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

- Small-area statistics

- Electoral divisions

- Census small areas

- Deprivation index

- Residential sales register

- Airfields

- Ports

### Public records and mapped context,

resolved to one address.

Planning, ground, water, heritage, land and people. 35 source feeds, with source and vintage made clear.

© OpenStreetMap contributors

Case study

### St Stephen’s Green Shopping Centre

Thirteen applications since 2019. Seven granted, three refused, five carried to An Coimisiún Pleanála. The whole record, in one workspace.

Open the site

A real workspace, opened up. No account needed.

The agent

### Every site comes with a stack of paperwork.

Ask, and it does the reading.

It finds the applications that matter, opens the documents, and tells you what they say — and where it found it.

#### It reads the actual documents

One application can run to dozens of files. Ask why something was refused and it opens them, finds the passage, and gives it to you word for word with the page it came from.

#### It answers what a filter can't

What keeps getting refused around here? How long does this council really take? It works the question out, then shows you how it got there.

“What keeps getting refused on streets like this one?”

analytics_query

select refusal_ground, count (*) from decisions where authority = … group by 1

Read-only. It shows you the query it ran.

#### It already knows which site you mean

Open a site or an application and it is right there, working on that one file. No re-explaining where you are or pasting references back to it.

14 Oakley Road, Ranelagh

LA DCC 4 applications

Overview History Documents

Working on this site

Ask about this site…

Who uses it

Land and development teams Screening a pipeline of sites before bidding — what has been tried here, and what came back.

Estate and land agents Proving to a buyer what a site can carry, without waiting on a consultant's report.

Solicitors and conveyancers Checking the planning history behind a sale, with the decision notice attached.

Lenders and surveyors Security reviews that need the permission, the conditions and whether it was ever built.

Architects and self-builders Finding what was approved nearby, and the exact conditions that came with it.

Planning consultants Building and defending a case with the precedent and policy that support it, cited.

#### Planning & delivery

- Local authority planning registers

- Development plans & zoning

- Residential Zoned Land Tax maps

- Building control records

- Property Price Register

+ 3 related feeds

#### Ground & environment

- Geological Survey Ireland

- Environmental Protection Agency

- Urban wastewater capacity

+ 12 related feeds

#### Heritage & archaeology

- National Monuments Service

- National Inventory of Architectural Heritage

- Protected structures & conservation areas

+ 2 related feeds

#### Land & tenure

- Tailte Éireann cadastral parcels

#### People & place

- CSO Census 2022

- Pobal HP Deprivation Index

+ 2 related feeds

#### Access & transport

- National airfields & ports

+ 1 related feeds

Explore data provenance

For developers

### Already have a product?

Put the record inside it.

Everything on this page is a REST call away: search, decision detail, planning history around a point or a boundary, the policy library, and which authority a site falls in.

Read the docs Get an API key

One call, the whole site An eircode, an address or coordinates. Back comes every application on and around that site: references, decisions, dates, and the documents behind them.

Or skip to the finished report Ask the same endpoint for a PDF and hand your customer a complete planning-history report.

Keys are self-serve from the hub. Calls are metered against your plan’s credits.

cURL

1

2

3

4

5

6

7

8

# Every application on and around one site.

curl -G https://api.eireplan.ie/ext/v1/precedents/site-history \

-H "Authorization: Bearer $EIREPLAN_API_KEY" \

-d eircode= D06X285 \

-d radius_m= 250

# Same path ending in /report.pdf returns the finished PDF.

GET /ext/v1/precedents/site-history api.eireplan.ie

---

# Page 29: Getting Started — EirePlan API docs

Source URL: https://eireplan.com/docs/getting-started

Skip to main content

API Reference

API Reference EirePlan for developers

Eireplan API gives you access to planning precedents and policy knowledge endpoints from your own tools.

### # Quick Start

- Create an API key in your Eireplan Hub account under API .

- Store the key securely (it is shown once on creation).

- Send requests to https://api.eireplan.ie/ext/v1/... with a Bearer token.

### # First Request

curl "https://api.eireplan.ie/ext/v1/precedents?limit=5" \ -H "Authorization: Bearer ek_your_api_key_here"

### # Response Format

Most list endpoints return objects with:

- items or resource arrays

- pagination hints (for endpoints that support pagination)

- stable IDs you can use for detail endpoints

Continue with Authentication and Endpoints to implement your integration end to end.

---

# Page 30: What EirePlan does: map, sites and precedent search

Source URL: https://eireplan.com/features

Skip to main content

Features

## Three ways into the same record.

All of it public, all of it cited.

Ireland's planning record is published across thirty-one registers and dozens of national datasets. These are the three places you actually work with it.

Map

### Every application in Ireland, in context

Zoning and precedent view modes, layer toggles, amenities, and drawing and measurement tools — over our own Ireland basemap.

Take a look

Sites

### One workspace per place, in order

A site outlives its applications. Everything ever proposed here, the documents behind it, and the ground it sits on.

Take a look

Precedent search

### Search every authority, then read why

Filter by authority, decision, status and type across the whole register — then open the council's own documents behind any result.

Take a look

### Or just go and look at the data.

A full site is open to the public, and the precedent browser needs no account.

Open the site See how it works

---

# Page 31: Irish planning application map — zoning and boundaries

Source URL: https://eireplan.com/features/map

Skip to main content

Map

## Every application in Ireland.

On one map.

Planning history is published as thirty-one separate registers, none of which draw you a picture. The map puts them in one place, over our own Ireland basemap, so you can see what has been tried on a site and everything around it.

Real application outlines over our Ireland basemap. Basemap © OpenStreetMap contributors, rendered with Protomaps.

### Not a locator. A workspace.

The map carries the analysis tools the work actually needs, rather than a pin and a zoom control.

#### Zoning and precedent, as view modes

Switch the base map between zoning and precedent views, and toggle the layers you need — nearby amenities included — instead of opening three tabs.

#### Draw it and measure it

Drawing and measurement tools on the map itself, so a site area or a separation distance is something you check rather than estimate.

Source Licence As at

National planning application database CC-BY 4.0 10 Aug 2026

An Coimisiún Pleanála — appeals CC-BY 4.0 09 Aug 2026

Tailte Éireann — LA boundaries CC-BY 4.0 2024 vintage

BCMS — commencement notices CC-BY 4.0 08 Aug 2026

EPA — strategic noise, round 4 CC-BY 4.0 20 Aug 2026

Geological Survey Ireland — bedrock CC-BY 4.0 02 Aug 2026

EPA — radon risk mapping CC-BY 4.0 02 Aug 2026

National Monuments Service — SMR CC-BY 4.0 28 Jul 2026

CSO — Census 2022 small areas CC-BY 4.0 14 Jul 2026

EPA — waste water treatment capacity CC-BY 4.0 05 Aug 2026

### Search by eircode, address, or a radius you draw

Point at a site and get its planning history back — with verification mapping showing exactly what was matched, and a report you can export and send on.

Eircode Exact match only. Irish eircodes are not a range — an adjacent code is not an adjacent place, so nothing here guesses.

Address Geocoded to a point, then resolved against the statutory local-authority boundary rather than the nearest record.

Area radius Draw the area you care about and take everything inside it, for sites a point does not describe.

### Open a real one.

St Stephen's Green Shopping Centre, with its boundary and its whole application history, is open to the public. No account needed.

Open the site See how it works

---

# Page 32: Search Irish planning precedents across all 31 authorities

Source URL: https://eireplan.com/features/precedents

Skip to main content

Precedent search

## Find what was decided.

Then read why.

Every authority publishes its decisions, and every one of them publishes differently. Precedent search puts them behind a single query — and, unlike a register, does not stop at the decision line.

first-floor rear extension

1,284 decisions · 31 authorities

3352/25

14 Oakley Road, Ranelagh, Dublin 6

LA DCC Decision Granted Year 2026

D26B/0196

18 Greenfield Road, Mount Merrion

LA Dún Laoghaire-Rathdown County Council Decision Refused Year 2026

ED26/0024

42 Knockmeenagh Road, Clondalkin

LA SDCC Decision Refused Year 2026

### Filters that search the register

Filter by authority, decision category, status, type and watch state. The query runs server-side against everything held, not against the page of results you happen to be looking at.

#### Open the file, not just the row

Each result opens onto a detail panel with a map preview, the planning timeline, schedules, and the raw record — plus the council's own documents behind it.

31 planning registers

LA DCC LA Fingal LA SDCC LA DLR + 27

One record per application

3352/25 14 Oakley Road, Ranelagh, Dublin 6 LA DCC Decision Granted

Read from the file

Condition 7 Decision notice, p.4

“The first-floor rear extension shall be set back a minimum of 1.2 metres from the eastern party boundary, and the window serving it shall be fitted with obscure glazing.” Reason: to protect the residential amenity of adjoining property.

#### Keep the ones that matter

Star a decision to keep it, and hand any result straight into a site history report when it turns out to be the one your case rests on.

first-floor rear extension

1,284 decisions · 31 authorities

3352/25

14 Oakley Road, Ranelagh, Dublin 6

LA DCC Decision Granted Year 2026

D26B/0196

18 Greenfield Road, Mount Merrion

LA Dún Laoghaire-Rathdown County Council Decision Refused Year 2026

ED26/0024

42 Knockmeenagh Road, Clondalkin

LA SDCC Decision Refused Year 2026

### One shape, whatever the register called it

Thirty-one authorities publish thirty-one ways. The work is in making them answer the same question.

Every authority All thirty-one planning authorities, normalised into one shape — the same fields whatever the source register calls them.

Resolved to the right council Sites are matched against the statutory boundary rather than the nearest record, which is a different answer near a boundary.

Named and licensed Every source is listed with its licence on the data-sources page. If a figure is on screen, you can find out where it came from.

### Go and look at the data.

A full site — boundary, thirteen applications, and the documents behind them — is open to the public with no account, if you would rather check the data before taking our word for any of this.

Open the site See the sources

---

# Page 33: Site workspace — every application for one address

Source URL: https://eireplan.com/features/sites

Skip to main content

Sites

## The register is filed by application.

Nobody thinks that way.

A site outlives its applications. It gets refused, redesigned, resubmitted, appealed and sold, and each of those is a separate entry in a register that will not join them up for you. A site in EirePlan is the place — with everything that has ever been proposed on it underneath.

Site record

#### 13 Fownes Street Upper

Temple Bar, Dublin 2 · D02 X066 · 116 m²

This site · 85 applications on screen

2

Applications

1

Appeal

364

Days to grant

Planning history

- Application lodged 4088/22 27 May 2022

- Declared invalid 08 Jun 2022 + 12 days

- Resubmitted 4220/22 14 Jun 2022

- Further information requested 08 Aug 2022

- Further information received 24 Aug 2022 + 16 days

- Permission granted 20 Sep 2022

- Appealed to ACP ABP-314878-22 20 Oct 2022

- Appeal withdrawn 24 May 2023 + 216 days

- Grant issued 26 May 2023

Dublin City Council register · An Coimisiún Pleanála · read 10 Aug 2026

### Everything that happened here, in order

One workspace per site: the boundary, every application against it, the documents behind each one, and the decisions that came back.

#### The context that comes with the ground

Zoning, heritage and protected structures, noise, radon, ground conditions, waste-water capacity and how the area travels — resolved to the site rather than to the county it sits in.

Site report

14 Oakley Road

Ranelagh, Dublin 6

7 Applications

5 Granted

1 Appealed

Zoning & designation

Zoning objective Z2 — Residential

Development plan Dublin City 2022–2028

RZLT final map Not on it

Heritage

SMR zone overlap 37% of site

Nearest monument Holy well, 10 m

NIAH within 1 km 1,793

Environment & ground

Loudest noise band Road, 65–69 dB

Radon risk area 1 in 20 predicted high

Waste water Ringsend, 4.5 km

Getting here

Public transport to work 34%

Households with no car 41%

#### A history you can hand to someone

The whole record as a report — conditions quoted verbatim, the further-information rounds, the planner's reasoning, and the drawings, with a citation on every line.

Site report

D02 X066

13 Fownes Street Upper

Temple Bar, Dublin 2 · 116 m²

2 Applications

1 Appeal

364 Days to grant

Planning history

- Application lodged 4088/22 27 May 2022

- Declared invalid 08 Jun 2022 + 12 days

- Resubmitted 4220/22 14 Jun 2022

- Further information requested 08 Aug 2022

- Further information received 24 Aug 2022 + 16 days

- Permission granted 20 Sep 2022

- Appealed to ACP ABP-314878-22 20 Oct 2022

- Appeal withdrawn 24 May 2023 + 216 days

- Grant issued 26 May 2023

Dublin City Council register · An Coimisiún Pleanála · read 10 Aug 2026

### The councils' own documents, read and quoted

A decision is one line in a register. The reasoning behind it sits in the documents published alongside it, and those get read rather than linked to.

Conditions, verbatim Every condition attached to a permission, quoted as it was written rather than paraphrased, against the decision order it was issued under.

The further-information rounds What was requested, when it was asked and when it came back — the part of a timeline that explains why a decision took as long as it did.

The planner's reasoning The assessment behind the recommendation, and the specific items an Article 33 request turned on, carried back with a citation to the document it came from.

### Thirteen applications, one site.

St Stephen's Green Shopping Centre is open to the public — the boundary, the full history, and the documents behind it.

Open the site Search precedents

---

# Page 34: How EirePlan builds Ireland's planning record

Source URL: https://eireplan.com/how-it-works

Skip to main content

How it works

## Everything about a site is already public.

It is just scattered.

Planning history, ground conditions, services and transport are all published, across 35 sources that were never built to talk to each other. We collect them, resolve them to one address, and keep the source attached to every figure.

- 01

### Collect

Thirty-one planning registers, plus the national datasets for ground, water, services, transport and people. Each on its own schedule, each in its own shape.

- 02

### Normalise

One record per application, carrying the same fields whatever the source register calls them, matched to the statutory authority whose boundary the site sits inside.

- 03

### Open the file

The documents the council published against the application: planner's report, conditions, further-information letters, objections.

- 04

### Answer

Ask a question about a site and get the passage back, with the document and page it came from. Or take the whole record as a report, or over the API.

### What we collect

Every layer here is built from public datasets that are licensed for reuse. Where a published figure exists we use it rather than model one of our own.

Planning and delivery Applications, decisions, appeals and what was actually built.

Ground and environment Geology, aquifers, flood risk, terrain and designations.

Services and capacity Wastewater headroom, grid connections and contracted capacity.

People and movement Population, commuting, transport, schools and energy ratings.

### From thirty-one registers to one record

A register will tell you an application was refused. The reason is in the planner's report and the conditions attached to the decision, which is why those are the files we open.

#### Register in, condition out

Thirty-one registers become one record per application, and then the decision notice sitting behind it, quoted with the page it came from.

31 planning registers

LA DCC LA Fingal LA SDCC LA DLR + 27

One record per application

3352/25 14 Oakley Road, Ranelagh, Dublin 6 LA DCC Decision Granted

Read from the file

Condition 7 Decision notice, p.4

“The first-floor rear extension shall be set back a minimum of 1.2 metres from the eastern party boundary, and the window serving it shall be fitted with obscure glazing.” Reason: to protect the residential amenity of adjoining property.

#### Every figure keeps its source

Each figure on a site page carries the dataset it came from and the date we last read it, so you can check it rather than take it.

Source Licence As at

National planning application database CC-BY 4.0 10 Aug 2026

An Coimisiún Pleanála — appeals CC-BY 4.0 09 Aug 2026

Tailte Éireann — LA boundaries CC-BY 4.0 2024 vintage

BCMS — commencement notices CC-BY 4.0 08 Aug 2026

EPA — strategic noise, round 4 CC-BY 4.0 20 Aug 2026

Geological Survey Ireland — bedrock CC-BY 4.0 02 Aug 2026

EPA — radon risk mapping CC-BY 4.0 02 Aug 2026

National Monuments Service — SMR CC-BY 4.0 28 Jul 2026

CSO — Census 2022 small areas CC-BY 4.0 14 Jul 2026

EPA — waste water treatment capacity CC-BY 4.0 05 Aug 2026

### Named, licensed, and listed

Everything we hold, and where each family of it comes from. If you have to stand over a figure in front of a planner or a client, you can point at its source.

#### Planning & delivery

- Local authority planning registers

- Development plans & zoning

- Residential Zoned Land Tax maps

- Building control records

- Property Price Register

+ 3 related feeds

#### Ground & environment

- Geological Survey Ireland

- Environmental Protection Agency

- Urban wastewater capacity

+ 12 related feeds

#### Heritage & archaeology

- National Monuments Service

- National Inventory of Architectural Heritage

- Protected structures & conservation areas

+ 2 related feeds

#### Land & tenure

- Tailte Éireann cadastral parcels

#### People & place

- CSO Census 2022

- Pobal HP Deprivation Index

+ 2 related feeds

#### Access & transport

- National airfields & ports

+ 1 related feeds

Explore data provenance

See every source and its licence

### Check it yourself.

A full site — boundary, thirteen applications, the documents behind them — is open to the public. No account needed.

Open the site Open precedent search

---

# Page 35: Irish planning statistics — grant rates, decision times, trends

Source URL: https://eireplan.com/insights

Skip to main content

#### 2026 year-to-date

Jan 1 to today · vs. same period last year

YTD monthly volume

#### Local authorities this year

#### Breakdown this year

On this page

### By authority

A dedicated page for each of the 31 planning authorities — volumes, grant rate, invalidation rate and decision times, with the trends behind them.

- Carlow

- Cavan

- Clare

- Cork City

- Cork County

- Donegal

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Galway City

- Galway County

- Kerry

- Kildare

- Kilkenny

- Laois

- Leitrim

- Limerick

- Longford

- Louth

- Mayo

- Meath

- Monaghan

- Offaly

- Roscommon

- Sligo

- South Dublin

- Tipperary

- Waterford

- Westmeath

- Wexford

- Wicklow

---

# Page 36: Planning in Carlow — grant rate & decision times

Source URL: https://eireplan.com/insights/carlow

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

448

4,382 on record since 2004

Grant rate

89.9%

National: 88.8%

Invalidation rate

21.0%

National: 16.5%

Avg decision time

12 weeks

85 days

Busiest categories in the window: residential new build ( 114 ) , residential extension alteration ( 104 ) and agricultural ( 39 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Carlow County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 37: Planning in Cavan — grant rate & decision times

Source URL: https://eireplan.com/insights/cavan

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

776

5,943 on record since 2004

Grant rate

95.2%

National: 88.8%

Invalidation rate

20.4%

National: 16.5%

Avg decision time

13 weeks

90 days

Busiest categories in the window: residential extension alteration ( 183 ) , residential new build ( 176 ) and agricultural ( 72 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Cavan County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 38: Planning in Clare — grant rate & decision times

Source URL: https://eireplan.com/insights/clare

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,145

10,682 on record since 2004

Grant rate

94.2%

National: 88.8%

Invalidation rate

4.3%

National: 16.5%

Avg decision time

9.9 weeks

69 days

Busiest categories in the window: residential new build ( 347 ) , residential extension alteration ( 270 ) and amendment revision ( 81 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Clare County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 39: Contested places — where Irish planning decisions split

Source URL: https://eireplan.com/insights/contested-places

Skip to main content

#### Methodology & scope

What this map shows — and what it doesn’t.

Each bubble is a single planning application. The bubble’s area is proportional to the number of public submitters recorded on the application’s page on eplanning.ie . A "submitter" can be a private citizen, a residents’ association, or a statutory consultee (e.g. Irish Water, Inland Fisheries Ireland) — the eplanning.ie portal does not distinguish them.

Sample scope. 1,005 applications received between 2022-01-04 and 2024-12-23 , randomly stratified at 42 per authority across all 24 local authorities on the eplanning.ie portal.

Not on this map. Applications under the Agile (Citizen Portal) system are excluded — that is Dublin City, Fingal, South Dublin, Dun Laoghaire-Rathdown, Wexford, Cork City & County, and Galway City. The Agile platform does not expose a public submissions listing API, so per-application counts cannot be sourced the same way. Rolling those councils in is tracked separately.

Cap at 10. The eplanning.ie portal paginates submitter lists at 10 per page; submitter_count values of 10 indicate "at least 10" (true count may be higher).

#### Top 12 contested applications

Most public submitters in the sample.

Ref 22135

Louth County Council · REFUSE · 2022-02-23

≥ 10

submitter s

Ref 2223

Monaghan County Council · GRANT · 2022-01-21

≥ 10

submitter s

Ref 23257

Wicklow County Council · GRANT · 2023-03-16

≥ 10

submitter s

Ref 2360330

Louth County Council · UNKNOWN · 2023-09-01

≥ 10

submitter s

Ref 2360360

Louth County Council · UNKNOWN · 2023-09-19

≥ 10

submitter s

Ref 2383

Galway City Council · GRANT · 2023-04-05

≥ 10

submitter s

Ref 2460230

Clare County Council · GRANT · 2024-05-22

≥ 10

submitter s

Ref 2460264

Donegal County Council · REFUSE · 2024-03-04

≥ 10

submitter s

Ref 2460400

Roscommon County Council · GRANT · 2024-08-23

≥ 10

submitter s

Ref 2460416

Clare County Council · GRANT · 2024-08-30

≥ 10

submitter s

Ref 23791

Meath County Council · UNKNOWN · 2023-08-10

9

submitter s

Ref 2460309

Monaghan County Council · UNKNOWN · 2024-08-22

9

submitter s

#### By local authority

How many sampled apps drew at least one submission.

- Limerick County Council 24 / 42 · 57 %

- Carlow County Council 23 / 42 · 55 %

- Longford County Council 19 / 42 · 45 %

- Clare County Council 16 / 41 · 39 %

- Galway City Council 15 / 42 · 36 %

- Kerry County Council 13 / 42 · 31 %

- Louth County Council 13 / 42 · 31 %

- Galway County Council 12 / 42 · 29 %

- Roscommon County Council 11 / 42 · 26 %

- Wicklow County Council 11 / 42 · 26 %

- Mayo County Council 10 / 42 · 24 %

- Westmeath County Council 10 / 42 · 24 %

- Leitrim County Council 9 / 42 · 21 %

- Cavan County Council 8 / 40 · 20 %

- Kildare County Council 7 / 42 · 17 %

- Laois County Council 7 / 42 · 17 %

- Offaly County Council 7 / 42 · 17 %

- Kilkenny County Council 6 / 42 · 14 %

- Monaghan County Council 6 / 42 · 14 %

- Sligo County Council 6 / 42 · 14 %

- Donegal County Council 5 / 42 · 12 %

- Meath County Council 4 / 42 · 10 %

- Tipperary County Council 4 / 42 · 10 %

- Waterford City and County Council 4 / 42 · 10 %

---

# Page 40: Planning in Cork City — grant rate & decision times

Source URL: https://eireplan.com/insights/cork-city

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

429

7,112 on record since 2004

Grant rate

91.0%

National: 88.8%

Invalidation rate

26.8%

National: 16.5%

Avg decision time

9.1 weeks

64 days

Busiest categories in the window: residential extension alteration ( 169 ) , residential new build ( 76 ) and signage advertising ( 36 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Cork City Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 41: Planning in Cork County — grant rate & decision times

Source URL: https://eireplan.com/insights/cork-county

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

2,900

73,057 on record since 2004

Grant rate

92.4%

National: 88.8%

Invalidation rate

22.6%

National: 16.5%

Avg decision time

11 weeks

80 days

Busiest categories in the window: residential new build ( 939 ) , residential extension alteration ( 706 ) and agricultural ( 238 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Cork County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 42: Planning in Donegal — grant rate & decision times

Source URL: https://eireplan.com/insights/donegal

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

2,507

21,243 on record since 2004

Grant rate

93.3%

National: 88.8%

Invalidation rate

14.6%

National: 16.5%

Avg decision time

9.4 weeks

66 days

Busiest categories in the window: residential new build ( 1,042 ) , residential extension alteration ( 508 ) and residential ancillary ( 161 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Donegal County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 43: Planning in Dublin City — grant rate & decision times

Source URL: https://eireplan.com/insights/dublin-city

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

4,894

30,988 on record since 2004

Grant rate

88.9%

National: 88.8%

Invalidation rate

22.1%

National: 16.5%

Avg decision time

7.0 weeks

49 days

Busiest categories in the window: residential extension alteration ( 743 ) , residential ancillary ( 403 ) and residential new build ( 366 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Dublin City Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 44: Planning in Dún Laoghaire–Rathdown — grant rate & decision times

Source URL: https://eireplan.com/insights/dun-laoghaire-rathdown

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,917

15,989 on record since 2004

Grant rate

88.5%

National: 88.8%

Invalidation rate

12.9%

National: 16.5%

Avg decision time

7.9 weeks

55 days

Busiest categories in the window: demolition ( 255 ) , residential extension alteration ( 122 ) and residential new build ( 97 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Dun Laoghaire Rathdown County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 45: Planning in Fingal — grant rate & decision times

Source URL: https://eireplan.com/insights/fingal

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,664

14,693 on record since 2004

Grant rate

76.7%

National: 88.8%

Invalidation rate

19.9%

National: 16.5%

Avg decision time

9.7 weeks

68 days

Busiest categories in the window: demolition ( 120 ) , residential new build ( 83 ) and change of use ( 50 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Fingal County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 46: Planning in Galway City — grant rate & decision times

Source URL: https://eireplan.com/insights/galway-city

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

337

3,399 on record since 2004

Grant rate

85.9%

National: 88.8%

Invalidation rate

3.6%

National: 16.5%

Avg decision time

10 weeks

73 days

Busiest categories in the window: residential extension alteration ( 91 ) , residential new build ( 45 ) and amendment revision ( 27 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Galway City Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 47: Planning in Galway County — grant rate & decision times

Source URL: https://eireplan.com/insights/galway-county

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,919

18,655 on record since 2004

Grant rate

83.5%

National: 88.8%

Invalidation rate

4.1%

National: 16.5%

Avg decision time

10 weeks

72 days

Busiest categories in the window: residential new build ( 716 ) , residential extension alteration ( 299 ) and agricultural ( 135 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Galway County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 48: Planning in Kerry — grant rate & decision times

Source URL: https://eireplan.com/insights/kerry

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,154

12,916 on record since 2004

Grant rate

87.4%

National: 88.8%

Invalidation rate

7.0%

National: 16.5%

Avg decision time

12 weeks

85 days

Busiest categories in the window: residential new build ( 306 ) , residential extension alteration ( 250 ) and amendment revision ( 108 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Kerry County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 49: Planning in Kildare — grant rate & decision times

Source URL: https://eireplan.com/insights/kildare

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,173

13,742 on record since 2004

Grant rate

79.9%

National: 88.8%

Invalidation rate

27.4%

National: 16.5%

Avg decision time

13 weeks

88 days

Busiest categories in the window: residential extension alteration ( 263 ) , residential new build ( 174 ) and residential ancillary ( 133 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Kildare County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 50: Planning in Kilkenny — grant rate & decision times

Source URL: https://eireplan.com/insights/kilkenny

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

871

8,531 on record since 2004

Grant rate

94.3%

National: 88.8%

Invalidation rate

9.8%

National: 16.5%

Avg decision time

12 weeks

86 days

Busiest categories in the window: residential new build ( 192 ) , residential extension alteration ( 185 ) and agricultural ( 88 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Kilkenny County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 51: Planning in Laois — grant rate & decision times

Source URL: https://eireplan.com/insights/laois

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

832

5,756 on record since 2004

Grant rate

94.3%

National: 88.8%

Invalidation rate

37.9%

National: 16.5%

Avg decision time

11 weeks

77 days

Busiest categories in the window: residential new build ( 239 ) , residential extension alteration ( 143 ) and amendment revision ( 77 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Laois County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 52: Planning in Leitrim — grant rate & decision times

Source URL: https://eireplan.com/insights/leitrim

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

198

1,486 on record since 2004

Grant rate

94.5%

National: 88.8%

Invalidation rate

2.0%

National: 16.5%

Avg decision time

10 weeks

72 days

Busiest categories in the window: residential extension alteration ( 54 ) , residential new build ( 42 ) and residential ancillary ( 16 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Leitrim County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 53: Planning in Limerick — grant rate & decision times

Source URL: https://eireplan.com/insights/limerick

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,349

12,382 on record since 2004

Grant rate

87.7%

National: 88.8%

Invalidation rate

3.8%

National: 16.5%

Avg decision time

11 weeks

79 days

Busiest categories in the window: residential extension alteration ( 332 ) , residential new build ( 314 ) and agricultural ( 94 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Limerick County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 54: Planning in Longford — grant rate & decision times

Source URL: https://eireplan.com/insights/longford

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

276

2,070 on record since 2004

Grant rate

84.3%

National: 88.8%

Invalidation rate

3.6%

National: 16.5%

Avg decision time

9.1 weeks

64 days

Busiest categories in the window: residential new build ( 76 ) , residential extension alteration ( 63 ) and agricultural ( 27 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Longford County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 55: Planning in Louth — grant rate & decision times

Source URL: https://eireplan.com/insights/louth

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

809

7,342 on record since 2004

Grant rate

86.5%

National: 88.8%

Invalidation rate

12.2%

National: 16.5%

Avg decision time

11 weeks

77 days

Busiest categories in the window: residential extension alteration ( 214 ) , residential new build ( 166 ) and residential ancillary ( 48 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Louth County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 56: Planning in Mayo — grant rate & decision times

Source URL: https://eireplan.com/insights/mayo

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,207

9,012 on record since 2004

Grant rate

93.2%

National: 88.8%

Invalidation rate

10.9%

National: 16.5%

Avg decision time

11 weeks

77 days

Busiest categories in the window: residential new build ( 411 ) , residential extension alteration ( 269 ) and amendment revision ( 78 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Mayo County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 57: Planning in Meath — grant rate & decision times

Source URL: https://eireplan.com/insights/meath

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,609

14,415 on record since 2004

Grant rate

85.7%

National: 88.8%

Invalidation rate

19.0%

National: 16.5%

Avg decision time

11 weeks

78 days

Busiest categories in the window: residential new build ( 398 ) , residential extension alteration ( 342 ) and residential ancillary ( 138 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Meath County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 58: Planning in Monaghan — grant rate & decision times

Source URL: https://eireplan.com/insights/monaghan

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

537

4,733 on record since 2004

Grant rate

94.4%

National: 88.8%

Invalidation rate

17.7%

National: 16.5%

Avg decision time

14 weeks

98 days

Busiest categories in the window: residential new build ( 157 ) , residential extension alteration ( 116 ) and agricultural ( 64 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Monaghan County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 59: Planning in Offaly — grant rate & decision times

Source URL: https://eireplan.com/insights/offaly

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

719

5,049 on record since 2004

Grant rate

90.1%

National: 88.8%

Invalidation rate

36.2%

National: 16.5%

Avg decision time

13 weeks

90 days

Busiest categories in the window: residential new build ( 232 ) , residential extension alteration ( 126 ) and amendment revision ( 48 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Offaly County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 60: Planning in Roscommon — grant rate & decision times

Source URL: https://eireplan.com/insights/roscommon

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

613

5,346 on record since 2004

Grant rate

86.1%

National: 88.8%

Invalidation rate

19.6%

National: 16.5%

Avg decision time

15 weeks

104 days

Busiest categories in the window: residential new build ( 151 ) , residential extension alteration ( 147 ) and agricultural ( 67 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Roscommon County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 61: Planning in Sligo — grant rate & decision times

Source URL: https://eireplan.com/insights/sligo

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

450

3,790 on record since 2004

Grant rate

92.7%

National: 88.8%

Invalidation rate

12.9%

National: 16.5%

Avg decision time

9.4 weeks

66 days

Busiest categories in the window: residential extension alteration ( 126 ) , residential new build ( 90 ) and amendment revision ( 30 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Sligo County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 62: Planning in South Dublin — grant rate & decision times

Source URL: https://eireplan.com/insights/south-dublin

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,003

8,342 on record since 2004

Grant rate

89.4%

National: 88.8%

Invalidation rate

7.2%

National: 16.5%

Avg decision time

6.3 weeks

44 days

Busiest categories in the window: residential extension alteration ( 218 ) , residential new build ( 80 ) and residential ancillary ( 73 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of South Dublin County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 63: Planning in Tipperary — grant rate & decision times

Source URL: https://eireplan.com/insights/tipperary

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,246

10,871 on record since 2004

Grant rate

95.8%

National: 88.8%

Invalidation rate

22.7%

National: 16.5%

Avg decision time

11 weeks

80 days

Busiest categories in the window: residential extension alteration ( 269 ) , residential new build ( 240 ) and agricultural ( 147 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Tipperary County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 64: Planning in Waterford — grant rate & decision times

Source URL: https://eireplan.com/insights/waterford

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

936

7,181 on record since 2004

Grant rate

92.2%

National: 88.8%

Invalidation rate

25.0%

National: 16.5%

Avg decision time

11 weeks

80 days

Busiest categories in the window: residential extension alteration ( 228 ) , residential new build ( 191 ) and signage advertising ( 70 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Waterford City and County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 65: Planning in Westmeath — grant rate & decision times

Source URL: https://eireplan.com/insights/westmeath

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

594

5,003 on record since 2004

Grant rate

84.5%

National: 88.8%

Invalidation rate

15.8%

National: 16.5%

Avg decision time

12 weeks

85 days

Busiest categories in the window: residential new build ( 159 ) , residential extension alteration ( 143 ) and amendment revision ( 44 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Westmeath County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 66: Planning in Wexford — grant rate & decision times

Source URL: https://eireplan.com/insights/wexford

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

1,046

14,468 on record since 2004

Grant rate

84.9%

National: 88.8%

Invalidation rate

3.9%

National: 16.5%

Avg decision time

11 weeks

76 days

Busiest categories in the window: residential new build ( 339 ) , residential extension alteration ( 88 ) and residential ancillary ( 64 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Wexford County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 67: Planning in Wicklow — grant rate & decision times

Source URL: https://eireplan.com/insights/wicklow

Skip to main content

### The last twelve months

August 2025 to July 2026

Applications

944

13,098 on record since 2004

Grant rate

89.0%

National: 88.8%

Invalidation rate

18.4%

National: 16.5%

Avg decision time

11 weeks

78 days

Busiest categories in the window: residential new build ( 208 ) , residential extension alteration ( 198 ) and amendment revision ( 77 ) .

### Trends since 2021

Live from the register, refreshed twice a week. Complete years only — the current year is still in flight. For side-by-side comparisons across authorities, use the national view .

#### Applications over time

Granted Refused Invalid Withdrawn In progress Other

#### Breakdown

Where these figures come from. Aggregates over the published planning register of Wicklow County Council , bucketed monthly by decision outcome. Grant rate is granted as a share of granted plus refused; it is suppressed below 20 decided applications, where a percentage would be noise. Snapshot computed July 2026 — the explorer above always shows the latest refresh. Aggregate figures on this page may be reused with attribution.

### The numbers are the surface. The record underneath is the product.

Every figure on this page aggregates individual applications — each with its documents, decision, and site. Open a real workspace and look at one.

Open a real site — no account Start free

Building something? The same data is an API.

### Every authority, the same page

The same figures, computed the same way, for each of the 31 planning authorities.

Leinster

- Carlow

- Dublin City

- Dún Laoghaire–Rathdown

- Fingal

- Kildare

- Kilkenny

- Laois

- Longford

- Louth

- Meath

- Offaly

- South Dublin

- Westmeath

- Wexford

- Wicklow

Munster

- Clare

- Cork City

- Cork County

- Kerry

- Limerick

- Tipperary

- Waterford

Connacht

- Galway City

- Galway County

- Leitrim

- Mayo

- Roscommon

- Sligo

Ulster

- Cavan

- Donegal

- Monaghan

---

# Page 68: Security at EirePlan — how your site data is handled

Source URL: https://eireplan.com/our-security

Skip to main content

## Security at EirePlan — how your site data is handled

Data Security & Privacy

## Security & Data Handling

Planning applications involve commercially sensitive information: site details, client strategies, financial arrangements, and pre-application discussions with local authorities.

We designed Eireplan with the assumption that all project data is confidential and should be treated accordingly.

### Project and organisation isolation

Eireplan enforces strict boundaries between organisations and projects.

All data is isolated by organisation. One organisation cannot access another organisation's projects, documents, or settings.

Within an organisation, users only access projects they have been explicitly invited to.

There is no cross-organisation visibility. Project data, user activity, and workspace configuration are entirely separate.

These boundaries are enforced at the database level, not just in the application interface.

### AI usage boundaries

Eireplan includes AI-assisted features for policy referencing, document analysis, and validation support. These features operate within clear boundaries.

AI features only access data within the specific project the user is working on.

No project data is exposed to other organisations or used to inform responses for other clients.

AI outputs are not shared, aggregated, or reused across organisations.

Project-specific context remains within that project's scope.

### Access control and permissions

Eireplan uses role-based access to control what users can see and do.

##### Organisation level

Organisation owners and administrators can manage members, invite new users, and configure organisation-wide settings. Members can access projects they are assigned to but cannot modify organisation settings.

##### Project level

Projects have their own permission structure. Managers control project settings and team composition. Planners have full access to project workspaces. Clients have limited access to specific documents.

Users are only granted the minimum access required for their role. Permissions cannot be escalated without explicit invitation from someone with the appropriate authority.

### Data ownership

Your data remains yours.

Organisations retain full ownership of all project data, documents, and outputs created within Eireplan. We do not claim any rights over your content.

Data is stored to provide the service and is not used for purposes beyond operating Eireplan for your organisation.

### Our commitment

We take a conservative approach to data handling because we understand what is at stake. Planning data often involves pre-application strategies, client relationships, and commercially sensitive site information.

Our design decisions reflect this:

Isolation is enforced by default, not as an optional setting.

Access is granted explicitly, not inferred.

Features that could compromise boundaries are not built.

We will continue to prioritise data responsibility as Eireplan develops. If you have specific security questions or requirements, we are happy to discuss them directly.

#### Questions about security?

Contact us directly to discuss your organisation's specific requirements.

Get Access

---

# Page 69: Pricing — EirePlan

Source URL: https://eireplan.com/pricing

Skip to main content

## Pricing

A free account gives you the national planning record to search, the map and policy layers, and the assistant. It is not a trial and it does not ask for a card.

Create a free account Talk to us about a plan

EirePlan plans compared. Free is self-serve; Solo, Practice and Team are arranged by contacting us.

Compare plans

Free

One person, no card, no expiry.

Create account

Solo

An individual planner, architect or surveyor.

Talk to us

Practice

A practice that runs on planning research.

Talk to us

Team

Several people working the same caseload.

Talk to us

The planning record Every tier searches the same national record. What changes is how much of it you can pull in a month.

Precedent searches Decisions, conditions and documents across all 31 planning authorities. 50 / month 1,000 / month Unlimited Unlimited

Source documents Planner's reports, further-information letters and decision orders, where the authority published them. Included Included Included Included

Map and policy layers Zoning, statutory boundaries, environmental designations and the rest of the spatial record. Included Included Included Included

Export and filtering Not included Included Included Included

Sites and applications A site holds everything for one address: its history, its constraints and the decisions worth citing near it.

Sites 6 10 25 Unlimited

Site history reports The planning history for an address, with conditions quoted as written and linked to their source. Not included 5 / month 20 / month 20 / seat, pooled

Document register Not included Included Included Included

The assistant Answers are drawn from the record and cited back to it. Where the record is incomplete, it says so.

AI queries 20 / month 150 / month 500 / month 500 / seat, pooled

Drafting and analysis Not included Included Included Included

People and access Who else can see the work, and on what terms.

Seats 1 1 1 3 or more

Shared workspace Sites, applications and documents visible to the whole team rather than one account. Not included Not included Not included Included

Roles and permissions Not included Not included Not included Included

Developers The same planning record, addressable from your own systems.

API access Precedents, boundaries and local-authority lookup over a documented REST API. Not included Not included Included Included

Support

Support Email Email Email Priority

Create account Talk to us Talk to us Talk to us

Limits are per calendar month and reset on the first. On Team they are pooled across the subscription rather than allocated per person, so heavier users draw on the same balance as lighter ones.

### Test it on a case you already know

Search the record for an application whose outcome you already know and see whether what comes back holds up. The free account is enough to do it.

Create a free account Talk to us

Or write to hello@eireplan.ie .

---

# Page 70: Eireplan Privacy Policy - Eireplan

Source URL: https://eireplan.com/privacy

Skip to main content

##### Eireplan Privacy Policy

How Eireplan handles personal data: what we collect, the legal basis for each use, who processes it, where it goes, how long we keep it, and your rights. Includes the Article 14 notice for people named in the public planning register.

This Privacy Policy was published on 31 August 2026

Version: privacy-2026-08-31 Last updated: 31 August 2026 Contact: privacy@eireplan.ie

This policy explains what personal data EirePlan collects, why, on what legal basis, who we share it with, where it goes, how long we keep it, and what you can do about it.

It covers two different groups of people, and the difference matters:

- Users. People who hold an account or visit the website. Sections 1 to 14 are about you.

- People named in the public planning record. If you applied for planning permission in Ireland, your name may appear in our database because the planning authority published it. You did not give us that data and you may not have known we hold it. Section 15 is written for you, and it is the section that explains your rights.

### 1. Who is responsible for your data

The controller is Neri Carcasci, trading as EirePlan, of [REGISTERED ADDRESS TO BE INSERTED BEFORE PUBLICATION], Ireland.

We intend to incorporate an Irish limited company to carry on this business. When we do, that company becomes the controller and we will update this policy and tell you.

Contact us about anything in this policy at privacy@eireplan.ie . We have not appointed a Data Protection Officer, because we are not required to under Article 37. Privacy queries go to the address above and are handled by the business owner.

### 2. Personal data we collect about users

You give us:

Data Where it comes from

Name, email address, password or Google sign-in identity Account creation

Profile details, avatar, organisation and role Your profile, or your organisation administrator

Billing name, address, VAT number, subscription record Purchase. Card details go directly to our payment processor and we never receive them

Documents, project data, site records, notes, drawings, boundaries Your use of the platform

Questions and prompts you type into AI features Your use of the platform

Correspondence with us, including support and enquiry forms You contacting us

Addresses and eircodes you search for Your use of search and mapping

We generate or observe:

Data Purpose

IP address, browser and device information, timestamps Security, abuse prevention, and delivering the site

Authentication events, session records, API key usage and credit consumption Access control, billing, and detecting misuse

Application logs and error reports Keeping the service working

Server-side records of which features you use Understanding which parts of the product are used, so we can improve them

Record of your acceptance of our Terms and Privacy Policy, including version, timestamp, IP address and browser user agent Proving what you agreed to and when

We do not collect special category data as defined in Article 9, and we ask you not to upload it. We do not knowingly collect data about children.

### 3. Why we use it, and the legal basis

What we do Legal basis

Create and run your account, provide the platform, take payment, give support Article 6(1)(b), performance of a contract with you

Keep the service secure, prevent abuse, investigate incidents, enforce our Terms Article 6(1)(f), our legitimate interest in protecting the service and its users

Understand how features are used, in order to improve them Article 6(1)(f), our legitimate interest in knowing which parts of the product are used. Measured on our servers from requests you already send us, never by anything placed on your device. You can object under section 11

Send service messages you need to receive, such as security notices, billing notices and material changes to these documents Article 6(1)(b) and Article 6(1)(f)

Send marketing about our own similar products to an existing customer Regulation 13 of S.I. 336 of 2011, with an opt out in every message

Send marketing to anyone else Article 6(1)(a), your consent

Keep records of acceptance of our Terms, and financial records Article 6(1)(c), legal obligation, and Article 6(1)(f), establishing and defending legal claims

Publish and analyse the public planning record Article 6(1)(f), our legitimate interest, and that of our users, in making the public planning record usable. Section 15 explains this in full

Where we rely on legitimate interests, we have assessed our interest against your rights and concluded that our processing does not override them. You can ask us for that assessment at privacy@eireplan.ie , and you can object under section 11.

### 4. Cookies and similar technologies

We place nothing on your device that is not strictly necessary to run the service, so there is nothing to consent to and no cookie banner.

What we store is limited to your sign-in session and anti-forgery tokens. If you are not signed in, we store nothing at all. We do not use analytics cookies, advertising cookies, tracking pixels, or any third party script, and we do not sell or share personal data for advertising.

We understand product usage from our own server logs instead, which is covered in section 3 and requires nothing on your device. Full detail is in the Cookie Policy.

### 5. AI features

When you use an AI feature, the content needed to answer your request is sent to a model provider. That may include the text of your prompt, extracts from documents in the project you are working in, and relevant planning records.

- We instruct our providers not to train models on our data, and they are contractually bound not to.

- Your content is not used to answer another customer's question and is not shared between organisations.

- We keep a record of the request for billing, cost control and debugging.

- Model providers are outside the European Economic Area. Section 8 explains the safeguards.

- No AI feature makes an automated decision about you that produces a legal or similarly significant effect within the meaning of Article 22.

AI output can be wrong. It is a draft for your review, not a statement of fact by us.

### 6. Who we share data with

We do not sell personal data. We share it only with the processors listed below, each under a written contract that meets Article 28.

Processor What it does Where it processes data

Supabase, on AWS Main database and file storage Ireland

Google Cloud Platform Application hosting for the backend and AI service Belgium

Google Firebase Authentication Sign-in and identity European Union and United States

Cloudflare Website delivery, DNS and network protection Global edge network, served from Dublin

OpenRouter Routing requests to large language model providers United States

OpenAI Text embeddings for search United States

Resend Transactional and service email United States

Stripe Payment processing Ireland and United States

Google Maps Platform Converting an address or eircode into map coordinates United States

OpenStreetMap Foundation Converting an address into map coordinates, as a fallback United Kingdom and European Union

We will give notice in this policy before adding a new processor, and business customers may object under the Data Processing Terms.

We may also disclose personal data where we are legally required to, to establish or defend a legal claim, or to a buyer if the business is sold, in which case we will tell you.

### 7. Where your data is stored

Your account, your documents, your project data and the planning database are stored in Ireland, and the applications that serve them run in Belgium. For the great majority of what we hold, your data does not leave the European Union.

### 8. Transfers outside the European Economic Area

Some processors in the table above operate from the United States. Those transfers are protected by:

- The European Commission's Standard Contractual Clauses, incorporated into our contract with each of them, together with technical measures including encryption in transit.

- Where the provider is certified, the EU to US Data Privacy Framework adequacy decision.

We have assessed each transfer and limited what is sent. Geocoding sends an address, not your identity. Model providers receive the content of your request, so please do not put personal data into a prompt unless you need to.

You can ask us for a copy of the safeguards that apply to a specific transfer at privacy@eireplan.ie .

### 9. How long we keep it

Data Retention

Account and profile While your account is open, then deleted or anonymised within 30 days of closure

Your documents and project data While your account is open. Available for export for 30 days after closure, then deleted

Record of acceptance of our Terms Six years after your account closes, matching the limitation period for contract claims

Billing and financial records Six years, as required by tax law

Security and access logs 12 months

Server-side product usage records 14 months

Support correspondence Three years

Public planning records For as long as the record is of research and reference value. Section 15 explains

Backups Deleted data persists in encrypted backups for up to 30 days before being overwritten

### 10. Security

Data is encrypted in transit and at rest. Access to production systems is limited to those who need it and requires multi-factor authentication. The database denies access by default and is reachable only through our backend. Organisation and project separation is enforced by our application layer, and we log administrative access.

If a breach is likely to result in a risk to your rights, we will notify the Data Protection Commission within 72 hours, and we will tell you directly where the risk is high.

Report a vulnerability to security@eireplan.ie . See clause 21 of the Terms for our commitment to researchers who report in good faith.

### 11. Your rights

You have the right to:

- Access the personal data we hold about you, and receive a copy.

- Rectify data that is wrong or incomplete.

- Erase your data, where one of the grounds in Article 17 applies.

- Restrict processing while a dispute about accuracy or legitimate interests is resolved.

- Portability of data you gave us, in a structured, machine readable format, where processing is based on consent or contract.

- Object to processing based on legitimate interests. If you object, we will stop unless we can show compelling grounds that override your rights. If you object to direct marketing, we will stop, with no exceptions.

- Withdraw consent at any time, which does not affect processing already carried out.

- Not be subject to a decision based solely on automated processing with legal or similarly significant effect. We do not make such decisions.

To exercise any right, email privacy@eireplan.ie . We will respond within one month, and may extend by two further months for complex requests, telling you if we do. We do not charge, unless a request is manifestly unfounded or excessive.

We may ask you to verify your identity before we act, so that we do not disclose your data to someone else.

### 12. Complaints

Please raise concerns with us first at privacy@eireplan.ie .

You also have the right to complain to the Data Protection Commission at any time:

Data Protection Commission, 6 Pembroke Row, Dublin 2, D02 X963, Ireland www.dataprotection.ie

If you live in another EEA country, you may complain to your local supervisory authority instead.

### 13. When you upload other people's data

If you upload documents containing personal data about other people, for example an applicant, an objector, a neighbour or a client, you are the controller of that data and we process it on your behalf. Our Data Processing Terms govern that relationship and meet Article 28.

You are responsible for having a lawful basis for the upload, and for telling those people what you are doing, as your own privacy notice requires.

### 14. Changes to this policy

We will update this policy as the service changes. Where a change is material, we will tell you by email or in the platform before it takes effect, and we will ask you to acknowledge it. The version identifier at the top changes whenever the substance changes.

### 15. If your name appears in the public planning record

This section is for people who never signed up to EirePlan and did not give us their data. It is our notice under Article 14 of the GDPR.

What we hold. Planning authorities in Ireland are required by the Planning and Development Act 2000 to keep a public register of planning applications, and to publish it. That register includes the name of the applicant, the address of the development, a description of it, and the decision. We collect that published record and organise it so it can be searched and analysed.

If you applied for planning permission, your name may be in our database, next to the address of the development.

Where we got it. From the planning authorities themselves, through the national planning data service and the authorities' own public portals, and from An Coimisiún Pleanála for appeals. We did not obtain it from you, and we do not buy personal data.

Why we process it, and on what basis. Our legal basis is Article 6(1)(f), legitimate interests. The interests are our own commercial interest in operating a planning research service, the interests of our users, who are planning professionals, researchers, solicitors and members of the public, and the wider public interest in the planning system being transparent and capable of being scrutinised. Planning is a public process that affects neighbours and communities, and the law requires the register to be public precisely so that it can be examined.

We have carried out a legitimate interests assessment and are satisfied that our use does not override your rights, taking into account that the data was published by a public authority, that it relates to a public administrative process rather than your private life, and that we apply the limits below.

The limits we apply.

- Applicant names are not shown to anonymous visitors and are not published on pages open to the public internet or to search engines. They are visible only to people who have signed in and accepted our Terms.

- We do not enrich applicant names with data from other sources, we do not build profiles of individuals, and we do not use these names for marketing or advertising.

- We do not sell this data.

- We link to the official record so that the authority's version remains the authoritative one.

How long we keep it. For as long as the record has research and reference value, which reflects the fact that planning history attaches to land indefinitely and that a decision from decades ago can still be material to a site today. We review this.

Your rights. You have every right listed in section 11. Two are particularly relevant:

- You can object at any time under Article 21(1). You do not need to give a reason, though it helps if you explain your situation. When you object, we stop processing unless we can demonstrate compelling legitimate grounds that override your interests. In practice, if you object to your name appearing, we will remove or suppress it, and we will tell you what we have done.

- You can ask us to erase your name under Article 17.

Removing your name from our copy does not remove it from the statutory register held by the planning authority, which we do not control. If you want it removed there, you must contact the authority.

To object, or to ask what we hold about you, email privacy@eireplan.ie with the address of the development and, if you know it, the planning reference. We will respond within one month.

Why we did not contact you directly. Article 14(5)(b) does not require us to give this notice individually where doing so would involve disproportionate effort. The register contains hundreds of thousands of records covering many years, and we do not hold contact details for the people named in them. Writing to each person is not possible, and attempting it would mean collecting contact data we do not currently hold and do not need. We publish this notice instead, keep it linked from every page of the site, and apply the safeguards above, which is the balancing measure Article 14(5)(b) requires.

### 16. Contact

Neri Carcasci, trading as EirePlan
[REGISTERED ADDRESS TO BE INSERTED BEFORE PUBLICATION], Ireland

Data protection: privacy@eireplan.ie Security: security@eireplan.ie General: hello@eireplan.ie

---

# Page 71: Eireplan Terms of Service - Eireplan

Source URL: https://eireplan.com/terms

Skip to main content

##### Eireplan Terms of Service

The binding agreement between you and Eireplan. Covers what the service is and is not, AI output, liability, consumer rights, and how the contract is formed and recorded.

This Terms of Service was published on 31 August 2026

Version: terms-2026-08-31 Last updated: 31 August 2026 Contact: legal@eireplan.ie

### 1. Who you are contracting with

EirePlan is operated by Neri Carcasci, trading as EirePlan, of [REGISTERED ADDRESS TO BE INSERTED BEFORE PUBLICATION], Ireland. In these Terms, "we", "us", "our" and "EirePlan" mean that person. "You" means the person or organisation that holds an account or otherwise uses the Service.

We intend to incorporate an Irish limited company to carry on this business. When that company is incorporated, we may transfer this agreement to it under clause 25.3. Your rights under this agreement will not be reduced by that transfer.

You can reach us at legal@eireplan.ie for contractual matters, privacy@eireplan.ie for data protection matters, and security@eireplan.ie to report a vulnerability.

### 2. These Terms, and the documents that form part of them

These Terms of Service are a binding contract between you and us. The following documents are incorporated into and form part of this agreement:

- The Privacy Policy, which explains how we handle personal data.

- The Cookie Policy, which explains what we store on your device.

- The Data Processing Terms, which apply where you upload personal data about other people and we process it on your behalf.

- Any order form, quotation or plan description that records what you have bought.

If there is a conflict between these documents, the order above governs, except that the Data Processing Terms prevail over everything else on the subject of processing personal data on your behalf.

### 3. How this agreement is formed

You enter into this agreement when you tick the box confirming that you accept these Terms and the Privacy Policy during account creation, and then create your account.

We record the fact of that acceptance, the exact version of each document you accepted, the date and time, and technical details of the request. We keep that record for as long as your account exists and for six years afterwards, so that both of us can establish what was agreed and when. That retention period matches the limitation period for contract claims in Ireland.

If we change these Terms in a way that materially affects your rights or obligations, we will ask you to accept the new version before you continue to use the Service, and we will record that acceptance in the same way.

If you accept these Terms on behalf of an organisation, you confirm that you have authority to bind that organisation, and "you" means that organisation as well as you personally.

### 4. Eligibility

You must be at least 18 years of age and legally capable of entering into a binding contract. The Service is not directed at children and we do not knowingly provide it to anyone under 18.

The Service is offered for use in Ireland. We make no representation that it is appropriate or available for use elsewhere, and you are responsible for compliance with local law if you access it from another country.

### 5. Your account

You are responsible for the accuracy of the information you give us, for keeping your credentials confidential, and for everything done under your account. You must tell us promptly at security@eireplan.ie if you believe your account has been accessed without your authority.

Where your account belongs to an organisation, the organisation's administrators can add and remove members, change roles, and access content held in the organisation's workspace, including content you created. If you use a work account, your employer may therefore be able to see what you do in the Service.

We may require you to verify your email address before your account becomes fully active.

### 6. What the Service is

EirePlan is a decision support platform for planning work in Ireland. It aggregates publicly available planning records, applies analysis and structure to them, and provides workflow tools, document management, search, mapping, reporting and AI assisted drafting.

### 7. What the Service is not

This clause is important. Please read it carefully, because it defines the limits of what you may rely on.

EirePlan is not the statutory record. The authoritative record of any planning application is the register kept by the relevant planning authority under the Planning and Development Acts, and the file held by An Coimisiún Pleanála where relevant. Our data is a copy, derived from public sources, and it may be incomplete, out of date, or wrong. Where a decision matters, you must check the statutory record directly. We provide links to the official record for that purpose.

EirePlan does not give advice. Nothing in the Service is legal advice, planning advice, engineering advice, environmental advice, valuation advice or financial advice. We are not your planner, your solicitor or your consultant, and no professional relationship arises between us. The Service does not replace professional judgment, statutory assessment, or the appointment of a suitably qualified professional.

EirePlan does not manage your deadlines. The Service may display dates, including decision due dates, further information dates, appeal windows and expiry dates. Those dates are derived from third party data and from our own calculation, and they may be wrong or missing. They are indicative only. You remain solely responsible for identifying and meeting every statutory and contractual deadline that applies to your work, and you must not use the Service as your only means of tracking one.

EirePlan does not guarantee an outcome. Analysis of previous decisions, precedent comparisons, approval estimates and similar features describe patterns in historic data. They are not predictions, they are not warranties, and they do not indicate how any authority will decide any future application.

### 8. Third party data and sources

The Service incorporates data published by planning authorities, An Coimisiún Pleanála, Tailte Éireann, the Environmental Protection Agency, the Central Statistics Office, the Ordnance Survey, and other public bodies, together with data from open sources such as OpenStreetMap.

We do not control that data, we do not verify it, and we cannot correct errors at source. It is provided to you on an "as is" basis. Where a source imposes licence conditions on downstream use, those conditions apply to you as well as to us, and we identify the source of each dataset within the Service so that you can comply.

Where the Service links to a third party website, we are not responsible for that website or its content.

### 9. AI features

The Service includes features that use large language models and other automated systems to summarise documents, extract information, draft text, answer questions and surface relevant material.

You acknowledge and accept each of the following:

- AI output is generated by statistical models. It can be wrong, incomplete, internally inconsistent, or entirely fabricated while appearing confident and well sourced. This is a known and unavoidable characteristic of the technology, not a defect in the Service.

- Citations, references, quotations, conditions, dates and figures produced by AI features must be checked against the underlying source before you rely on them or pass them to a client, an authority or a court.

- AI output is a draft for your review. You are the author of anything you submit. Professional responsibility for the content of your work remains entirely with you.

- We do not warrant that AI output is accurate, current, complete, or fit for any purpose.

- We may change, limit, meter or withdraw AI features, and we may change the underlying model providers.

We do not use your content to train foundation models, and we require our AI providers not to do so. This is set out further in the Privacy Policy.

No AI feature in the Service produces a decision about you that has a legal or similarly significant effect within the meaning of Article 22 of the GDPR.

### 10. Your content

You keep ownership of everything you upload, create or store in the Service, including documents, project data, site records and drafting. We claim no ownership of it.

You grant us a non-exclusive, worldwide, royalty free licence to host, copy, transmit, display, index, process and create technical derivatives of your content, for the sole purposes of operating the Service for you, keeping it secure, meeting our legal obligations, and providing support you request. That licence lasts only as long as we hold the content, and it ends when the content is deleted.

You are responsible for having the rights necessary to upload your content, and for ensuring that doing so does not breach any duty of confidence, any intellectual property right, or any data protection obligation you owe to another person.

We may generate aggregated and statistical information from use of the Service. We may use that information for any business purpose, provided it does not identify you, your organisation, your clients, or any individual, and cannot reasonably be used to do so.

### 11. Data protection

Where we handle personal data about you as a user of the Service, we act as controller and the Privacy Policy applies.

Where you upload documents or records containing personal data about other people, for example an applicant, an objector, a client or a member of the public, you act as controller of that personal data and we act as your processor. The Data Processing Terms apply to that processing and satisfy Article 28 of the GDPR. You are responsible for having a lawful basis for that upload, and for the transparency obligations you owe to those people.

We publish a current list of our sub-processors in the Privacy Policy and will give notice before adding a new one.

### 12. Acceptable use

You must not:

- Use the Service in breach of any law, regulation or professional obligation.

- Attempt to access any account, organisation, workspace, dataset or system that you have not been granted access to, or test the security of the Service without our prior written consent.

- Scrape, crawl, bulk export, mirror or systematically extract data from the Service other than through an interface we provide for that purpose and within the limits that apply to it.

- Use the Service to build, train or improve a competing product or dataset.

- Resell, sublicense, share or otherwise make your access available to anyone outside your organisation, or exceed the number of users your plan permits.

- Upload malware, or content that is unlawful, defamatory, or infringing.

- Interfere with the operation of the Service, circumvent rate limits or access controls, or impose an unreasonable load on our infrastructure.

- Misrepresent AI generated output as having been verified by us, or present the Service as the statutory record.

We may investigate suspected breaches and take the steps set out in clause 18.

### 13. Our intellectual property

The Service, including its software, interfaces, design, structure, documentation, and the analysis, categorisation, enrichment and organisation we apply to public data, belongs to us or our licensors and is protected by intellectual property law. Nothing in this agreement transfers any of it to you.

We grant you a non-exclusive, non-transferable, revocable licence to use the Service during the term of this agreement, for your own internal business purposes or, if you are a consumer, your own personal purposes.

The underlying public records are not owned by us, and nothing here restricts your right to obtain them from their source.

If you send us feedback or suggestions, we may use them without restriction and without owing you anything.

### 14. Fees, billing and renewal

Some parts of the Service are free and some require payment. The price, the billing period and what is included are set out at the point of purchase.

Fees are stated exclusive of VAT unless we say otherwise, and you are responsible for any tax that applies. Payment is taken by our payment processor. We do not receive or store your full card details.

Where a plan renews automatically, we will tell you that clearly before you buy, and we will remind you before each renewal where the law requires it. You can cancel a renewal at any time before it takes effect, through your account or by contacting us. Cancelling stops the next renewal, and your access continues until the end of the period you have already paid for.

We may change our prices. For an existing paid plan, we will give you at least 30 days notice before a price change takes effect, and you may cancel before it does.

If a payment fails, we may suspend access until it is resolved.

Except where clause 15 or the law requires otherwise, fees already paid are not refundable.

### 15. If you are a consumer

This clause applies if you are an individual acting wholly or mainly outside your trade, business, craft or profession. It gives you rights in addition to the rest of this agreement, and where it conflicts with another clause, this clause wins.

Nothing in this agreement affects your statutory rights. Your rights under the Consumer Rights Act 2022, the European Union (Consumer Information, Cancellation and Other Rights) Regulations 2013, and other consumer protection law are not excluded, restricted or reduced by anything written here. If any clause purports to do so, it does not apply to you to that extent.

Right to cancel. You have 14 days from the day you enter into a paid contract with us to cancel it without giving a reason and receive a refund. To cancel, tell us at legal@eireplan.ie , or use the model cancellation form in the 2013 Regulations. We will refund you within 14 days of being told.

If you ask us to start straight away. If you ask us to begin providing the Service during the 14 day period, you can still cancel, but you must pay for what you have used up to the point of cancellation. If you receive digital content immediately, and you expressly consented to that and acknowledged that you would lose the right to cancel, the right to cancel that content is lost. We will ask for that consent and acknowledgement clearly and separately before delivery, and not by burying it here.

Complaints and dispute resolution. Please contact us first at legal@eireplan.ie . If we cannot resolve matters, you may use the European Commission's Online Dispute Resolution platform, and you may complain to the Competition and Consumer Protection Commission.

Courts. You may bring proceedings in the courts of the country where you live, and this agreement does not deprive you of the protection of the mandatory law of that country.

### 16. Availability

We aim to keep the Service available and to give notice of planned maintenance where we reasonably can. We do not promise that it will be uninterrupted, error free, or available at any particular time, and we do not offer a service level guarantee unless we have agreed one with you in writing.

The Service depends on third parties including hosting providers, authentication providers, payment processors, model providers and public data sources. Failures in those services can make the Service unavailable, and we do not control them.

### 17. Changes to the Service and to these Terms

We develop the Service continuously and may add, change, or remove features. Where we remove or materially reduce a feature that you pay for, we will give you at least 30 days notice, and if the change is materially detrimental to you, you may cancel and receive a pro rata refund of fees paid in advance for the period after cancellation.

We may change these Terms. Where a change is material, we will give you at least 30 days notice by email or in the Service, and we will ask you to accept the new version. Where a change is required by law or is needed to address a security risk, it may take effect sooner. If you do not accept a material change, your remedy is to stop using the Service and cancel, and we will refund fees paid in advance for the unused period.

### 18. Suspension and termination

You may close your account at any time.

We may suspend or terminate your access, in whole or in part, if:

- You are in material breach of this agreement, and, where the breach can be fixed, you have not fixed it within 14 days of us asking you to.

- You fail to pay.

- We are required to do so by law, or by a court, or by a regulator.

- Continuing to provide the Service to you would expose us or another user to a security risk, a legal claim, or serious harm.

Where the risk is immediate and serious, including suspected unauthorised access, fraud, or activity that threatens the integrity of the Service, we may suspend first and tell you afterwards. We will restrict a suspension to what is necessary and lift it as soon as the reason for it has gone.

On termination, your licence to use the Service ends. For 30 days afterwards, we will make your content available for export on request. After that we will delete or anonymise it in accordance with the Privacy Policy, except where we are required to keep it.

Clauses 7, 10, 13, 19, 20, 21, 22, 24 and 28 survive termination.

### 19. Warranties and disclaimers

We warrant that we will provide the Service with reasonable care and skill, and, if you are a consumer, to the standard required by the Consumer Rights Act 2022.

Subject to that warranty and to clause 20.1, and to the fullest extent permitted by law, the Service and all content, data, analysis, output, estimates and reporting within it are provided "as is" and "as available". We exclude all other warranties, conditions and terms, whether express, implied or statutory, including any implied warranty of merchantability, satisfactory quality, fitness for a particular purpose, accuracy, completeness, currency, or non-infringement.

We do not warrant that the Service will meet your requirements, that defects will be corrected, or that the data within it corresponds to the statutory record.

### 20. Liability

20.1 What we never exclude. Nothing in this agreement excludes or limits our liability for death or personal injury caused by our negligence, for fraud or fraudulent misrepresentation, for any liability that cannot lawfully be excluded or limited, or, where you are a consumer, for any liability under the Consumer Rights Act 2022 or other consumer protection law that cannot be excluded.

20.2 If you are a business. Subject to clause 20.1, we are not liable to you for:

- Loss of profit, revenue, business, contracts, anticipated savings or goodwill.

- Loss of, corruption of, or inability to access data, except to the extent caused by our failure to take the security measures described in clause 21.

- Loss arising from a planning decision, a refusal, a grant, a condition, an appeal, a judicial review, or the outcome of any application.

- Loss arising from a missed statutory or contractual deadline, however that deadline was displayed, calculated or omitted by the Service. Clause 7 explains why.

- Loss arising from reliance on AI output that has not been independently verified.

- Loss arising from an error, omission, delay or change in third party or public source data.

- Any indirect or consequential loss.

This applies however the liability arises, including in contract, tort, negligence, breach of statutory duty, restitution or otherwise, and whether or not we were told the loss was possible.

20.3 Cap, business users. Subject to clause 20.1, our total aggregate liability to a business user for all claims arising in any 12 month period is limited to the greater of the fees you actually paid us in the 12 months before the first event giving rise to the claim, or 500 euro.

20.4 Cap, consumers. Subject to clause 20.1, and without limiting any statutory right, our total aggregate liability to a consumer is limited to the loss that was reasonably foreseeable to both of us when the contract was made.

20.5 Your responsibility. The Service is a tool used by skilled people who exercise their own judgment. The allocation of risk in this clause reflects that, and it reflects the price of the Service, which is set on the basis that we do not carry the risk of the professional decisions you make using it.

20.6 Time limit. A business user must bring any claim within 12 months of becoming aware of the circumstances giving rise to it. This does not apply to consumers.

20.7 Free, trial and beta use. Subject to clause 20.1, where you use the Service without paying, on a free plan, during a trial, or where a feature is marked as beta, preview or experimental, that access is provided "as is" with no warranty of any kind, and our total aggregate liability to a business user in respect of it is limited to 100 euro. Beta features may be changed or withdrawn without notice and should not be used for work you depend on.

### 21. Security

We maintain technical and organisational measures appropriate to the risk, including encryption of data in transit and at rest, access control, tenant separation, least privilege administrative access, logging, and dependency monitoring. Further detail is in the Privacy Policy and the Data Processing Terms.

No system is perfectly secure. You are responsible for your own credentials, your devices, and the access you grant to members of your organisation.

If you believe you have found a vulnerability, please report it to security@eireplan.ie and give us a reasonable opportunity to fix it before disclosing it. We will not pursue a claim against anyone who reports a vulnerability in good faith, does not access or alter data beyond what is needed to demonstrate it, and does not disrupt the Service.

### 22. Confidentiality

Each of us may receive information from the other that is confidential. Each of us will keep the other's confidential information secret, use it only for the purposes of this agreement, and disclose it only to people who need it and are bound by equivalent obligations.

This does not apply to information that is public through no breach of this clause, was already known, is independently developed, or must be disclosed by law, and in that last case the disclosing party will give notice where it is lawful to do so.

We treat your project data, documents and site records as your confidential information.

### 23. Indemnity

This clause applies only if you are a business.

You will indemnify us against any loss, liability, cost and reasonable expense we suffer arising from a third party claim caused by your breach of clause 10, clause 11 or clause 12, or by content you upload.

We will tell you promptly of any such claim, will not admit liability without your consent, and will let you control the defence and give you reasonable assistance at your cost. You may not settle in a way that imposes an obligation on us without our consent.

### 24. Force majeure

Neither of us is liable for a failure to perform caused by an event beyond our reasonable control, including an outage at a hosting or infrastructure provider, a failure of public data sources, a cyber attack not caused by our failure to meet clause 21, an act of government, or a natural event. If the event continues for more than 30 days, either of us may terminate, and we will refund fees paid in advance for the unused period.

### 25. General

25.1 Notices. We will send notices to the email address on your account, and they take effect when sent. Send notices to us at legal@eireplan.ie .

25.2 Assignment by you. You may not assign or transfer this agreement without our written consent, which we will not unreasonably withhold.

25.3 Transfer by us. We may assign or transfer this agreement, in whole or in part, to a company that we incorporate to carry on this business, or as part of a merger, reorganisation or sale of the business or its assets. We will tell you if we do. Your rights under this agreement will not be reduced as a result, and if a transfer would materially prejudice you, you may terminate and receive a pro rata refund of fees paid in advance.

25.4 Subcontracting. We may use subcontractors and sub-processors to provide the Service, and we remain responsible to you for their performance.

25.5 Entire agreement. This agreement is the whole agreement between us on its subject matter, and it replaces anything said or written before it. Neither of us relies on any statement not written in it. This does not limit liability for fraudulent misrepresentation, and it does not apply to consumers to the extent it would exclude a statutory right.

25.6 Severability. If a clause is found to be unenforceable, it is modified to the minimum extent needed to make it enforceable, or, if that is not possible, removed. The rest of the agreement continues.

25.7 No waiver. If we do not enforce a right, that is not a waiver of it.

25.8 No third party rights. Nobody other than you and us may enforce this agreement.

25.9 No partnership. Nothing here creates a partnership, joint venture, agency or employment relationship.

### 26. Export, sanctions and anti-bribery

You confirm that you are not subject to EU or UN sanctions, and that you will not use the Service in breach of sanctions or export control law. Each of us will comply with applicable anti-bribery and anti-corruption law.

### 27. Governing law and jurisdiction

This agreement, and any dispute arising out of it or its subject matter, is governed by the laws of Ireland.

The courts of Ireland have exclusive jurisdiction, except that if you are a consumer, clause 15 applies and you may bring proceedings in the courts of the country where you live.

### 28. Contact

Neri Carcasci, trading as EirePlan
[REGISTERED ADDRESS TO BE INSERTED BEFORE PUBLICATION], Ireland

Contractual matters: legal@eireplan.ie Data protection: privacy@eireplan.ie Security: security@eireplan.ie General: hello@eireplan.ie

---

# Page 72: Talk to us about a plan — EirePlan

Source URL: https://eireplan.com/contact

Skip to main content

← Back to pricing

## Talk to us about a plan

Everything past the free account is arranged in a conversation rather than a checkout page. Tell us what you are working on and we will set up something that fits it.

### What happens next

- 01

#### We read it

Not a sales team — the people building this. Usually a reply within one working day.

- 02

#### A short conversation

What you are working on, how many people need it, and which authorities have to be covered. Twenty minutes, and only if it is useful.

- 03

#### We set the plan up

Configured against what you actually need. No card details are taken at any point in this — we are not charging yet.

Would rather just email? hello@eireplan.ie reaches the same inbox.

---

# Page 73: Get Knowledge Document — EirePlan API docs

Source URL: https://eireplan.com/docs/endpoints-knowledge/get-document

Skip to main content

API Reference

API Reference EirePlan for developers

Use this request when you already have a docId and want the complete metadata and resource links for one document.

### # Request

GET /ext/v1/knowledge/docs/:docId

### # Path Parameters

Parameter Type Required Description

docId string Yes Document UUID returned by the list endpoint.

### # Example Request

curl "https://api.eireplan.ie/ext/v1/knowledge/docs/7af4c2d9-87ea-4887-8d8f-95e20b25a1a5" \ -H "Authorization: Bearer ek_your_api_key_here"

### # Response Structure

Field Type Description

document.doc_id string (UUID) Unique document identifier.

document.metadata.document_title string Official title.

document.metadata.short_reference_name string Short reference label.

document.metadata.document_type string Document classification.

document.metadata.planning_system_level string Jurisdiction level.

document.metadata.current_status string Current validity status.

document.metadata.issuing_body_name string Issuing body.

document.metadata.adoption_commencement_date string Effective date where available.

document.metadata.geographic_scope array Covered geographic areas.

document.metadata.used_by_ai_for array Typical AI usage categories.

document.base_url string Official source link.

document.pdf_url string Direct PDF link when available.

document.updated_at string Last updated timestamp.

document.created_at string Creation timestamp.

### # Example Response

json

{ "document" : { "doc_id" : "7af4c2d9-87ea-4887-8d8f-95e20b25a1a5" , "metadata" : { "document_title" : "Sustainable Residential Development and Compact Settlements Guidelines" , "short_reference_name" : "SRD Guidelines" , "document_type" : "Ministerial Guidelines" , "planning_system_level" : "National" , "current_status" : "In force" , "issuing_body_name" : "Department of Housing, Local Government and Heritage" , "adoption_commencement_date" : "2024-03-01" , "geographic_scope" : [ "Statewide" ] , "used_by_ai_for" : [ "Policy compliance checks" , "Planning analysis" ] } , "base_url" : "https://www.gov.ie/example-guidelines" , "pdf_url" : "https://storage.eireplan.ie/knowledge/example-guidelines.pdf" , "updated_at" : "2026-01-14T11:20:00Z" , "created_at" : "2025-11-07T09:02:00Z" } }

### # Where It Fits

Start with List Knowledge Docs if you do not already know the document identifier you need.

---

# Page 74: List Knowledge Docs — EirePlan API docs

Source URL: https://eireplan.com/docs/endpoints-knowledge/list-docs

Skip to main content

API Reference

API Reference EirePlan for developers

Use this request to search the knowledge base and return document metadata in pages.

### # Request

GET /ext/v1/knowledge/docs

### # When To Use It

- You need to browse the knowledge catalog.

- You want to filter by jurisdiction, document type, or policy domain.

- You need doc_id values for follow-up detail requests.

### # Query Parameters

Parameter Type Required Description Example(s)

jurisdiction string No Filter by planning system level or local authority. Use National for national guidance. National , Dublin City Council

document_type string No Filter by document type. Ministerial Guidelines

policy_domain string No Filter by planning policy domain or topic area. Housing standards & mix

limit integer No Maximum documents per request, from 1 to 100. Default is 20. 50

offset integer No Result offset for pagination. 0

### # Example Request

curl "https://api.eireplan.ie/ext/v1/knowledge/docs?jurisdiction=National&limit=2" \ -H "Authorization: Bearer ek_your_api_key_here"

### # Response Structure

Field Type Description

documents array List of knowledge documents matching the query.

total integer Total number of matching documents.

limit integer The applied page size.

offset integer The applied result offset.

has_more boolean Whether another page is available after this one.

Each item in documents includes:

Field Type Description

doc_id string (UUID) Stable document identifier.

metadata.document_title string Full official title.

metadata.short_reference_name string Short reference name for display.

metadata.planning_system_level string National, Regional, or Local.

metadata.document_type string Document classification.

metadata.current_status string Current document status.

metadata.issuing_body_name string Issuing authority or organization.

metadata.key_policy_domains array Main policy themes covered.

base_url string Official source URL.

updated_at string Last update timestamp in ISO 8601 format.

### # Example Response

json

{ "documents" : [ { "doc_id" : "7af4c2d9-87ea-4887-8d8f-95e20b25a1a5" , "metadata" : { "document_title" : "Sustainable Residential Development and Compact Settlements Guidelines" , "short_reference_name" : "SRD Guidelines" , "planning_system_level" : "National" , "document_type" : "Ministerial Guidelines" , "current_status" : "In force" , "issuing_body_name" : "Department of Housing, Local Government and Heritage" , "key_policy_domains" : [ "Housing standards & mix" , "Urban design & placemaking" ] } , "base_url" : "https://www.gov.ie/example-guidelines" , "updated_at" : "2026-01-14T11:20:00Z" } ] , "total" : 42 , "limit" : 2 , "offset" : 0 , "has_more" : true }

### # Next Step

Use the returned doc_id with Get Knowledge Document when you want the complete record for a specific document.

---

# Page 75: Get Precedent Details — EirePlan API docs

Source URL: https://eireplan.com/docs/endpoints-precedents/get-by-id

Skip to main content

API Reference

API Reference EirePlan for developers

Use this request when you already have a precedent id and need the richer detail record.

### # Request

GET /ext/v1/precedents/:id

### # Path Parameters

Parameter Type Required Description

id string Yes Precedent UUID returned by the search endpoint.

### # Query Parameters

Parameter Type Required Description

geometry string No How much site geometry to return: simplified (default), full , or none . Any other value returns 400 .

simplified is the right default for mapping — it returns a boundary with reduced
vertex detail, which is what you want on a web map. Use full only when you need
the boundary at its published precision, and none to skip the geometry lookup
entirely when you just want the record.

Site boundaries are fetched live from the national dataset rather than stored, so
this lookup can fail. When it does the request still succeeds: polygon is
omitted and has_polygon comes back false . Treat a missing polygon as
"no boundary available right now", not as "this site has no boundary".

### # Example Request

curl "https://api.eireplan.ie/ext/v1/precedents/5f8fcb68-2be1-4ce7-8ef4-6a29c2fb4aa8" \ -H "Authorization: Bearer ek_your_api_key_here"

### # Response Structure

Field Type Description

precedent.id string (UUID) Unique precedent identifier.

precedent.planning_ref string Official planning reference.

precedent.address string Site address.

precedent.description string Application description.

precedent.applicant string Applicant or developer name.

precedent.local_authority string Responsible authority.

precedent.decision_norm string Normalized decision value.

precedent.received_date string Received date.

precedent.decision_date string Final decision date.

precedent.official_record_url string Link to the official planning record.

precedent.official_docs_url string Link to official planning documents.

precedent.has_polygon boolean Whether site boundary geometry was available for this request.

precedent.point object GeoJSON Point geometry for the site location. This is the geocoded application address, not a surveyed position.

precedent.polygon object GeoJSON Polygon or MultiPolygon geometry for the site boundary. Omitted when has_polygon is false or geometry=none was requested.

### # Example Response

json

{ "precedent" : { "id" : "5f8fcb68-2be1-4ce7-8ef4-6a29c2fb4aa8" , "planning_ref" : "DCC-1234-25" , "address" : "15 Example Street, Dublin 2" , "description" : "Mixed-use development with 42 apartments" , "applicant" : "Example Developments Ltd" , "local_authority" : "Dublin City Council" , "decision_norm" : "granted" , "received_date" : "2025-03-12" , "decision_date" : "2025-08-07" , "official_record_url" : "https://planning.localauthority.ie/records/DCC-1234-25" , "official_docs_url" : "https://planning.localauthority.ie/docs/DCC-1234-25" , "has_polygon" : true , "point" : { "type" : "Point" , "coordinates" : [ -6.2603 , 53.3498 ] } } }

### # Where It Fits

Start with Search Precedents if you do not already have the precedent identifier.

To plot a set of results on a map, see the worked example in Site History by Boundary — the site-history responses carry no coordinates, so geometry comes from this request.

---

# Page 76: Search Precedents — EirePlan API docs

Source URL: https://eireplan.com/docs/endpoints-precedents/search

Skip to main content

API Reference

API Reference EirePlan for developers

Use this request to search precedent records across Ireland and return a lightweight result set you can page through.

### # Request

GET /ext/v1/precedents

### # Query Parameters

Parameter Type Required Description Example

q string No Full-text search query across address, description, applicant name, and planning reference. apartment , residential

local_authority string No Filter by local authority. Dublin City Council

status string No Filter by normalized status. decided

decision string No Filter by normalized decision. granted

limit integer No Maximum results per page, from 1 to 100. Default is 20. 50

offset integer No Pagination offset. 0

### # Example Request

curl "https://api.eireplan.ie/ext/v1/precedents?q=apartment&local_authority=Dublin%20City%20Council&limit=2" \ -H "Authorization: Bearer ek_your_api_key_here"

### # Response Structure

Field Type Description

precedents array Search results for the current page.

next string Cursor for the next page, or null when there is no next page.

Each item in precedents includes:

Field Type Description

id string (UUID) Stable precedent identifier.

planning_ref string Official planning reference.

address string Site address.

description string Application description.

local_authority string Responsible authority.

decision_norm string Normalized decision value.

status_norm string Normalized status value.

type_norm string Normalized application type.

received_date string Date received in ISO 8601 format.

decision_date string Date decided in ISO 8601 format.

is_favourite boolean Whether the precedent is in the watchlist.

### # Example Response

json

{ "precedents" : [ { "id" : "5f8fcb68-2be1-4ce7-8ef4-6a29c2fb4aa8" , "planning_ref" : "DCC-1234-25" , "address" : "15 Example Street, Dublin 2" , "description" : "Mixed-use development with 42 apartments" , "local_authority" : "Dublin City Council" , "decision_norm" : "granted" , "status_norm" : "decided" , "type_norm" : "permission" , "received_date" : "2025-03-12" , "decision_date" : "2025-08-07" , "is_favourite" : false } ] , "next" : "eyJvZmZzZXQiOjJ9" }

### # Next Step

Use the returned id with Get Precedent Details when you need the full record for one result.

---

# Page 77: Site History — EirePlan API docs

Source URL: https://eireplan.com/docs/endpoints-precedents/site-history

Skip to main content

API Reference

API Reference EirePlan for developers

Use this request to find planning application history around a site using address text, eircode, or map coordinates.

### # Request

GET /ext/v1/precedents/site-history

### # Valid Query Combinations

- Address search: address can be passed once or repeated (for example, address=...&address=... ).

- Eircode search: pass eircode when you have a known postal code.

- Coordinate search: pass lat and lon together, with optional radius_m .

You can include limit with any of the combinations above.

If you already hold the site's extent — a folio parcel, a red-line application
area, or a polygon drawn on a map — use Site History by Boundary instead of approximating it with radius_m . It returns the same response shape.

Defaults:

- radius_m defaults to 5 .

- limit defaults to 100 .

### # Query Parameters

Parameter Type Required Description Example(s)

address string No Site address text. Supports single or repeated query params. address=15%20Example%20Street , repeated address keys

eircode string No Irish eircode for the site. D02 X285

lat number No Latitude for coordinate-based search. Use with lon . 53.3498

lon number No Longitude for coordinate-based search. Use with lat . -6.2603

radius_m integer No Radius in meters for coordinate search. Must be greater than 0. Default is 5 . 25

limit integer No Maximum records returned. Must be greater than 0. Default is 100 . 50

### # Example Request

curl "https://api.eireplan.ie/ext/v1/precedents/site-history?address=15%20Example%20Street&address=15%20Example%20St%2C%20Dublin%202&eircode=D02%20X285&lat=53.3498&lon=-6.2603&radius_m=25&limit=20" \ -H "Authorization: Bearer ek_your_api_key_here"

### # Response Shape

{ "result": { query_* fields, query_radius_m, used_fallbacks, summary, precedents, source } }

### # Response Structure

Field Type Description

result.query_address string Primary normalized address used for lookup, when available.

result.query_addresses array Normalized address candidates used in the request.

result.query_eircode string Normalized eircode used for lookup, when available.

result.query_lat number Effective latitude used for the query, when available.

result.query_lon number Effective longitude used for the query, when available.

result.query_radius_m integer Applied search radius in meters.

result.used_fallbacks array Any fallback strategies used to complete the lookup.

result.summary.total_applications integer Total matched applications in this result set.

result.summary.decision_counts object Counts by normalized decision.

result.summary.type_counts object Counts by normalized application type.

result.precedents array Matching precedent records near or matching the site input.

result.source string Data source strategy used for the search.

### # Example Response

json

{ "result" : { "query_address" : "15 Example Street" , "query_addresses" : [ "15 Example Street" , "15 Example St, Dublin 2" ] , "query_eircode" : "D02 X285" , "query_lat" : 53.3498 , "query_lon" : -6.2603 , "query_radius_m" : 25 , "used_fallbacks" : [ "address_normalization" ] , "summary" : { "total_applications" : 2 , "decision_counts" : { "granted" : 1 , "refused" : 1 } , "type_counts" : { "permission" : 2 } } , "precedents" : [ { "id" : "5f8fcb68-2be1-4ce7-8ef4-6a29c2fb4aa8" , "planning_ref" : "DCC-1234-25" , "address" : "15 Example Street, Dublin 2" , "decision_norm" : "granted" } , { "id" : "f40db59f-91f5-478c-a5ab-5c1b6086f7cd" , "planning_ref" : "DCC-9981-24" , "address" : "18 Example Street, Dublin 2" , "decision_norm" : "refused" } ] , "source" : "db_bbox" } }

### # Where It Fits

Use Site History after Search Precedents when you need neighborhood context around a known site before drilling into one precedent by id .

When you have a drawn or imported site boundary rather than an address, use Site History by Boundary .

---

# Page 78: Site History by Boundary — EirePlan API docs

Source URL: https://eireplan.com/docs/endpoints-precedents/site-history-boundary

Skip to main content

API Reference

API Reference EirePlan for developers

Search planning history inside a site boundary rather than around a point.

Use this when you already hold the site's extent — a folio parcel, a red-line
application area, a title map, or a polygon a user drew on a map — and would
otherwise have to approximate it with a radius. The boundary states exactly which
site you mean, so a 90 m frontage and a 9 m one are no longer the same query.

Everything about Site History stays as
it is. This is an alternative entry point that returns the identical response
envelope, so both can render through the same code path.

### # Request

POST /ext/v1/precedents/site-history/polygon

### # Body

Field Type Required Description

geometry object Yes A GeoJSON Polygon or MultiPolygon geometry object. Not a Feature , not a FeatureCollection — see below.

limit integer No Maximum records returned. Default 200 , capped at 500 .

json

{ "geometry" : { "type" : "Polygon" , "coordinates" : [ [ [ -6.26400 , 53.34500 ] , [ -6.26340 , 53.34500 ] , [ -6.26340 , 53.34527 ] , [ -6.26400 , 53.34527 ] , [ -6.26400 , 53.34500 ] ] ] } , "limit" : 200 }

### # Geometry Rules

These are the four rules that matter:

- Coordinate order is [longitude, latitude] , not [lat, lon] . This is the
GeoJSON convention and it is the reverse of how the lat / lon query
parameters are named elsewhere in this API. Getting it backwards is the one
mistake that does not raise an error: a ring written as [53.345, -6.264] puts your site in the Indian Ocean and quietly returns zero results. An empty
result from a boundary you know is populated is almost always this.

- Rings must be closed. The last coordinate pair must repeat the first, so a
ring needs at least four positions. Fewer than four is rejected with 400 ; an
unclosed ring of four or more is currently rejected further down the stack and
surfaces as a 500 , so treat closing the ring as your responsibility rather
than relying on the error to be descriptive.

- WGS84 (EPSG:4326) only. Irish Transverse Mercator (EPSG:2157) and Irish
Grid (EPSG:29903) coordinates are rejected as out of range with 400 .
Reproject before sending — most Irish folio and red-line data arrives in ITM.

- Type must be Polygon or MultiPolygon . Feature , GeometryCollection , LineString , and bare coordinate arrays are all rejected with 400 .

Area is capped at 5 km² , returning 413 . A red-line application boundary is
typically a few hundred to a few thousand square metres, so this only bites if you
send an estate, a townland, or an accidentally malformed ring whose extent spans
the country.

One caveat on that cap: area is measured by summing every ring, so interior rings
(holes) add to the measured area instead of subtracting from it. A doughnut-shaped
boundary measures larger than it really is. Well under the cap this never matters;
near it, send the outer ring alone.

### # Sending a Boundary You Already Have

GIS exports almost never hand you a bare geometry. They hand you a Feature or a FeatureCollection , and posting one of those verbatim is the most common 400 on
this endpoint. Unwrap it first:

javascript

// From a Feature const geometry = feature . geometry ; // From a FeatureCollection — first feature const geometry = featureCollection . features [ 0 ] . geometry ; // From a Leaflet layer (already WGS84) const geometry = layer . toGeoJSON ( ) . geometry ;

A full Feature looks like this. The part you send is the value of geometry and
nothing else — properties is discarded and is not echoed back:

json

{ "type" : "Feature" , "properties" : { "site_ref" : "INFILL-01" , "area_ha" : 0.12 } , "geometry" : { "type" : "Polygon" , "coordinates" : [ [ [ -6.26400 , 53.34500 ] , [ -6.26340 , 53.34500 ] , [ -6.26340 , 53.34527 ] , [ -6.26400 , 53.34527 ] , [ -6.26400 , 53.34500 ] ] ] } }

Use a MultiPolygon when one site is split into parts — a plot severed by a
laneway, or a landholding in two blocks. Send it as a single request rather than
one request per part, so the returned counts describe the whole site:

json

{ "geometry" : { "type" : "MultiPolygon" , "coordinates" : [ [ [ [ -6.26400 , 53.34500 ] , [ -6.26340 , 53.34500 ] , [ -6.26340 , 53.34527 ] , [ -6.26400 , 53.34527 ] , [ -6.26400 , 53.34500 ] ] ] , [ [ [ -6.26310 , 53.34500 ] , [ -6.26260 , 53.34500 ] , [ -6.26260 , 53.34522 ] , [ -6.26310 , 53.34522 ] , [ -6.26310 , 53.34500 ] ] ] ] } }

### # Example Request

curl -X POST "https://api.eireplan.ie/ext/v1/precedents/site-history/polygon" \ -H "Authorization: Bearer ek_your_api_key_here" \ -H "Content-Type: application/json" \ -d '{ "geometry": { "type": "Polygon", "coordinates": [[[-6.26400, 53.34500], [-6.26340, 53.34500], [-6.26340, 53.34527], [-6.26400, 53.34527], [-6.26400, 53.34500]]] }, "limit": 200 }'

### # Drawing a Boundary on a Map

Any draw control that emits GeoJSON works. With Leaflet and Leaflet.draw, take the
geometry straight off the drawn layer — Leaflet already works in WGS84 and already
closes the ring for you:

javascript

const map = L . map ( "map" ) . setView ( [ 53.34513 , - 6.26370 ] , 19 ) ; const drawnItems = new L . FeatureGroup ( ) . addTo ( map ) ; map . addControl ( new L . Control . Draw ( { draw : { polygon : true , rectangle : true , marker : false , polyline : false , circle : false } , edit : { featureGroup : drawnItems } , } ) ) ; map . on ( L . Draw . Event . CREATED , async ( event ) => { drawnItems . clearLayers ( ) ; drawnItems . addLayer ( event . layer ) ; const geometry = event . layer . toGeoJSON ( ) . geometry ; const result = await searchSiteHistory ( geometry ) ; // the fetch call above renderPlanningHistory ( result ) ; } ) ;

If you use MapLibre with Mapbox Draw, draw.getAll() returns a FeatureCollection — unwrap it as shown above before sending.

### # Response Shape

Identical to Site History : { "result": { summary, precedents, used_fallbacks, source, … } } . Two fields
differ in a way worth handling:

Field Value here Why

result.source user_polygon Records that the area came from you, not from a geocode or a radius.

result.query_radius_m 0 No radius was involved. Do not render it as "searched within 0 m".

Every returned precedent carries the strongest match signals, because a hit means
the application's point falls inside the area you defined:

Field Value

match_reason user_polygon

confidence_tier S

same_site_confidence 0.95

same_site_signals ["user_polygon"]

### # Example Response

json

{ "result" : { "query_radius_m" : 0 , "used_fallbacks" : [ "user_polygon" ] , "summary" : { "total_applications" : 2 , "decision_counts" : { "GRANTED" : 1 , "REFUSED" : 1 } , "type_counts" : { "PERMISSION" : 2 } } , "precedents" : [ { "id" : "5f8fcb68-2be1-4ce7-8ef4-6a29c2fb4aa8" , "planning_ref" : "DCC-1234-25" , "address" : "15 Example Street, Dublin 2" , "decision_norm" : "granted" , "match_reason" : "user_polygon" , "confidence_tier" : "S" , "same_site_confidence" : 0.95 , "same_site_signals" : [ "user_polygon" ] } , { "id" : "f40db59f-91f5-478c-a5ab-5c1b6086f7cd" , "planning_ref" : "DCC-9981-24" , "address" : "15 Example Street, Dublin 2" , "decision_norm" : "refused" , "match_reason" : "user_polygon" , "confidence_tier" : "S" , "same_site_confidence" : 0.95 , "same_site_signals" : [ "user_polygon" ] } ] , "source" : "user_polygon" } }

### # Putting the Results Back on the Map

The site-history response carries no coordinates — it is a list of records, not a
feature collection. To plot the results, fetch geometry per precedent from Get Precedent Details , which returns a
GeoJSON point and, where the authority publishes one, a polygon :

javascript

async function toFeatureCollection ( precedents , apiKey ) { const features = await Promise . all ( precedents . map ( async ( precedent ) => { const response = await fetch ( ` https://api.eireplan.ie/ext/v1/precedents/ ${ precedent . id } ?geometry=simplified ` , { headers : { Authorization : ` Bearer ${ apiKey } ` } } ) ; const { precedent : detail } = await response . json ( ) ; // Prefer the published site boundary; fall back to the address point. const geometry = detail . polygon ?? detail . point ; if ( ! geometry ) return null ; return { type : "Feature" , geometry , properties : { planning_ref : detail . planning_ref , decision : detail . decision_norm , address : detail . address , } , } ; } ) ) ; return { type : "FeatureCollection" , features : features . filter ( Boolean ) } ; } const collection = await toFeatureCollection ( result . precedents , apiKey ) ; L . geoJSON ( collection , { style : ( feature ) => ( { color : feature . properties . decision === "refused" ? "#b4342a" : "#2f6b45" , weight : 2 , } ) , } ) . addTo ( map ) ;

That is one metered request per precedent, so plot the precedents a user actually
asked to see rather than the whole result set. Pass geometry=none on detail
requests where you need the record but not the shape.

### # What the Boundary Does and Does Not Prove

The query tests each precedent's address point against your area. That point is
the geocoded application address, and it is the least reliable field in the record:
an application registered to one house number routinely sits tens of metres from
its neighbour's pin, and authorities frequently geocode a large site to its road
frontage.

So a boundary tells you precisely which site you mean. It is not proof of where
the application was.

- A hit is a strong positive signal. The point is inside your site.

- A miss is inconclusive, not a rejection. A permission on your own site that
the authority geocoded to the road would silently disappear.

Treat the boundary as a confirming signal alongside address and eircode identity,
never as the sole filter. For a complete picture, run the boundary search and the
address or eircode search at Site History , then merge the two result
sets on precedent id .

### # Errors

Status Meaning

400 geometry missing, malformed JSON body, wrong geometry type, a ring with fewer than four positions, or coordinates outside valid lon/lat range — the usual cause of the last being unprojected ITM or Irish Grid coordinates.

401 Missing or invalid API key.

413 Boundary area exceeds 5 km².

500 Includes geometry that passes the checks above but that the spatial engine rejects — in practice, an unclosed ring. Close the ring and retry before treating it as an outage.

### # Where It Fits

Use this instead of a radius whenever you hold a real site extent. Use Site History when all you have is an
address or eircode, and Get Precedent Details to expand any id either one returns.
