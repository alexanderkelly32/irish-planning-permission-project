"""Generate national flood input CSV: case_key + geometry (hex WKB Point ITM)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely import wkb

ROOT = Path(r"")
OUT = ROOT / "07_context" / "raw" / "all_cases_flood_input.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_prospective_calibration_backtest import prepare  # noqa: E402

data = prepare()
subset = data[["case_key", "ITMEasting", "ITMNorthing"]].copy()
mask = subset[["ITMEasting", "ITMNorthing"]].notna().all(axis=1)
subset = subset[mask]
subset["geometry"] = [
    Point(float(e), float(n)).wkb.hex()
    for e, n in zip(subset["ITMEasting"], subset["ITMNorthing"])
]
subset.to_csv(OUT, index=False)
print("wrote", len(subset), "rows ->", OUT)
