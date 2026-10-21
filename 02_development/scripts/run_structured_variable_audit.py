#!/usr/bin/env python3
"""Run the structured-variable audit (Task 1) and write the audit package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from audit_structured_variables import (
    EXTRACTED_FIELDS,
    PLAUSIBLE_BOUNDS,
    REGISTER_FIELDS,
    derive_density_plot_ratio,
    distribution_table,
    field_coverage,
    grouped_coverage,
    recommend_ready_fields,
)

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "structured_variable_audit_2026-09-04"
DEFAULT_PARQUET = ROOT / "old_original_attempt" / "first_attempt_messy" / "irish_planning_dataset_clean_model.parquet"
DEFAULT_EXTRACTED = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_ge10_fixed.csv"

RESIDENTIAL_TERMS = r"\b(?:apartment|apartments|dwelling|dwellings|house|houses|housing|residential|home|homes|retirement village|student accommodation|one-off|one off)\b"


def load_register(path: Path) -> pd.DataFrame:
    columns = [
        "PlanningAuthority", "ApplicationNumber", "ApplicationType", "DevelopmentDescription",
        "Decision", "ReceivedDate", "NumResidentialUnits", "AreaofSite", "FloorArea", "OneOffHouse",
        "ITMEasting", "ITMNorthing",
    ]
    frame = pd.read_parquet(path, columns=columns)
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    residential = units.gt(0) | frame["OneOffHouse"].fillna("").astype(str).str.strip().str.lower().isin(
        {"y", "yes", "one", "single house"}
    )
    residential |= frame["DevelopmentDescription"].fillna("").astype(str).str.contains(RESIDENTIAL_TERMS, case=False, regex=True)
    frame = frame[residential].copy()
    frame["received_year"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce").dt.year
    frame = derive_density_plot_ratio(frame)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--extracted", type=Path, default=DEFAULT_EXTRACTED)
    args = parser.parse_args()

    register = load_register(args.parquet)
    extracted = pd.read_csv(args.extracted, low_memory=False)
    extracted["received_year"] = pd.to_datetime(extracted["ReceivedDate"], errors="coerce").dt.year
    extracted["Decision"] = extracted["Decision"].fillna("").astype(str).str.strip().str.upper()
    extracted["resolved_outcome"] = extracted["Decision"].map(
        lambda value: "GRANTED" if value in {"CONDITIONAL", "CONDITIONAL PERMISSION", "GRANT PERMISSION", "UNCONDITIONAL", "UNCONDITIONAL PERMISSION", "GRANTED"}
        else "REFUSED" if value in {"REFUSED", "REFUSE PERMISSION"} else "UNKNOWN"
    )

    register_cover = field_coverage(register, {**REGISTER_FIELDS, "density_units_per_ha": "density_units_per_ha", "plot_ratio_proxy": "plot_ratio_proxy"})
    register_cover["one_off_house"] = {
        "rows": int(len(register)),
        "non_null": int(register["OneOffHouse"].fillna("").astype(str).str.strip().ne("").sum()),
        "fraction": round(register["OneOffHouse"].fillna("").astype(str).str.strip().ne("").mean(), 4),
        "column_missing": False,
    }
    extracted_cover = field_coverage(extracted, EXTRACTED_FIELDS)
    recommendation = recommend_ready_fields(register_cover, extracted_cover)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, field in {"units": "units_total_best", "max_storeys": "max_storeys_best", "parking_spaces": "parking_spaces_best"}.items():
        grouped_coverage(extracted, field, "PlanningAuthority").to_csv(OUT_DIR / f"extracted_coverage_by_authority_{name}.csv", index=False)
    grouped_coverage(extracted, "units_total_best", "received_year").to_csv(OUT_DIR / "extracted_coverage_by_year_units.csv", index=False)
    grouped_coverage(extracted, "max_storeys_best", "received_year").to_csv(OUT_DIR / "extracted_coverage_by_year_storeys.csv", index=False)
    grouped_coverage(extracted, "units_total_best", "resolved_outcome").to_csv(OUT_DIR / "extracted_coverage_by_outcome_units.csv", index=False)
    grouped_coverage(extracted, "max_storeys_best", "resolved_outcome").to_csv(OUT_DIR / "extracted_coverage_by_outcome_storeys.csv", index=False)
    for name, field in {"units": "NumResidentialUnits", "site_area_ha": "AreaofSite", "floor_area_sqm": "FloorArea"}.items():
        grouped_coverage(register, field, "PlanningAuthority").to_csv(OUT_DIR / f"register_coverage_by_authority_{name}.csv", index=False)
    grouped_coverage(register, "NumResidentialUnits", "received_year").to_csv(OUT_DIR / "register_coverage_by_year_units.csv", index=False)
    register[["PlanningAuthority", "ApplicationType", "received_year"]].assign(units=pd.to_numeric(register["NumResidentialUnits"], errors="coerce")).pipe(
        lambda frame: grouped_coverage(frame, "units", "ApplicationType")
    ).to_csv(OUT_DIR / "register_coverage_by_type_units.csv", index=False)

    extracted_dist = distribution_table(extracted, EXTRACTED_FIELDS, PLAUSIBLE_BOUNDS)
    register_dist = distribution_table(
        register,
        {"units": "NumResidentialUnits", "site_area_ha": "AreaofSite", "floor_area_sqm": "FloorArea", "density_units_per_ha": "density_units_per_ha", "plot_ratio_proxy": "plot_ratio_proxy"},
        PLAUSIBLE_BOUNDS,
    )
    pd.concat([extracted_dist, register_dist], ignore_index=True).to_csv(OUT_DIR / "distributions.csv", index=False)

    provenance = {
        "units": extracted["units_recovery_method"].fillna("").astype(str).value_counts().to_dict(),
        "note": (
            "Only units records an extraction method (units_recovery_method). Other extracted "
            "fields have no per-value provenance column, so their confidence is 'high-confidence "
            "extracted' at best and unverified until spot-checked."
        ),
    }

    payload = {
        "generated": "2026-09-04",
        "task": "Task 1 structured-variable audit",
        "register_tier": {
            "description": "Official register fields across the national residential scope; no extraction risk.",
            "rows": int(len(register)),
            "coverage": register_cover,
        },
        "extracted_tier": {
            "description": "Description-extracted 'best' fields on the GE10 (10+ units) cohort.",
            "rows": int(len(extracted)),
            "coverage": extracted_cover,
        },
        "verified_tier": {
            "rows": 46,
            "description": "Annotation-verified before/after deltas for 46 audited revision pairs (see canonical_revision_scheme_records.csv).",
        },
        "provenance": provenance,
        "recommendation": recommendation,
        "caveat": (
            "Coverage counts non-null numeric values only. Extracted values are not manually "
            "verified unless stated. Height, setbacks and separation distances are absent from "
            "all current cohorts and require new extraction before they can be modelled."
        ),
    }
    (OUT_DIR / "audit_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
