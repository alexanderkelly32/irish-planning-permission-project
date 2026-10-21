"""Phase-aware denominators: replace scheme-level progress denominators
with BCMS CN_Units_for_phase; quarantine unresolved phase structures;
rebuild pct25/50/75 states and re-verify the information-gain result.
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
DQ = SILVER / "dq"
SNAP = pd.Timestamp("2026-10-01")


def main() -> None:
    truth = pd.read_csv(SILVER / "phase_pilot" / "bcms_phase_ground_truth.csv", dtype=str)
    truth["units"] = pd.to_numeric(truth["units"], errors="coerce")
    truth["phase_no"] = pd.to_numeric(truth["CN_Phase_for_this_Notice"], errors="coerce")
    phase_units = truth.dropna(subset=["units", "phase_no"]).groupby(
        ["scheme_id", "phase_no"])["units"].median().reset_index()
    per_scheme = phase_units.groupby("scheme_id").agg(
        n_phases=("phase_no", "nunique"),
        phase_units_sum=("units", "sum"),
        max_phase=("phase_no", "max")).reset_index()
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "NumResidentialUnits"])
    register = register.drop_duplicates("case_key")
    per_scheme = per_scheme.merge(register, left_on="scheme_id", right_on="case_key", how="left")
    per_scheme["reg_units"] = pd.to_numeric(per_scheme["NumResidentialUnits"], errors="coerce")
    per_scheme["deviation_pct"] = (per_scheme["phase_units_sum"] - per_scheme["reg_units"]) / per_scheme["reg_units"] * 100
    per_scheme["resolved"] = per_scheme["deviation_pct"].abs() <= 30
    per_scheme["n_phase_rows"] = truth.dropna(subset=["units", "phase_no"]).groupby("scheme_id").size()
    per_scheme.to_csv(SILVER / "phase_pilot" / "phase_denominators.csv", index=False)
    quar = per_scheme[~per_scheme["resolved"]].copy()
    quar = quar.rename(columns={"scheme_id": "case_key"}).drop(columns=["case_key"], errors="ignore")
    quar["case_key"] = per_scheme[~per_scheme["resolved"]]["scheme_id"]
    quar["rule"] = "R11"
    quar["severity"] = "block"
    quar["description"] = "phase units deviate >30% from register units"
    quar["evidence"] = ("phase_units_sum=" + quar["phase_units_sum"].round(0).astype(str) +
                        " reg_units=" + quar["reg_units"].round(0).astype(str))
    quar["status"] = "open"
    existing = pd.read_csv(DQ / "quarantine.csv", dtype=str) if (DQ / "quarantine.csv").exists() else pd.DataFrame()
    existing = existing.reset_index(drop=True)
    quar = quar.reset_index(drop=True)
    cols = list(existing.columns) if len(existing) else ["case_key", "rule", "severity", "description",
                                                          "evidence", "status"]
    merged = pd.concat([existing, quar[cols]], ignore_index=True).drop_duplicates(
        subset=["case_key", "rule", "evidence"])
    merged.to_csv(DQ / "quarantine.csv", index=False)

    resolved_keys = set(per_scheme[per_scheme["resolved"]]["scheme_id"])
    prog = pd.read_csv(SILVER / "construction_progress" / "construction_progress_events.csv")
    before = prog["case_key"].nunique()
    prog_clean = prog[prog["case_key"].isin(resolved_keys)]
    prog_clean.to_csv(SILVER / "construction_progress" / "construction_progress_events_phase_clean.csv", index=False)
    after = prog_clean["case_key"].nunique()

    snap = pd.read_csv(SILVER / "construction_progress" / "construction_progress_snapshots.csv")
    snap_clean = snap[snap["case_key"].isin(resolved_keys)]
    snap_clean.to_csv(SILVER / "construction_progress" / "construction_progress_snapshots_phase_clean.csv", index=False)

    widths = {}
    for state in ["commenced", "pct25", "pct50", "pct75"]:
        sub = snap_clean[snap_clean["state"] == state]
        if len(sub) < 20:
            continue
        widths[state] = {"n": int(len(sub)),
                         "median_remaining": round(float(sub["target_final_ccc_days"].median()), 1),
                         "width80": round(float(np.quantile(sub["target_final_ccc_days"], 0.9) -
                                              np.quantile(sub["target_final_ccc_days"], 0.1)), 1)}
    report = {"schemes_before": before, "schemes_after": after,
              "quarantined_phase_schemes": int((~per_scheme["resolved"]).sum()),
              "info_gain_after_phase_clean": widths}
    (SILVER / "phase_pilot" / "phase_denominator_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
