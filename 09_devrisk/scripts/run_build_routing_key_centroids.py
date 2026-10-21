"""Runner: routing-key centroids from BCMS (free geocoder for PPR rows).

BCMS silver rows carry both eircodes and ITM coordinates. A routing key
(first 3 chars of the eircode) identifies a small area. Median coordinates
per routing key give approximate positions for the 250k PPR rows that have
eircodes. Accuracy is routing-key-scale (hundreds of metres), used for
candidate generation, never as sole confirmation.
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
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    frame = bcms[bcms["eircode"].fillna("").astype(str).str.strip().ne("")].copy()
    frame["routing_key"] = frame["eircode"].astype(str).str.strip().str.upper().str.replace(" ", "").str.slice(0, 3)
    frame["itm_easting"] = pd.to_numeric(frame["itm_easting"], errors="coerce")
    frame["itm_northing"] = pd.to_numeric(frame["itm_northing"], errors="coerce")
    frame = frame.dropna(subset=["itm_easting", "itm_northing"])

    centroids = frame.groupby("routing_key").agg(
        n_bcms_rows=("routing_key", "size"),
        itm_easting=("itm_easting", "median"),
        itm_northing=("itm_northing", "median"),
        itm_easting_std=("itm_easting", "std"),
        itm_northing_std=("itm_northing", "std"),
    ).reset_index()

    out = settings.SILVER_DIR / "routing_key_centroids.parquet"
    centroids.to_parquet(out, index=False)

    summary = {
        "bcms_rows_with_eircode_and_geo": int(len(frame)),
        "routing_keys_covered": int(len(centroids)),
        "median_std_metres": round(float(np.median(centroids[["itm_easting_std", "itm_northing_std"]].max(axis=1))), 0),
        "out_path": str(out),
    }
    (settings.SILVER_DIR / "routing_key_centroids_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
