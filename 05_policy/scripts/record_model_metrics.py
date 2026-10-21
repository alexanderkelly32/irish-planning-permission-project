#!/usr/bin/env python3
"""Append the current model metrics to the improvement ledger.

Reads the frozen baselines and candidate JSONs on disk and appends one dated
row to 05_policy/current/model_improvement_ledger.jsonl (append-only, so every
cycle is preserved). Run from run_improvement_cycle.py or standalone.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "05_policy" / "current"
LEDGER = CURRENT / "model_improvement_ledger.jsonl"

V3_BASELINE = ROOT / "05_policy" / "baselines" / "model_v3_2026-09-01.json"
V4_JSON = CURRENT / "raw_planning_structured_optimiser_candidate.json"
V5_JSON = CURRENT / "raw_planning_v5_optimiser_candidate.json"
BOTTLENECK = ROOT / "02_development" / "current" / "theme_tagging_scoring.json"
BACKTEST = None  # resolved per-cycle from the newest evaluation folder
READINESS = ROOT / "02_development" / "current" / "v5_optimiser_readiness.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _newest_backtest() -> dict:
    base = ROOT / "02_development" / "current"
    folders = sorted(base.glob("optimizer_interim_evaluation_*"), reverse=True)
    for folder in folders:
        for candidate in sorted(folder.glob("*.json"), reverse=True):
            payload = _load(candidate)
            if "blind_backtest" in payload:
                return payload
    return {}


def collect_snapshot() -> dict:
    v3 = _load(V3_BASELINE)
    v4 = _load(V4_JSON)
    v5 = _load(V5_JSON)
    bottleneck = _load(BOTTLENECK)
    readiness = _load(READINESS)
    evaluation = _newest_backtest()

    v3_holdout = v3.get("holdout") or {}
    v3_ranking = v3_holdout.get("ranking") or {}
    v3_calibrated = v3_holdout.get("calibrated") or {}
    v4_eval = (v4.get("evaluation") or {}).get("structured_logistic") or {}
    v5_eval = (v5.get("evaluation") or {}).get("v5_logistic") or {}
    v5_boot = (v5.get("evaluation") or {}).get("bootstrap_ci_v5_logistic") or {}
    v5_cohort = v5.get("cohort") or {}
    v5_test_counts = v5_cohort.get("report_value_counts_test") or {}
    backtest = evaluation.get("blind_backtest") or {}
    rerank = backtest.get("optimizer_most_common_first_theme_rerank") or {}
    conditioned = backtest.get("optimizer_theme_conditioned_directions") or {}
    readiness_fields = readiness.get("fields") or {}

    return {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "date": date.today().isoformat(),
        "v3": {
            "auc": v3_ranking.get("roc_auc"),
            "ap": v3_ranking.get("average_precision"),
            "brier": v3_calibrated.get("brier"),
        },
        "structured_incumbent_v4": {
            "auc": v4_eval.get("roc_auc"),
            "ap": v4_eval.get("average_precision"),
        },
        "structured_candidate_v5": {
            "auc": v5_eval.get("roc_auc"),
            "ap": v5_eval.get("average_precision"),
            "calibrated_brier": v5_eval.get("brier"),
            "bootstrap_auc_low": (v5_boot.get("roc_auc") or {}).get("p05"),
            "bootstrap_auc_high": (v5_boot.get("roc_auc") or {}).get("p95"),
            "holdout_heights": v5_test_counts.get("height_present"),
            "holdout_access": v5_test_counts.get("access_present"),
            "joinable_rows": v5_cohort.get("planner_report_joinable_rows"),
        },
        "bottleneck_top1": bottleneck.get("top1_accuracy"),
        "backtest": {
            "top3_match": rerank.get("top3_match"),
            "direction_correct": conditioned.get("direction_correct_rate") or rerank.get("direction_correct_rate"),
        },
        "planner_reports": {
            "reports": readiness.get("planner_reports"),
            "heights": (readiness_fields.get("max_height_m") or {}).get("values"),
            "storeys": (readiness_fields.get("max_storeys") or {}).get("values"),
            "separations": (readiness_fields.get("nearest_dwelling_separation_m") or {}).get("values"),
        },
    }


def append_snapshot() -> dict:
    snapshot = collect_snapshot()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(snapshot) + "\n")
    return snapshot


def read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


if __name__ == "__main__":
    snapshot = append_snapshot()
    print(json.dumps(snapshot, indent=2))
