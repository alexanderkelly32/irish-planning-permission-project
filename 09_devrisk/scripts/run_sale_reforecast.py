"""Runner: post-commencement sale re-forecast (monitoring tier).

At grant date, sale timing is ~1,485d-wide honest intervals. Once a scheme
commences, BCMS gives us the developer's DECLARED completion date
(proposed_end_date_dt), phase count and unit mix - post-submission features
that are legitimate for a monitoring product. Measure how much tighter the
sale interval gets when conditioned on those.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = pd.read_csv(settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv")
    links = pd.concat([links, overlay.reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    events = confirmed.merge(bcms, on="bcms_event_id", how="inner")

    sold = exit_labels[exit_labels["sales_linked"] > 0].copy()
    sold["first_sale_dt"] = pd.to_datetime(sold["first_sale_date"], utc=True, errors="coerce")
    sold = sold.dropna(subset=["first_sale_dt"])

    report = {}
    for target_col in ("commencement", "completion"):
        rows = []
        for scheme_id, group in events.groupby("scheme_id"):
            comm = pd.to_datetime(group["commencement_date_dt"], utc=True, errors="coerce").min()
            declared = pd.to_datetime(group["proposed_end_date_dt"], utc=True, errors="coerce").min()
            ccc = pd.to_datetime(group["completion_certificate_date_dt"], utc=True, errors="coerce")
            ccc = ccc.min() if ccc.notna().any() else pd.NaT
            anchor = comm if target_col == "commencement" else (ccc if pd.notna(ccc) else None)
            if anchor is None or pd.isna(anchor):
                continue
            scheme = sold[sold["scheme_id"] == str(scheme_id)]
            if scheme.empty:
                continue
            tfs = (scheme.iloc[0]["first_sale_dt"] - anchor).days
            declared_duration = (declared - comm).days if pd.notna(declared) and pd.notna(comm) else np.nan
            rows.append({
                "scheme_id": str(scheme_id),
                "anchor": target_col,
                "time_to_first_sale": tfs,
                "n_notices": int(len(group)),
                "declared_build_days": declared_duration,
                "dwellings_total": float(pd.to_numeric(group["dwellings_total"], errors="coerce").sum()),
                "apartments_total": float(pd.to_numeric(group["apartments_total"], errors="coerce").sum()),
            })
        frame = pd.DataFrame(rows)
        frame = frame[frame["time_to_first_sale"].between(-180, 3000)]
        if frame.empty:
            continue
        lo, hi = np.quantile(frame["time_to_first_sale"], [0.1, 0.9])
        report[target_col] = {
            "n": int(len(frame)),
            "median_days": round(float(frame["time_to_first_sale"].median()), 0),
            "interval_80_width_days": round(float(hi - lo), 0),
            "coverage": round(float(np.mean(frame["time_to_first_sale"].between(lo, hi))), 3),
            "share_within_180d_of_median": round(float(np.mean(np.abs(frame["time_to_first_sale"] - frame["time_to_first_sale"].median()) <= 180)), 3),
            "share_within_365d_of_median": round(float(np.mean(np.abs(frame["time_to_first_sale"] - frame["time_to_first_sale"].median()) <= 365)), 3),
        }
        # declared duration signal
        valid = frame.dropna(subset=["declared_build_days"])
        if len(valid) >= 30:
            corr = np.corrcoef(valid["declared_build_days"], valid["time_to_first_sale"])[0, 1]
            report[target_col]["corr_declared_duration_vs_sale"] = round(float(corr), 3)
            report[target_col]["declared_duration_n"] = int(len(valid))
            # split by declared duration tercile
            valid = valid.copy()
            valid["tercile"] = pd.qcut(valid["declared_build_days"], 3, labels=["short", "mid", "long"])
            report[target_col]["by_declared_duration"] = {
                str(t): {
                    "n": int(len(part)),
                    "median_days": round(float(part["time_to_first_sale"].median()), 0),
                    "width_80": round(float(np.quantile(part["time_to_first_sale"], 0.9) - np.quantile(part["time_to_first_sale"], 0.1)), 0),
                }
                for t, part in valid.groupby("tercile", observed=True)
            }

    out = settings.SILVER_DIR / "sale_reforecast_postcommencement.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
