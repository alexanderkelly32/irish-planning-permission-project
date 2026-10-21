# Grant-condition corpus plan (engine c)

Goal: audited labels `P(condition_family | grant)` for the pilot, per product
brief 6.7. Current: regex starter labels on 17 verified reports; classifier
and corpus runner built; network crawl pending retry.

## Pipeline (built)

`09_devrisk/scripts/run_condition_corpus.py` — resumable, polite (1s delay):
1. Candidate queue: 166 granted pool schemes with eplanning detail URLs
   (Carlow + Meath default; any authority supported).
2. Reuses `02_development/scripts/planner_report_downloader.py`
   (ePlan → iDocs planner-report flow) to fetch planner-report PDFs.
3. Native text extraction (PyMuPDF/fitz); condition-family classification
   (`devrisk/reporting/condition_families.py`, 11 families, regex v1).
4. Exports `condition_corpus/condition_family_labels_pilot.csv` + state/summary.

## Blocker observed 2026-09-28

Smoke run (limit 2): eplanning.ie closed connections from this environment
(`RemoteDisconnected`). Not a code issue; retry at a different time/session
or from the user's browser session. State file is resumable
(`condition_corpus/state.json`).

## After download succeeds

1. Label ~50-100 granted reports across Carlow + Meath.
2. Export an audit pack (per-scheme family flags + evidence snippets).
3. Human audit (inter-rater kappa >= 0.70 for high-impact families per
   `configs/rules/pilot_gates.yaml`).
4. Fit `P(family | grant, submission features)` models; report conditional
   calibration; then wire into report 6.7 replacing starter priors.

## Upgrade path

LLM extraction under the `condition_families_v1` contract (evidence spans,
confidence, reviewer disposition) replaces regex once audit precision is
known; prompts/model versioned per the technical brief section 11.
