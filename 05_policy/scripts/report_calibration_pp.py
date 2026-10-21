#!/usr/bin/env python3
"""Calibration error per band, in percentage points."""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
data = json.loads((OUT / "raw_planning_8020_calibration.json").read_text(encoding="utf-8"))
bins = data["E8020"]["calibrated_isotonic"]["reliability_bins"]

print(f"{'band':>12} {'n':>6} {'pred':>6} {'obs':>6} {'error(pp)':>9}")
rows = []
for b in bins:
    error = (b["pred"] - b["obs"]) * 100
    rows.append((b["lo"], b["hi"], b["n"], b["pred"], b["obs"], error))
    print(f"{b['lo']:.1f}-{b['hi']:.1f} {b['n']:>6} {b['pred']*100:>5.1f}% {b['obs']*100:>5.1f}% {error:>+8.1f}")

ece = data["E8020"]["calibrated_isotonic"]["ece_weighted"]
print(f"\nweighted ECE: {ece*100:.2f}pp")

fig, ax = plt.subplots(figsize=(11, 4.5))
lo = [b["lo"] for b in bins]
error = [(b["pred"] - b["obs"]) * 100 for b in bins]
ns = [b["n"] for b in bins]
colours = ["#c0392b" if e > 0.5 else ("#27ae60" if e < -0.5 else "#95a5a6") for e in error]
bars = ax.bar(lo, error, width=0.075, color=colours, alpha=0.85)
for i, (bar, n) in enumerate(zip(bars, ns)):
    if n >= 100:
        ax.annotate(f"n={n}", (bar.get_x() + bar.get_width() / 2, bar.get_height()), textcoords="offset points", xytext=(0, 3 if bar.get_height() >= 0 else -10), ha="center", fontsize=7)
ax.axhline(0, color="grey", linewidth=0.8)
ax.set_xlabel("predicted band (calibrated probability)")
ax.set_ylabel("calibration error (pp): predicted minus observed")
ax.set_title("v4-full calibration error by band, 2024+2025 (red = overstates risk, green = understates)")
fig.tight_layout()
fig.savefig(OUT / "calibration_error_pp.png", dpi=130)
print("saved calibration_error_pp.png")
