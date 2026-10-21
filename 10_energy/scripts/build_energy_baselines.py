#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "10_energy" / "source_data" / "energy_cohort.csv"
DEFAULT_OUTPUT_DIR = ROOT / "10_energy" / "source_data"

Z = 1.959964


def wilson(k: int, n: int, z: float = Z) -> Tuple[Optional[float], Optional[float]]:
    if n == 0:
        return None, None
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt((phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def rate_row(k: int, n: int) -> Dict[str, object]:
    lo, hi = wilson(k, n)
    return {
        "n_decided": n,
        "n_refused": k,
        "refusal_rate": round(k / n, 4) if n else None,
        "wilson_lo": round(lo, 4) if lo is not None else None,
        "wilson_hi": round(hi, 4) if hi is not None else None,
    }


def refusal_table(frame: pd.DataFrame, group_cols: List[str], min_n: int = 1) -> Dict[str, Dict[str, object]]:
    out: Dict[str, Dict[str, object]] = {}
    for key, sub in frame.groupby(group_cols, dropna=False):
        decided = sub[sub["outcome"].isin(["grant", "refuse"])]
        n = int(len(decided))
        if n < min_n:
            continue
        k = int((decided["outcome"] == "refuse").sum())
        label = key if not isinstance(key, tuple) else "|".join(str(x) for x in key)
        out[label] = rate_row(k, n)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Reference-class baselines for the energy cohort.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    df = pd.read_csv(args.input, dtype=str, low_memory=False)
    df["received_dt"] = pd.to_datetime(df["received_date"], format="mixed", utc=True, errors="coerce")
    df["decision_dt"] = pd.to_datetime(df["decision_date"], format="mixed", utc=True, errors="coerce")
    df["received_year"] = df["received_dt"].dt.year
    df["decision_days"] = (df["decision_dt"] - df["received_dt"]).dt.days
    df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce")

    utility = df[df["is_utility_scale"].astype(str) == "True"].copy()
    utility = utility[utility["energy_type"] != "data_centre"]

    report: Dict[str, object] = {}

    report["overall"] = {
        "cohort_rows": int(len(df)),
        "utility_rows": int(len(utility)),
        "utility_decided": int(utility["outcome"].isin(["grant", "refuse"]).sum()),
        "utility_undecided": int((utility["outcome"] == "undecided").sum()),
    }
    report["overall"]["utility"] = rate_row(
        int((utility["outcome"] == "refuse").sum()),
        int(utility["outcome"].isin(["grant", "refuse"]).sum()),
    )

    report["by_type_utility"] = refusal_table(utility, ["energy_type"])
    report["by_type_all"] = refusal_table(df, ["energy_type"])

    by_authority = refusal_table(utility, ["planning_authority"], min_n=10)
    report["by_authority_utility"] = dict(
        sorted(by_authority.items(), key=lambda item: -(item[1]["n_decided"] or 0))
    )

    report["by_year_utility"] = refusal_table(utility, ["received_year"])

    bands = [-1.0, 5.0, 20.0, 50.0, 100.0, float("inf")]
    band_labels = ["<5MW", "5-20MW", "20-50MW", "50-100MW", "100MW+"]
    utility["mw_band"] = pd.cut(
        utility["capacity_mw"], bins=bands, labels=band_labels, right=True
    ).astype(object)
    report["by_capacity_band_utility"] = refusal_table(utility, ["mw_band"])

    for t in ["solar", "wind", "bess", "grid", "biogas"]:
        sub = utility[utility["energy_type"] == t]
        if len(sub) == 0:
            continue
        report[f"by_authority_{t}"] = refusal_table(sub, ["planning_authority"], min_n=5)

    timing: Dict[str, object] = {}
    decided_timing = utility[utility["outcome"].isin(["grant", "refuse"]) & utility["decision_days"].notna()]
    timing["n_with_decision_dates"] = int(len(decided_timing))
    timing["overall_days"] = {
        "p20": round(float(decided_timing["decision_days"].quantile(0.20)), 1),
        "p50": round(float(decided_timing["decision_days"].quantile(0.50)), 1),
        "p80": round(float(decided_timing["decision_days"].quantile(0.80)), 1),
    }
    for t in ["solar", "wind", "bess", "grid"]:
        sub = decided_timing[decided_timing["energy_type"] == t]
        if len(sub) < 5:
            continue
        timing[f"{t}_days"] = {
            "n": int(len(sub)),
            "p20": round(float(sub["decision_days"].quantile(0.20)), 1),
            "p50": round(float(sub["decision_days"].quantile(0.50)), 1),
            "p80": round(float(sub["decision_days"].quantile(0.80)), 1),
        }
    report["decision_timing"] = timing

    out_json = args.output_dir / "energy_baselines.json"
    with out_json.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)

    authority_rows = [
        {"planning_authority": key, **value}
        for key, value in report["by_authority_utility"].items()
    ]
    pd.DataFrame(authority_rows).to_csv(args.output_dir / "energy_refusal_by_authority.csv", index=False)

    year_rows = [
        {"received_year": key, **value}
        for key, value in report["by_year_utility"].items()
    ]
    pd.DataFrame(year_rows).to_csv(args.output_dir / "energy_refusal_by_year.csv", index=False)

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
