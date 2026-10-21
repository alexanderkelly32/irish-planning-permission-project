#!/usr/bin/env python3
"""One improvement cycle: rebuild what new data justifies, re-measure, log.

Order:
1. Readiness check (planner-report coverage vs v5 targets).
2. Rebuild the v5 structured candidate if planner coverage grew since the
   previous cycle (or if its outputs are missing).
3. Refresh the interim evaluation.
4. Append a metrics snapshot to the improvement ledger and print deltas plus
   promotion-gate verdicts.

Promotion gates (manual, recorded as verdicts only - nothing is auto-promoted):
- structured candidate -> app: v5 AUC > v4 AUC AND AP within tolerance AND
  holdout heights >= MIN_HOLDOUT_HEIGHTS AND bootstrap CI excludes 0.5.
- v3 rebuild: only when a new full outcome year exists (see state docs); the
  frozen discipline is not automated here.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "05_policy" / "scripts"
DEVELOPMENT = ROOT / "02_development" / "scripts"

MIN_HOLDOUT_HEIGHTS = 30
AP_TOLERANCE = 0.01


def run_python(script: Path, *args: str) -> None:
    command = [sys.executable, str(script), *args]
    print(f"RUN: {' '.join(command)}", flush=True)
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout:
        tail = result.stdout.strip().splitlines()[-8:]
        print("\n".join(tail), flush=True)
    if result.stderr.strip():
        print("STDERR:", result.stderr.strip()[-400:], flush=True)


def main() -> None:
    from record_model_metrics import append_snapshot, collect_snapshot, read_ledger

    rows = read_ledger()
    previous = rows[-1] if rows else {}

    run_python(DEVELOPMENT / "check_structured_readiness.py")

    prev_reports = (previous.get("planner_reports") or {}).get("reports")
    current = collect_snapshot()
    cur_reports = (current.get("planner_reports") or {}).get("reports")
    v5_missing = not (ROOT / "05_policy" / "current" / "raw_planning_v5_optimiser_candidate.json").exists()
    if v5_missing or prev_reports is None or (cur_reports or 0) > (prev_reports or 0):
        print("planner coverage changed -> rebuilding the v5 structured candidate", flush=True)
        run_python(SCRIPTS / "build_structured_optimiser_v5.py")
    else:
        print("planner coverage unchanged since the last cycle -> v5 rebuild skipped", flush=True)

    run_python(DEVELOPMENT / "optimizer_interim_evaluation.py")
    snapshot = append_snapshot()

    v5 = snapshot["structured_candidate_v5"]
    v4 = snapshot["structured_incumbent_v4"]
    v5_auc = v5.get("auc")
    v4_auc = v4.get("auc")
    v5_ap = v5.get("ap")
    v4_ap = v4.get("ap")
    ci_low = v5.get("bootstrap_auc_low")
    heights = v5.get("holdout_heights") or 0

    gates = []
    auc_ok = v5_auc is not None and v4_auc is not None and v5_auc > v4_auc
    ap_ok = v5_ap is not None and v4_ap is not None and v5_ap >= (v4_ap - AP_TOLERANCE)
    ci_ok = ci_low is not None and ci_low > 0.5
    heights_ok = heights >= MIN_HOLDOUT_HEIGHTS
    gates.append({
        "gate": "structured candidate promotion",
        "status": "PASS" if (auc_ok and ap_ok and ci_ok and heights_ok) else "HOLD",
        "checks": {
            "v5_auc_over_v4": [round(v5_auc, 4) if v5_auc is not None else None, round(v4_auc, 4) if v4_auc is not None else None],
            "ap_within_tolerance": [round(v5_ap, 4) if v5_ap is not None else None, round(v4_ap, 4) if v4_ap is not None else None],
            "bootstrap_ci_excludes_05": ci_low,
            "holdout_heights_gte_30": heights,
        },
    })
    gates.append({
        "gate": "v3 rebuild",
        "status": "WAITING_ON_OUTCOMES",
        "note": "requires a full new outcome year (2026 decisions) recorded in a separate outcomes file; frozen discipline, manual promotion only.",
    })

    print()
    print("=== IMPROVEMENT CYCLE VERDICTS ===")
    for gate in gates:
        print(json.dumps(gate, indent=2))


if __name__ == "__main__":
    main()
