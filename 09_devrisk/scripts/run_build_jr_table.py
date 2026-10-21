"""Runner: JR positive-events table from the 4Dublin pipeline layer.

Extracts judicial-review evidence (reference, conclusion, date, subject
scheme), matches to the mature cohort via ITM proximity (<= 100m), and
writes jr_events.csv. Positive evidence only - absence is never a negative.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    pipeline = pd.read_csv(settings.SILVER_DIR / "4dublin" / "pipeline_all.csv", low_memory=False)
    jr = pipeline[pipeline["Subject_to_Live_JR"].notna()].copy()
    jr["jr_text"] = jr["Subject_to_Live_JR"].astype(str)
    jr["jr_has_conclusion"] = jr["JR_Conclusion"].notna().astype(int)
    jr["easting"] = pd.to_numeric(jr["X_Coordinate_ITM"], errors="coerce")
    jr["northing"] = pd.to_numeric(jr["Y_Coordinate_ITM"], errors="coerce")
    jr = jr.dropna(subset=["easting", "northing"])

    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    mature["easting"] = pd.to_numeric(mature["ITMEasting"], errors="coerce")
    mature["northing"] = pd.to_numeric(mature["ITMNorthing"], errors="coerce")
    mature = mature.dropna(subset=["easting", "northing"])

    matches = []
    mature_positions = mature.reset_index(drop=True)
    for _, row in jr.iterrows():
        distance = np.hypot(mature_positions["easting"] - row["easting"], mature_positions["northing"] - row["northing"])
        nearest_idx = int(distance.idxmin())
        if distance[nearest_idx] <= 100:
            scheme = mature_positions.iloc[nearest_idx]
            matches.append({
                "case_key": str(scheme["case_key"]),
                "authority": row.get("Planning_Authority"),
                "planning_reference": row.get("Planning_Reference"),
                "jr_reference": row.get("JR_Reference"),
                "jr_conclusion": row.get("JR_Conclusion"),
                "jr_conclusion_date": row.get("JR_Conclusion_Date"),
                "jr_text": str(row["jr_text"])[:300],
                "distance_metres": round(float(distance[nearest_idx]), 1),
                "units_permitted": row.get("Planning_Permission_Units_Permi"),
            })

    events = pd.DataFrame(matches).drop_duplicates(subset=["case_key", "jr_reference"])
    events.to_csv(settings.SILVER_DIR / "jr_events.csv", index=False)

    summary = {
        "pipeline_records": int(len(pipeline)),
        "jr_rows_in_pipeline": int(len(jr)),
        "jr_matched_to_cohort": int(len(events)),
        "schemes_with_jr": int(events["case_key"].nunique()) if len(events) else 0,
        "jr_with_conclusion": int(events["jr_conclusion"].notna().sum()) if len(events) else 0,
        "note": "Dublin region only (4Dublin pipeline); positive evidence only",
    }
    (settings.SILVER_DIR / "jr_events_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
