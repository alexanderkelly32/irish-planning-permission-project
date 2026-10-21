#!/usr/bin/env python3
"""
Recompute missing unit counts from DevelopmentDescription and update _best fields.

Default inputs:
- input:  extraction_of_site_data/ground_source_extracted_final_wide.csv
- output: extraction_of_site_data/ground_source_extracted_final_wide_fixed.csv
- ge10:   extraction_of_site_data/ground_source_extracted_final_wide_ge10_fixed.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from extract_development_details import extract_details  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="extraction_of_site_data/ground_source_extracted_final_wide.csv",
    )
    parser.add_argument(
        "--output",
        default="extraction_of_site_data/ground_source_extracted_final_wide_fixed.csv",
    )
    parser.add_argument(
        "--output-ge10",
        default="extraction_of_site_data/ground_source_extracted_final_wide_ge10_fixed.csv",
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    out_ge10 = Path(args.output_ge10)

    df = pd.read_csv(in_path, low_memory=False)

    # Recompute only where units_total_best is missing and description exists.
    mask = df["units_total_best"].isna() & df["DevelopmentDescription"].notna()
    subset = df.loc[mask, ["DevelopmentDescription"]].copy()

    if len(subset) > 0:
        details = subset["DevelopmentDescription"].map(extract_details)
        details_df = pd.DataFrame(list(details), index=subset.index).add_suffix("_fix")

        # Map fix columns to best columns when best is missing.
        field_map = {
            "units_total_text": "units_total_best",
            "units_houses": "units_houses_best",
            "units_dwellings": "units_dwellings_best",
            "units_apartments": "units_apartments_best",
            "units_duplex": "units_duplex_best",
            "units_townhouses": "units_townhouses_best",
            "units_bungalows": "units_bungalows_best",
            "bed_1": "bed_1_best",
            "bed_2": "bed_2_best",
            "bed_3": "bed_3_best",
            "bed_4": "bed_4_best",
            "bed_5": "bed_5_best",
            "parking_spaces": "parking_spaces_best",
            "cycle_parking_spaces": "cycle_parking_spaces_best",
            "site_area_ha": "site_area_ha_best",
            "site_area_sqm": "site_area_sqm_best",
            "floor_area_sqm": "floor_area_sqm_best",
            "open_space_sqm": "open_space_sqm_best",
            "max_storeys": "max_storeys_best",
            "retail_area_sqm": "retail_area_sqm_best",
            "commercial_area_sqm": "commercial_area_sqm_best",
            "creche_area_sqm": "creche_area_sqm_best",
            "serviced_sites": "serviced_sites_best",
            "phase": "phase_best",
            "has_retail": "has_retail_best",
            "has_commercial": "has_commercial_best",
            "has_mixed_use": "has_mixed_use_best",
            "has_creche": "has_creche_best",
            "has_community": "has_community_best",
            "has_hotel": "has_hotel_best",
            "has_industrial": "has_industrial_best",
        }

        for col, best_col in field_map.items():
            fix_col = f"{col}_fix"
            if best_col in df.columns and fix_col in details_df.columns:
                target_idx = details_df.index[df.loc[details_df.index, best_col].isna()]
                df.loc[target_idx, best_col] = details_df.loc[target_idx, fix_col]

    # Also provide a fixed units_total_best using NumResidentialUnits if still missing.
    if "units_total_best" in df.columns:
        df["units_total_best"] = df["units_total_best"].fillna(df["NumResidentialUnits"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    if "units_total_best" in df.columns:
        ge10 = df[df["units_total_best"].fillna(0) >= 10]
        ge10.to_csv(out_ge10, index=False)

    print(f"Wrote: {out_path}")
    print(f"Wrote: {out_ge10}")
    # quick DLR check
    if "PlanningAuthority" in df.columns:
        dlr = df["PlanningAuthority"].astype(str).str.lower().str.contains("dun laoghaire")
        print("DLR rows:", int(dlr.sum()))
        if "units_total_best" in df.columns:
            print("DLR with units_total_best >=10:", int((df.loc[dlr, "units_total_best"].fillna(0) >= 10).sum()))


if __name__ == "__main__":
    main()
