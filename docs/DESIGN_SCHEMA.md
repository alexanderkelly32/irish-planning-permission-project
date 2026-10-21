# Development-Design Schema v1 (counterfactual optimiser)

Every design version records: value, units, source, extraction method,
confidence, observation date, and class. Classes:

## Immutable (site-level)
site_location, site_area_m2, planning_authority, zoning, settlement_type,
flood_constraints, ecology_constraints, transport_access, surrounding_form,
site_history, protected_structures, access_constraints.

## Mutable (design-level)
total_units, units_per_ha, house_apartment_mix, unit_type_mix (bedrooms),
block_count, max_storeys, gross_floor_area_m2, site_coverage_pct, plot_ratio,
private_open_space_m2, communal_open_space_m2, public_open_space_m2,
parking_spaces, cycle_spaces, access_points, traffic_generation_est,
childcare_bool, tenure_partv_bool, demolition_bool, retention_bool,
phasing_plan, density_massing, description_text (as the textual projection
of real design choices).

## Derived (recompute on every mutation - never left stale)
units_per_ha = total_units / site_area_ha
parking_ratio = parking_spaces / total_units
open_space_per_unit = total_open_space / total_units
floor_area_est = sum(unit_type floor areas) + ancillary
traffic_intensity = f(trip rates, unit mix, parking)
childcare_threshold = f(total_units, policy band)
house_apartment_share = mix proportions
description_text = deterministic regeneration from the structured fields

## Extraction sources (priority order)
1. register structured fields (units, site area, floor area, description)
2. iDocs site-layout/schedule documents (deterministic parsing)
3. FI responses / revised plans / planner reports (text)
4. vision-language extraction on drawings (last resort, audit-gated)

## Lineage versioning
version_id, case_key, version_type (original | fi_revision | amended |
refused | resubmission | appeal | later_grant), match_confidence,
relationship (same_proposal_revised | replacement | additional_phase |
unrelated). Deltas are computed only across linked versions.

## Policy constraints
Any planning-policy constraint (density bands, height, parking standards)
must cite the official development plan or statutory guidance IN FORCE on
the application date. Policy versions are date-aware (policy regime table
in silver/usp/e2_e3_report.json).
