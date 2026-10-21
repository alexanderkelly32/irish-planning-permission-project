#!/usr/bin/env python3
"""Precompute the rate tables used by the explainers into a static JSON."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current" / "rate_tables.json"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_prospective_calibration_backtest import prepare  # noqa: E402

df = prepare()
df = df[df["target_refused"].notna()]
units = pd.to_numeric(df["NumResidentialUnits"], errors="coerce")

bucket_rates = df.groupby("application_bucket")["target_refused"].agg(["mean", "size"])
council_bucket = df.groupby(["PlanningAuthority", "application_bucket"])["target_refused"].agg(["mean", "size"])

units_buckets = [(0, 1, "single home"), (2, 9, "2-9 homes"), (10, 19, "10-19 homes"), (20, 39, "20-39 homes"), (40, 79, "40-79 homes"), (80, 9999, "80+ homes")]
units_bucket_rates = {}
for lo, hi, label in units_buckets:
    sel = df[(units >= lo) & (units <= hi)]
    if len(sel) >= 30:
        units_bucket_rates[label] = {"rate": round(float(sel["target_refused"].mean()), 4), "n": int(len(sel))}

site_ha = pd.to_numeric(df["AreaofSite"], errors="coerce")
density = np.divide(units, site_ha, out=np.full(len(df), np.nan), where=site_ha > 0)
density_bands = {
    "low (below 35 homes/ha)": density < 35,
    "medium (35-50 homes/ha)": (density >= 35) & (density <= 50),
    "high (above 50 homes/ha)": density > 50,
}
density_band_rates = {}
for label, mask in density_bands.items():
    sel = df[mask]
    if len(sel) >= 30:
        density_band_rates[label] = {"rate": round(float(sel["target_refused"].mean()), 4), "n": int(len(sel))}

payload = {
    "bucket_rates": {str(k): {"rate": round(float(v["mean"]), 4), "n": int(v["size"])} for k, v in bucket_rates.iterrows()},
    "council_bucket_rates": {f"{a}__{b}": {"rate": round(float(v["mean"]), 4), "n": int(v["size"])} for (a, b), v in council_bucket.iterrows()},
    "units_bucket_rates": units_bucket_rates,
    "density_band_rates": density_band_rates,
}
OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
print("wrote", OUT, "| buckets:", len(payload["bucket_rates"]), "| council-buckets:", len(payload["council_bucket_rates"]))
