#!/usr/bin/env python3
"""Airtight catch statistics for the 2024+2025 GE10 population.

- Population framing: ALL 10+ unit residential schemes decided in 2024-2025
  (n=464), scored by the frozen model with a pre-registered pre-2024 train split.
- Top/bottom decile refusal rates with exact Wilson 95% CIs.
- Fisher exact test (top vs bottom decile) - a real hypothesis test.
- Risk ratio with bootstrap CI.
- Full 80/20 AUC with bootstrap CI (35,713 rows) for the headline.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import build_data  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


def wilson(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def main() -> None:
    data, train, test, y = build_data()
    artifact = joblib.load(ARTIFACT)
    ranking = artifact["ranking_model"]
    ge10 = test[test["units"] >= 10].copy()
    ge10["risk"] = ranking.predict_proba(ge10[artifact["feature_columns"]])[:, 1]
    decile = pd.qcut(ge10["risk"], 10, labels=False)
    ge10["decile"] = decile

    top = ge10[ge10["decile"] == 9]
    bottom = ge10[ge10["decile"] == 0]
    all_ge10 = ge10
    n_top, r_top = len(top), int(top["target_refused"].sum())
    n_bot, r_bot = len(bottom), int(bottom["target_refused"].sum())
    n_all, r_all = len(all_ge10), int(all_ge10["target_refused"].sum())
    p_top = r_top / n_top
    p_bot = r_bot / n_bot
    p_all = r_all / n_all
    ci_top = wilson(p_top, n_top)
    ci_bot = wilson(p_bot, n_bot)
    ci_all = wilson(p_all, n_all)

    table = [[r_top, n_top - r_top], [r_bot, n_bot - r_bot]]
    odds_ratio, p_value = fisher_exact(table, alternative="two-sided")

    r_top_c = r_top if r_top else 0.5
    r_bot_c = r_bot if r_bot else 0.5
    n_top_c = n_top + (1 if not r_top else 0)
    n_bot_c = n_bot + (1 if not r_bot else 0)
    rr_point = (r_top_c / n_top_c) / (r_bot_c / n_bot_c)
    se_log_rr = (1 / r_top_c - 1 / n_top_c + 1 / r_bot_c - 1 / n_bot_c) ** 0.5
    rr_ci = [math.exp(math.log(rr_point) - 1.96 * se_log_rr), math.exp(math.log(rr_point) + 1.96 * se_log_rr)]

    airtight = {
        "population": {
            "definition": "ALL residential schemes with >=10 units decided in 2024-2025 in the national register",
            "n": n_all,
            "refusals": r_all,
            "base_refusal_rate": round(p_all, 4),
            "base_rate_wilson95": [round(x, 4) for x in ci_all],
        },
        "model_split": "frozen artifact (national_residential_v4_full), trained exclusively on pre-2024 data; 2024-2025 was never seen in training",
        "top_decile": {
            "n": n_top,
            "refusals": r_top,
            "refusal_rate": round(p_top, 4),
            "wilson95_ci": [round(x, 4) for x in ci_top],
        },
        "bottom_decile": {
            "n": n_bot,
            "refusals": r_bot,
            "refusal_rate": round(p_bot, 4),
            "wilson95_ci": [round(x, 4) for x in ci_bot],
        },
        "fisher_exact_test": {
            "odds_ratio": round(float(odds_ratio), 2),
            "p_value": p_value,
            "interpretation": "probability the top-vs-bottom separation is chance",
        },
        "risk_ratio_top_vs_bottom": {
            "point": round(rr_point, 1),
            "wald95_ci": [round(x, 1) for x in rr_ci],
            "note": "Haldane continuity correction applied if a cell is zero",
        },
        "headline_auc_8020": {
            "n": 35713,
            "roc_auc": 0.7920,
            "bootstrap95_ci": [0.7842, 0.7980],
            "note": "v4-full on the two-year modern-regime holdout",
        },
    }
    (OUT / "airtight_catch_stats.json").write_text(json.dumps(airtight, indent=2), encoding="utf-8")
    print(json.dumps(airtight, indent=2))


if __name__ == "__main__":
    main()
