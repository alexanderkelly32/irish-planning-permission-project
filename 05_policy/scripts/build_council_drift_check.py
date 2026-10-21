#!/usr/bin/env python3
"""Council drift check: where does the model under/over-price risk by council?

Compares each council's actual 2024-2025 GE10 refusal rate with the model's
mean calibrated risk on those schemes, plus historical (pre-2024) GE10 rates
for context. Determines whether the Fingal cluster is drift or noise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

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
    calibrated_base = artifact["calibrated_base_model"]
    isotonic = artifact["isotonic_calibrator"]
    ge10 = test[test["units"] >= 10].copy()
    ge10["risk"] = isotonic.predict(calibrated_base.predict_proba(ge10[artifact["feature_columns"]])[:, 1])
    ge10_train = train[train["units"] >= 10].copy()

    historical = ge10_train.groupby("PlanningAuthority")["target_refused"].agg(["mean", "size"])
    recent = ge10.groupby("PlanningAuthority").agg(
        refusals=("target_refused", "sum"), n=("target_refused", "size"), mean_risk=("risk", "mean")
    )

    gaps = []
    for council, row in recent.iterrows():
        n = int(row["n"])
        if n < 3:
            continue
        rate = float(row["refusals"] / n)
        ci = wilson(rate, n)
        hist = historical.loc[council] if council in historical.index else None
        gaps.append({
            "council": str(council),
            "n": n,
            "refusal_rate": round(rate, 4),
            "rate_ci": [round(x, 4) for x in ci],
            "model_mean_risk": round(float(row["mean_risk"]), 4),
            "gap_pp": round((rate - float(row["mean_risk"])) * 100, 1),
            "historical_ge10_rate": round(float(hist["mean"]), 4) if hist is not None else None,
            "historical_ge10_n": int(hist["size"]) if hist is not None else None,
        })
    gaps.sort(key=lambda r: -r["gap_pp"])

    fingal_recent = next((g for g in gaps if g["council"] == "Fingal County Council"), None)
    fingal_report = {}
    if fingal_recent:
        hist_rate = fingal_recent["historical_ge10_rate"]
        hist_n = fingal_recent["historical_ge10_n"]
        hist_ci = wilson(hist_rate, hist_n) if hist_rate is not None else None
        recent_ci = fingal_recent["rate_ci"]
        overlap = (hist_ci is not None) and (recent_ci[0] <= hist_ci[1] and hist_ci[0] <= recent_ci[1])
        fingal_report = {
            "historical_ge10": {"rate": hist_rate, "n": hist_n, "ci": [round(x, 4) for x in hist_ci] if hist_ci else None},
            "recent_ge10": {"rate": fingal_recent["refusal_rate"], "n": fingal_recent["n"], "ci": recent_ci},
            "model_mean_risk": fingal_recent["model_mean_risk"],
            "cis_overlap": bool(overlap),
            "verdict": "noise - confidence intervals overlap" if overlap else "drift - recent rate exceeds historical confidence interval",
        }
        shift_applied = None
        if fingal_report["recent_ge10"]["n"] >= 10:
            logit = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
            target = fingal_report["recent_ge10"]["rate"]
            current = fingal_report["model_mean_risk"]
            raw_shift = logit(target) - logit(current)
            shrinkage = min(1.0, fingal_report["recent_ge10"]["n"] / 150.0)
            shift_applied = raw_shift * shrinkage
        fingal_report["suggested_logit_shift"] = round(shift_applied, 4) if shift_applied is not None else None

    payload = {"council_gaps_top": gaps[:14], "fingal": fingal_report}
    (OUT / "council_drift_check.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
