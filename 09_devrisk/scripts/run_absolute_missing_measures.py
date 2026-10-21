"""Absolute-accuracy read: the two missing milestone measures.

1. Completion timing (commencement -> CCC): distribution, and how well the
   developer's declared build duration (planned_duration_days) predicts the
   actual build duration.
2. Price benchmark: how far scheme median prices sit from their same-county
   benchmark in euros (absolute deviation).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    report: dict = {}

    # ---- 1. completion duration ----
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    events = confirmed.merge(bcms, on="bcms_event_id", how="inner")

    build_rows = []
    for scheme_id, group in events.groupby("scheme_id"):
        comm = pd.to_datetime(group["commencement_date_dt"], utc=True, errors="coerce").min()
        ccc = pd.to_datetime(group["completion_certificate_date_dt"], utc=True, errors="coerce").dropna()
        if pd.isna(comm) or ccc.empty:
            continue
        actual = (ccc.min() - comm).days
        declared = pd.to_numeric(group["planned_duration_days"], errors="coerce").dropna()
        build_rows.append({
            "scheme_id": str(scheme_id),
            "actual_build_days": actual,
            "declared_median_days": float(declared.median()) if len(declared) else np.nan,
        })
    build = pd.DataFrame(build_rows)
    build = build[build["actual_build_days"].between(0, 3000)]
    med = build["actual_build_days"].median()
    err = np.abs(build["actual_build_days"] - med)
    valid = build.dropna(subset=["declared_median_days"])
    valid = valid[valid["declared_median_days"].between(30, 3000)]
    declared_err = np.abs(valid["actual_build_days"] - valid["declared_median_days"])
    report["completion_duration"] = {
        "n": int(len(build)),
        "median_actual_days": round(float(med), 0),
        "mae_constant_median": round(float(err.mean()), 0),
        "share_within_90d_of_median": round(float(np.mean(err <= 90)), 3),
        "share_within_180d_of_median": round(float(np.mean(err <= 180)), 3),
        "share_within_365d_of_median": round(float(np.mean(err <= 365)), 3),
        "declared_vs_actual": {
            "n": int(len(valid)),
            "mae_declared": round(float(declared_err.mean()), 0),
            "share_declared_within_90d": round(float(np.mean(declared_err <= 90)), 3),
            "share_declared_within_180d": round(float(np.mean(declared_err <= 180)), 3),
            "corr": round(float(np.corrcoef(valid["actual_build_days"], valid["declared_median_days"])[0, 1]), 3),
        },
    }

    # ---- 2. price benchmark absolute deviation ----
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    priced = exit_labels[exit_labels["median_price"].notna() & exit_labels["benchmark_median"].notna()].copy()
    deviation = (priced["median_price"] - priced["benchmark_median"]).abs()
    rel_dev = deviation / priced["benchmark_median"]
    report["price_benchmark"] = {
        "n": int(len(priced)),
        "median_abs_deviation_eur": round(float(deviation.median()), 0),
        "mean_abs_deviation_eur": round(float(deviation.mean()), 0),
        "median_abs_deviation_pct": round(float(rel_dev.median()) * 100, 1),
        "p80_abs_deviation_eur": round(float(deviation.quantile(0.8)), 0),
        "scheme_median_price_median": round(float(priced["median_price"].median()), 0),
    }

    out = settings.SILVER_DIR / "absolute_accuracy_missing_measures.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
