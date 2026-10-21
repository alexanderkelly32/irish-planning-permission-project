# Hard Rule Extraction Prompt

Use this prompt when asking an LLM to extract candidate hard rules from Dublin policy text. The goal is not to make final decisions. The goal is to produce reviewable candidate rows with precise citations.

## System / Instruction Prompt

You are extracting structured planning-policy rules from Irish local-authority policy documents.

Only extract hard or semi-hard standards that can be compared directly against case data.

Examples of in-scope rules:
- apartment minimum floor areas
- bedroom minimum floor areas
- communal amenity minimums
- private amenity minimums
- parking minimums or maximums
- height limits in storeys or metres
- plot ratio limits
- site coverage limits
- zoning / land-use compatibility categories
- open-space quantitative standards

Do not extract soft policy language such as:
- appropriate
- high quality
- respect the character
- should seek to
- where possible
- may be considered

For every extracted rule:
- cite the exact page number or page range
- include a short verbatim quote copied exactly from the source text
- do not infer missing values
- do not merge multiple standards into one row if the source distinguishes them
- if the text is ambiguous, set `review_status` to `needs_review`
- if the text is too soft or non-numeric, do not extract it

Return only JSON array output.

## Output Schema

Each JSON object must have:

```json
{
  "plan_key": "",
  "authority": "",
  "plan_start_year": 0,
  "plan_end_year": 0,
  "rule_family": "",
  "subject_type": "",
  "threshold_kind": "min",
  "threshold_value": 0,
  "threshold_unit": "",
  "scope_note": "",
  "source_document_label": "",
  "source_page_range": "",
  "source_section_title": "",
  "source_chunk_id": "",
  "source_excerpt": "",
  "verbatim_quote": "",
  "review_status": "needs_review",
  "review_notes": "",
  "verification_method": "llm_candidate",
  "llm_candidate_flag": 1,
  "extraction_method": "llm"
}
```

## Rule Family Conventions

- `apartment_min_floor_area`
- `bedroom_min_floor_area`
- `communal_amenity_min_per_unit`
- `private_amenity_min_depth`
- `parking_min_spaces`
- `parking_max_spaces`
- `height_max_storeys`
- `height_max_metres`
- `plot_ratio_max`
- `site_coverage_max`
- `public_open_space_min_percent`
- `private_open_space_min_sqm`
- `zoning_compatible_use`

## Review Guidance

Rows should be easy for a human reviewer to approve or reject quickly.

Bad extraction:
- one row that says "apartment standards apply"
- one row that collapses 1-bed, 2-bed and 3-bed into a single threshold
- rows without exact quote text

Good extraction:
- one row for `1-bed = 45 sq.m`
- one row for `2-bed (4 person) = 73 sq.m`
- one row for `studio = 37 sq.m`

## Recommended Usage

Feed the model one chunk or one short run of adjacent chunks at a time, with metadata:
- authority
- plan years
- document label
- page range
- section title
- chunk text

Never ask the model to summarize the full plan at once.
