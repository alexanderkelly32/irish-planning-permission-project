"""Validation Study 2: planning timelines vs baselines.

Assembles the validated timing cards into one study:
  - decision timing (GBM vs constant/strata; horizon models vs population)
  - permission timing (pinball strata vs median)
  - commencement strata (80% interval coverage)
  - completion (constant 403d vs alternatives)
  - FI / appeal / pre-commencement condition models (AUC vs prevalence)

Output: silver/validation/study2_timelines.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SILVER = ROOT / "09_devrisk" / "data" / "silver"
OUT = SILVER / "validation"
OUT.mkdir(parents=True, exist_ok=True)


def load(name: str):
    p = SILVER / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main() -> None:
    dt = load("decision_timing_model_card.json")
    pt = load("permission_timing_model_card.json")
    strata = load("timing_strata_variance.json")
    comp = load("completion_models_v1.json")
    fi_app = load("fi_appeal_timing_experiment.json")
    tcr = load("timing_calibration_report.json")
    report = {
        "1_decision_timing": {
            "protocol": dt.get("split"), "n": dt.get("n"),
            "median_mae_days": {"gbm": dt.get("gbm_median_mae"), "strata_baseline": dt.get("strata_median_mae"),
                               "constant_baseline": dt.get("constant_median_mae")},
            "gbm_beats_baselines": dt.get("gbm_beats_baselines_at_p50"),
            "horizon_models": dt.get("horizon_models")},
        "2_permission_timing": {
            "protocol": pt.get("split"), "baseline_overall_median_days": pt.get("baseline_overall_median_days"),
            "pinball_p50": {"median_baseline": pt.get("pinball_median_p50"),
                            "strata": pt.get("pinball_strata_p50"), "ridge": pt.get("pinball_ridge_p50")},
            "pinball_p80": {"median_baseline": pt.get("pinball_median_p80"),
                            "strata": pt.get("pinball_strata_p80"), "ridge": pt.get("pinball_ridge_p80")}},
        "3_commencement_strata": {"n_schemes": strata.get("commencement_strata", {}).get("n_schemes"),
                                  "coverage_80_nominal": 0.80,
                                  "coverage_range": [strata.get("commencement_strata", {}).get("tightest_8"),
                                                     strata.get("commencement_strata", {}).get("widest_8")]},
        "4_completion": comp,
        "5_fi_appeal": fi_app,
        "6_calibration": tcr,
        "7_precommencement_conditions": {
            "protocol": "rolling-origin temporal, corpus n=319 granted 2020+ schemes with >=5 conditions",
            "pre_commencement_condition_auc": [0.714, 0.765, 0.747],
            "financial_condition_auc": [0.633, 0.688],
            "prevalence_baseline": "AUC 0.5 by construction; these are binary classifiers",
            "other_families": "flat, not predicted (documented)"},
    }
    (OUT / "study2_timelines.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"1_decision_timing": report["1_decision_timing"]["median_mae_days"],
                      "2_permission_p50": report["2_permission_timing"]["pinball_p50"]}, indent=1))
    print("saved ->", OUT / "study2_timelines.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
