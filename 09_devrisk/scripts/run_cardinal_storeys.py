"""Final cardinal pass: storeys effect with CI, era stability, theme split.
Also assembles the complete cardinal landscape: rescue bundles, description
trimming, storeys, units - which have support and which are zero.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "optimiser"


def main() -> None:
    pairs = pd.read_csv(OUT / "mutation_pairs_design.csv")
    pairs["y"] = (pairs["outcome_b"] == "grant").astype(int)
    train = pairs[pairs["year_a"] < 2022]
    report = {}
    # storeys effect, all pairs with any storeys info
    sub = train.dropna(subset=["d_storeys"]).copy()
    sub["d_storeys"] = sub["d_storeys"].astype(float)
    sub = sub[sub["d_storeys"].between(-4, 4)]
    feats = ["d_storeys", "d_units"]
    m = LogisticRegression(max_iter=3000, C=1.0)
    m.fit(sub[feats].fillna(0), sub["y"])
    coef = float(m.coef_[0][0])
    rng = np.random.default_rng(7)
    bs = []
    for _ in range(400):
        idx = rng.choice(len(sub), len(sub), replace=True)
        try:
            mm = LogisticRegression(max_iter=3000, C=1.0)
            mm.fit(sub.iloc[idx][feats].fillna(0), sub.iloc[idx]["y"])
            bs.append(float(mm.coef_[0][0]))
        except ValueError:
            continue
    report["storeys"] = {
        "n": int(len(sub)), "coef_per_storey_down": round(coef, 4),
        "odds_ratio_per_storey_down": round(float(np.exp(-coef)), 3),
        "ci95": [round(float(np.quantile(bs, 0.025)), 4), round(float(np.quantile(bs, 0.975)), 4)],
        "era_stability": {
            "2014-2018": round(float(LogisticRegression(max_iter=3000, C=1.0).fit(
                sub[sub["year_a"] <= 2018][feats].fillna(0), sub[sub["year_a"] <= 2018]["y"]).coef_[0][0]), 4)
            if len(sub[sub["year_a"] <= 2018]) >= 60 else None,
            "2019-2021": round(float(LogisticRegression(max_iter=3000, C=1.0).fit(
                sub[sub["year_a"] > 2018][feats].fillna(0), sub[sub["year_a"] > 2018]["y"]).coef_[0][0]), 4),
        },
    }
    report["cardinal_landscape"] = {
        "rescue_bundle_table": {"support": "SUPPORTED",
                                "evidence": "0/1.7/5.6/18.7/24.9% (Wilson CIs, fresh-era confirmed 0/1.2/4.5/17.4/21.0%)"},
        "description_trimming": {"support": "SUPPORTED (correlational)",
                                 "evidence": "converts 91.5% [90.0,92.8] vs 66.9% [66.0,67.9]; fresh-era desc-ratio 1.03 vs 1.53"},
        "storeys": {"support": "PENDING THIS PASS"},
        "units": {"support": "FALSIFIED",
                  "evidence": "effect 0 with CI straddling 0 across themes and eras; OR 1.001"},
    }
    (OUT / "cardinal_landscape.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
