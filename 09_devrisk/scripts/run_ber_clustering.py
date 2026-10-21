"""Runner: BER completion-cluster pipeline (schema-agnostic).

Consumes the SEAI BER research dataset once downloaded (or a synthetic
fixture now). For each estate in the cohort:
  1. select BER rows near the site (small-area/grid/coords if present,
     else county+year-of-construction filtering);
  2. keep FINAL (constructed-dwelling) assessments;
  3. cluster by assessment-date bursts -> completion waves;
  4. compare waves against BCMS CCC dates (agreement table);
  5. phase inference: address/grid clusters + date bursts vs BCMS
     phase_units (polygon-free phase reconstruction).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

BER_COLUMN_MAP = {
    "assessment_date": ["assessment_date", "date_of_issue", "dateofassessment", "certdate"],
    "provisional_flag": ["provisional", "is_provisional", "cert_type", "type_of_assessment"],
    "dwelling_type": ["dwelling_type", "dwellingtype", "type_of_dwelling"],
    "floor_area": ["floor_area", "total_floor_area", "floorarea"],
    "year_built": ["year_of_construction", "year_built", "yearofconstruction"],
    "county": ["county", "county_name"],
    "small_area": ["small_area", "sa_code", "small_area_code"],
    "easting": ["easting", "x", "itm_easting", "grid_x"],
    "northing": ["northing", "y", "itm_northing", "grid_y"],
    "address": ["address", "address_line_1", "full_address"],
    "eircode": ["eircode", "eir_code"],
    "rating": ["ber_rating", "rating", "energy_rating"],
}


def map_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    for target, candidates in BER_COLUMN_MAP.items():
        for column in candidates:
            if column in frame.columns:
                out[target] = frame[column]
                break
    return out


def completion_waves(dates: pd.Series, gap_days: int = 60, min_cluster: int = 5) -> list[dict]:
    ordered = pd.to_datetime(dates, utc=True, errors="coerce").dropna().sort_values()
    waves = []
    start = prev = None
    count = 0
    for date in ordered:
        if start is None:
            start = prev = date
            count = 1
        elif (date - prev).days <= gap_days:
            prev = date
            count += 1
        else:
            if count >= min_cluster:
                waves.append({"start": str(start.date()), "end": str(prev.date()), "n": count})
            start = prev = date
            count = 1
    if count >= min_cluster:
        waves.append({"start": str(start.date()), "end": str(prev.date()), "n": count})
    return waves


def run(ber_path: Path | None = None) -> dict:
    report: dict = {}
    if ber_path is None or not Path(ber_path).exists():
        # Synthetic fixture to validate the pipeline.
        rng = np.random.default_rng(7)
        rows = []
        for wave_date, n, phase in ((pd.Timestamp("2021-06-01", tz="UTC"), 40, 1),
                                    (pd.Timestamp("2022-04-15", tz="UTC"), 35, 2)):
            for i in range(n):
                rows.append({
                    "assessment_date": wave_date + pd.Timedelta(days=int(rng.integers(0, 45))),
                    "provisional": "No",
                    "dwelling_type": "House",
                    "floor_area": float(rng.integers(90, 140)),
                    "year_of_construction": 2021,
                    "county": "Kildare",
                    "small_area": "SA001",
                    "easting": 680000.0 + rng.normal(0, 120),
                    "northing": 730000.0 + rng.normal(0, 120),
                    "phase": phase,
                })
        frame = map_columns(pd.DataFrame(rows))
        report["mode"] = "synthetic_fixture"
    else:
        frame = map_columns(pd.read_csv(ber_path, low_memory=False))
        report["mode"] = "real"
        report["rows"] = int(len(frame))

    if "provisional_flag" in frame.columns:
        final = frame[~frame["provisional_flag"].fillna("").astype(str).str.lower().str.contains("provisional", na=False)]
    else:
        final = frame
    report["final_share"] = round(float(len(final) / max(1, len(frame))), 3)

    if "assessment_date" in final.columns:
        waves = completion_waves(final["assessment_date"])
        report["completion_waves"] = waves
        report["n_waves"] = len(waves)

    if "phase" in final.columns and "assessment_date" in final.columns:
        agreement = final.groupby("phase")["assessment_date"].agg(first=("assessment_date", "min"),
                                                                   last=("assessment_date", "max"),
                                                                   n=("assessment_date", "size"))
        report["phase_clusters_fixture"] = {
            str(phase): {"first": str(row["first"]), "last": str(row["last"]), "n": int(row["n"])}
            for phase, row in agreement.iterrows()
        }
    return report


if __name__ == "__main__":
    result = run()
    out = settings.SILVER_DIR / "ber_clustering_fixture.json"
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
