"""Delta estimator v2 on the 200-400+ cohort: weighted neighbour estimates,
effective support, stability re-check, tightened paired-ranking CI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "optimiser"


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(centre - margin, 0.0), min(centre + margin, 1.0)


def main() -> None:
    pairs = pd.read_csv(OUT / "mutation_pairs_design.csv")
    pairs["y"] = (pairs["outcome_b"] == "grant").astype(int)
    train = pairs[pairs["year_a"] < 2022]
    delta_cols = ["d_units", "d_storeys", "d_apartment", "d_house", "d_creche",
                  "d_open_space", "d_demolition", "d_part_v", "d_phasing", "d_access_mention"]
    report = {"n_pairs": int(len(pairs)), "n_train": int(len(train))}

    def delta_estimate(delta: dict, k: int = 40) -> dict:
        sub = train
        dist = np.zeros(len(sub))
        for c in delta_cols:
            dist += ((sub[c].fillna(0) - delta.get(c, 0)) ** 2)
        idx = np.argsort(dist)[:k]
        sel = sub.iloc[idx]
        w = np.exp(-np.sqrt(dist.iloc[idx]) / 3.0)
        eff_n = float((w.sum() ** 2) / (w ** 2).sum())
        k_w = int(np.round((sel["y"] * w).sum()))
        n_w = float(w.sum())
        lo, hi = wilson(max(k_w, 0), max(int(round(n_w)), 1))
        return {"grant_rate": round(float(k_w / n_w), 3), "ci": [round(lo, 3), round(hi, 3)],
                "n_raw": int(k), "effective_n": round(eff_n, 1),
                "ood": eff_n < 25}

    ests = {}
    for name, delta in [("reduce_units_20pct", {"d_units": -22.6}),
                        ("reduce_storeys_1", {"d_storeys": -1}),
                        ("add_open_space", {"d_open_space": 1}),
                        ("add_creche", {"d_creche": 1}),
                        ("add_part_v", {"d_part_v": 1}),
                        ("add_phasing", {"d_phasing": 1}),
                        ("increase_units_20pct", {"d_units": 22.6})]:
        ests[name] = delta_estimate(delta)
    report["delta_estimates"] = ests

    stability = {}
    for name, delta in [("reduce_units_20pct", {"d_units": -22.6})]:
        base = delta_estimate(delta)
        perturbed = [delta_estimate({**delta, "d_units": delta["d_units"] + 3})["grant_rate"],
                     delta_estimate({**delta, "d_units": delta["d_units"] - 3})["grant_rate"]]
        spread = max(perturbed) - min(perturbed)
        stability[name] = {"base_rate": base["grant_rate"], "perturbed": perturbed,
                           "spread_pp": round(spread * 100, 1),
                           "stable": spread < 0.10}
    report["stability"] = stability

    test_p = pairs[pairs["year_a"] >= 2022]
    frame = pd.read_csv(OUT / "design_versions.csv").set_index("case_key")
    ranks = []
    for _, p in test_p.iterrows():
        if p["case_key_a"] not in frame.index or p["case_key_b"] not in frame.index:
            continue
        ra = frame.loc[p["case_key_a"]]
        rb = frame.loc[p["case_key_b"]]
        if p["outcome_b"] == "grant" and rb["granted"] == 1 and ra["granted"] == 0:
            ranks.append(int(ra["refused"] == 1 and rb["refused"] == 0))
    if ranks:
        acc = float(np.mean(ranks))
        lo, hi = wilson(int(sum(ranks)), len(ranks))
        report["paired_ranking"] = {"n_pairs": len(ranks), "accuracy": round(acc, 3),
                                    "ci": [round(lo, 3), round(hi, 3)]}
    (OUT / "delta_estimator_v2.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
