"""Runner: BER clustering POC on Fingal's open BER certificates layer.

The national unit-level BER bulk needs SEAI research-tool access; Fingal
publishes building-level BER certs openly. This validates the completion-wave
algorithm: cluster final BER dates by small area / proximity and compare
waves against Fingal cohort commencement/completion dates. Algorithm is then
national-ready when the SEAI bulk lands.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

# Fingal BER ArcGIS Hub CSV endpoints (2020-2024 and 2025-2027 packages).
CSV_URLS = [
    "https://data.fingal.ie/datasets/FingalCoCo::ber-ratings-building-certs-2020-2024-fcc.csv",
    "https://data.fingal.ie/datasets/FingalCoCo::ber-ratings-building-certs-2025-2027-fcc.csv",
]
OUT_DIR = settings.RAW_DIR / "ber_fingal"

if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for url in CSV_URLS:
        name = url.split("::")[-1].replace(".csv", "") + ".csv"
        target = OUT_DIR / name
        if not target.exists():
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 planning-risk-review/1.0"})
            with urllib.request.urlopen(request, timeout=300) as response:
                target.write_bytes(response.read())
        part = pd.read_csv(target, low_memory=False)
        frames.append(part)
        print(f"{name}: {len(part)} rows, columns: {part.columns.tolist()[:12]}", flush=True)
    frame = pd.concat(frames, ignore_index=True)
    print(json.dumps({"total_rows": int(len(frame)), "columns": frame.columns.tolist()}), flush=True)
    frame.to_parquet(OUT_DIR / "ber_fingal_raw.parquet", index=False)
