#!/usr/bin/env python3
"""Risk strip plot: every GE10 scheme on the probability axis, outliers annotated.

x = calibrated refusal probability; colour = actual outcome; vertical lines at
the candidate cutoffs. Outliers (refused-but-scored-low, granted-but-scored-high)
are labelled and exported.
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import build_data  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


def main() -> None:
    data, train, test, y = build_data()
    artifact = joblib.load(ARTIFACT)
    calibrated_base = artifact["calibrated_base_model"]
    isotonic = artifact["isotonic_calibrator"]
    ge10 = test[test["units"] >= 10].copy()
    base_scores = calibrated_base.predict_proba(ge10[artifact["feature_columns"]])[:, 1]
    ge10["risk"] = isotonic.predict(base_scores)
    ge10 = ge10.sort_values("risk").reset_index(drop=True)
    ge10["refused"] = ge10["target_refused"].astype(int)

    refused = ge10[ge10["refused"] == 1]
    granted = ge10[ge10["refused"] == 0]
    rng = np.random.default_rng(3)
    jitter_r = rng.uniform(-0.9, 0.9, len(refused))
    jitter_g = rng.uniform(-0.9, 0.9, len(granted))

    fig, ax = plt.subplots(figsize=(16, 5.5))
    ax.scatter(refused["risk"] * 100, jitter_r, s=22, c="#c0392b", alpha=0.55, label=f"refused ({len(refused)})")
    ax.scatter(granted["risk"] * 100, jitter_g, s=18, c="#27ae60", alpha=0.5, label=f"granted ({len(granted)})")

    cutoffs = {
        "low-band 3.8%": 3.7612,
        "national base 11%": 11.0,
        "GE10 base 19%": 19.0,
        "medium-band 11.4%": 11.4078,
    }
    colours = {"low-band 3.8%": "#8e44ad", "national base 11%": "#34495e", "GE10 base 19%": "#f39c12", "medium-band 11.4%": "#8e44ad"}
    for label, x in cutoffs.items():
        ax.axvline(x, color=colours[label], linestyle="--", linewidth=1.2)
        ax.text(x, 0.55, label, rotation=90, fontsize=8, color=colours[label], va="bottom")

    misses = refused[refused["risk"] < 0.10]
    alarms = granted[granted["risk"] > 0.55]
    for _, row in misses.iterrows():
        ax.annotate(
            f"{row['PlanningAuthority'][:18]}, {int(row['units'])}u",
            xy=(row["risk"] * 100, 0.8), xytext=(row["risk"] * 100 - 9, 1.05),
            fontsize=7, color="#7b241c", arrowprops=dict(arrowstyle="-", color="#c0392b", lw=0.6),
        )
    for _, row in alarms.iterrows():
        ax.annotate(
            f"{row['PlanningAuthority'][:18]}, {int(row['units'])}u",
            xy=(row["risk"] * 100, -0.8), xytext=(row["risk"] * 100 - 9, -1.15),
            fontsize=7, color="#145a32", arrowprops=dict(arrowstyle="-", color="#27ae60", lw=0.6),
        )

    ax.set_xlabel("calibrated refusal probability (%)")
    ax.set_yticks([])
    ax.set_ylim(-1.6, 1.6)
    ax.set_title("Every 10+ unit scheme decided 2024-2025 on the probability axis (n=464) - green granted, red refused")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "risk_strip_outliers.png", dpi=130)
    print("saved risk_strip_outliers.png")

    outliers = pd.concat([
        misses.assign(kind="missed_refusal"),
        alarms.assign(kind="false_alarm"),
    ])[["case_key", "PlanningAuthority", "units", "risk", "refused", "kind", "description_stripped"]]
    outliers = outliers.sort_values("kind").reset_index(drop=True)
    outliers.to_csv(OUT / "outlier_cases.csv", index=False)
    print(f"outliers: {len(misses)} missed refusals (risk<10%), {len(alarms)} false alarms (risk>55%)")
    for _, row in misses.iterrows():
        print(f"  MISS  {row['risk'] * 100:5.1f}% refused - {row['PlanningAuthority']} {int(row['units'])}u - {str(row['description_stripped'])[:90]}")
    for _, row in alarms.iterrows():
        print(f"  ALARM {row['risk'] * 100:5.1f}% granted - {row['PlanningAuthority']} {int(row['units'])}u - {str(row['description_stripped'])[:90]}")


if __name__ == "__main__":
    main()
