"""Validation Study 1: planning outcomes vs simple historical baselines.

Assembles existing validated artifacts into one head-to-head:
  - national prior, authority prior, authority x size prior (simple baselines)
  - raw benchmark model (national 2024-25 holdout)
  - frozen v4-full (promoted)
  - calibration by project size and authority on the v4 2025 holdout

Output: 09_devrisk/data/silver/validation/study1_outcomes.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "09_devrisk" / "data" / "silver" / "validation"
OUT.mkdir(parents=True, exist_ok=True)
CUR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(ROOT / "09_devrisk"))
from devrisk import settings  # noqa: E402


def brier(y, p):
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def main() -> None:
    v4_preds = pd.read_csv(CUR / "raw_planning_v4_2025_predictions.csv", low_memory=False)
    raw_preds = pd.read_csv(CUR / "raw_planning_national_predictions.csv", low_memory=False)
    keep = [c for c in ["case_key", "PlanningAuthority", "application_bucket", "target_refused",
                        "v4_platt_risk", "units", "NumResidentialUnits", "received_date_dt"] if c in v4_preds.columns]
    v4 = v4_preds[keep].copy()
    v4["p"] = pd.to_numeric(v4["v4_platt_risk"], errors="coerce")
    v4["y"] = pd.to_numeric(v4["target_refused"], errors="coerce")
    v4 = v4.dropna(subset=["p", "y"])
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "NumResidentialUnits"])
    reg = reg.drop_duplicates("case_key")
    v4 = v4.merge(reg, on="case_key", how="left")
    v4["units"] = pd.to_numeric(v4["NumResidentialUnits"], errors="coerce")
    v4["size"] = pd.cut(v4["units"], [-1, 9, 30, 80, 500], labels=["1-9", "10-29", "30-79", "80+"])
    year_col = "received_date_dt"
    v4["year"] = pd.to_datetime(v4[year_col], utc=True, errors="coerce").dt.year
    report = {"holdout_n": int(len(v4)),
              "refusal_rate": round(float(v4["y"].mean()), 4),
              "year_range": [int(v4["year"].min()), int(v4["year"].max())],
              "models": {}}

    # simple baselines on the v4 holdout
    prior = float(v4["y"].mean())
    auth_prior = v4.groupby("PlanningAuthority")["y"].transform("mean")
    auth_size_prior = v4.groupby(["PlanningAuthority", "size"], observed=True)["y"].transform("mean").fillna(auth_prior)
    for name, p in (("national_prior", prior), ("authority_prior", auth_prior),
                    ("authority_size_prior", auth_size_prior)):
        report["models"][name] = {"brier": round(brier(v4["y"], p), 4),
                                  "log_loss": round(float(-np.mean(v4["y"] * np.log(np.clip(p, 1e-6, 1))
                                                                    + (1 - v4["y"]) * np.log(np.clip(1 - p, 1e-6, 1)))), 4)}
    # v4-full on this holdout
    report["models"]["v4_full_frozen"] = {
        "roc_auc": round(float(roc_auc_score(v4["y"], v4["p"])), 4),
        "brier": round(brier(v4["y"], v4["p"]), 4),
        "log_loss": round(float(-np.mean(v4["y"] * np.log(np.clip(v4["p"], 1e-6, 1))
                                         + (1 - v4["y"]) * np.log(np.clip(1 - v4["p"], 1e-6, 1)))), 4),
    }
    # raw benchmark model
    raw = raw_preds[["case_key", "target_refused", "refusal_score"]].copy()
    raw["p"] = pd.to_numeric(raw["refusal_score"], errors="coerce")
    raw["y"] = pd.to_numeric(raw["target_refused"], errors="coerce")
    raw = raw.dropna(subset=["p", "y"])
    report["models"]["raw_benchmark_model"] = {
        "n": int(len(raw)), "roc_auc": round(float(roc_auc_score(raw["y"], raw["p"])), 4),
        "brier": round(brier(raw["y"], raw["p"]), 4)}

    # calibration by size and authority for v4
    def reliability(g):
        g = g.copy()
        g["decile"] = pd.qcut(g["p"], 10, labels=False, duplicates="drop")
        rows = []
        for d, gg in g.groupby("decile"):
            rows.append({"decile": int(d), "n": int(len(gg)), "mean_pred": round(float(gg["p"].mean()), 4),
                         "obs_rate": round(float(gg["y"].mean()), 4)})
        return rows
    report["calibration_by_size"] = {str(k): reliability(g) for k, g in v4.groupby("size", observed=True)}
    report["calibration_by_authority"] = {}
    for auth, g in v4.groupby("PlanningAuthority"):
        if len(g) >= 100:
            report["calibration_by_authority"][auth] = {
                "n": int(len(g)), "obs_rate": round(float(g["y"].mean()), 4),
                "mean_pred": round(float(g["p"].mean()), 4),
                "brier": round(brier(g["y"], g["p"]), 4),
                "brier_authority_prior": round(brier(g["y"], g["y"].mean()), 4),
                "auc": round(float(roc_auc_score(g["y"], g["p"])), 4) if g["y"].nunique() == 2 else None}
    # size-band AUC vs prior
    report["by_size"] = {}
    for k, g in v4.groupby("size", observed=True):
        report["by_size"][str(k)] = {
            "n": int(len(g)), "refusal_rate": round(float(g["y"].mean()), 4),
            "auc": round(float(roc_auc_score(g["y"], g["p"])), 4) if g["y"].nunique() == 2 else None,
            "brier": round(brier(g["y"], g["p"]), 4),
            "brier_prior": round(brier(g["y"], g["y"].mean()), 4)}
    (OUT / "study1_outcomes.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report["models"], indent=1))
    print("by_size:", json.dumps(report["by_size"], indent=1))
    print("saved ->", OUT / "study1_outcomes.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
