# Revision evidence annotation guide

`revision_evidence_annotation_registry.csv` contains one row per manually accepted refused-to-revised-to-granted pair. It is an evidence worklist, not a model-input table. If the CSV is open in Excel when regenerated, use the automatically created `revision_evidence_annotation_registry_with_links.csv` (or close the workbook and rerun the generator).

For each row, read the original refusal material and revised application source. Fill only changes you can support from those source documents:

- `addressed_refusal_theme`: short controlled description of the issue addressed.
- `change_layout_design`, `change_access_parking`, `change_open_space_amenity`, `change_drainage_environment`, `change_policy_land_use`: concise source-backed change descriptions.
- `source_backed_change_note`: the specific comparison evidence.
- `annotation_confidence`: `high`, `medium`, or `low`.

Do not use blank extracted numeric values to mean "unchanged". Do not infer that a change caused permission; the registry supports future comparable evidence and sensitivity framing only.

## Completed annotation export

Run `python 02_development/scripts/build_completed_revision_evidence.py` after saving the completed workbook as `revision_evidence_annotation_registry_with_links_fixed.csv`.

- `revision_evidence_annotations_validated.csv` preserves every validated manual annotation.
- `revision_intervention_evidence.csv` contains only pairs marked `yes` or `partial` for the relationship between the observed change and refusal issue, with at least one observed change category.
- `revision_evidence_annotation_summary.json` reports coverage and confidence counts.

Rows marked `unclear` remain valuable context but are deliberately excluded from intervention evidence.

## Automated review cues

`automated_review_cues` is a short-listing aid. It appears only where the refusal text and revised description share a relevant theme, such as `density_scale` or `drainage_environment`. Confirm or clear every cue using the linked source documents; a cue is not a finding that the revised scheme addressed the issue or that it caused the grant.
