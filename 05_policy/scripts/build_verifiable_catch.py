#!/usr/bin/env python3
"""Verifiable catch: nothing to take on trust.

Produces:
  - ge10_scored_2024_25.csv: all 464 schemes, model score, band, actual outcome
  - catch_grid.png: every scheme as a coloured cell (green=granted, red=refused),
    sorted by model risk from safest to riskiest
  - the three-band count table: safest 47 / middle 370 / riskiest 47
The audience can recount the cells and the sums themselves.
"""
from __future__ import annotations

import json
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
    ranking = artifact["ranking_model"]
    ge10 = test[test["units"] >= 10].copy()
    ge10["model_risk"] = ranking.predict_proba(ge10[artifact["feature_columns"]])[:, 1]
    ge10 = ge10.sort_values("model_risk").reset_index(drop=True)
    ge10["risk_rank"] = ge10.index + 1

    keep = {
        "risk_rank": ge10["risk_rank"],
        "case_key": ge10["case_key"],
        "council": ge10["PlanningAuthority"],
        "units": ge10["units"],
        "description": ge10["description_stripped"],
        "model_risk": ge10["model_risk"].round(4),
        "outcome": ge10["target_refused"].map({1: "REFUSED", 0: "granted"}),
    }
    table = pd.DataFrame(keep)
    table.to_csv(OUT / "ge10_scored_2024_25.csv", index=False)

    n = len(ge10)
    safest = ge10.iloc[:47]
    middle = ge10.iloc[47:417]
    riskiest = ge10.iloc[417:]
    counts = {
        "safest_47": {"refused": int(safest["target_refused"].sum()), "granted": int(len(safest) - safest["target_refused"].sum())},
        "middle_370": {"refused": int(middle["target_refused"].sum()), "granted": int(len(middle) - middle["target_refused"].sum())},
        "riskiest_47": {"refused": int(riskiest["target_refused"].sum()), "granted": int(len(riskiest) - riskiest["target_refused"].sum())},
        "total": {"refused": int(ge10["target_refused"].sum()), "granted": int(n - ge10["target_refused"].sum()), "schemes": n},
    }

    cols = 29
    rows = int(np.ceil(n / cols))
    fig, ax = plt.subplots(figsize=(16, rows * 0.42 + 1.2))
    outcomes = ge10["target_refused"].to_numpy()
    for i in range(n):
        r, c = divmod(i, cols)
        colour = "#c0392b" if outcomes[i] == 1 else "#27ae60"
        ax.add_patch(plt.Rectangle((c, rows - 1 - r), 0.92, 0.82, facecolor=colour, edgecolor="white", linewidth=0.6))
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.annotate("safest\nby model", xy=(0, -0.35), fontsize=10, ha="left")
    ax.annotate("riskiest\nby model", xy=(cols, -0.35), fontsize=10, ha="right")
    ax.set_title(f"Every 10+ unit scheme decided 2024-2025 (n={n}) - sorted by the model's score before decision\nred = refused, green = granted", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "catch_grid.png", dpi=130)
    print("saved catch_grid.png + ge10_scored_2024_25.csv")

    payload = {"counts": counts, "check": f"safest 47 + middle 370 + riskiest 47 = {len(safest) + len(middle) + len(riskiest)} schemes; refusals {counts['safest_47']['refused']} + {counts['middle_370']['refused']} + {counts['riskiest_47']['refused']} = {counts['total']['refused']}"}
    (OUT / "verifiable_catch.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
