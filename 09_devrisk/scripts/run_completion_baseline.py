"""Runner: completion survival baseline (commencement -> completion certificate).

KM overall and by size band. Completion durations only among schemes with a
confirmed commencement; schemes without a CCC by the censor date are
right-censored at censor. Research baseline (brief 15.4): no model claims.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.survival import kaplan_meier, km_probability_by, median_survival_time  # noqa: E402

CENSOR_DATE = "2026-09-27"

if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv")
    labels = labels.rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = labels.merge(
        register[["case_key", "NumResidentialUnits", "GrantDate"]], on="case_key", how="inner"
    ).drop_duplicates("case_key").copy()
    frame = frame[frame["activation_linked"].astype(bool)].copy()  # only commenced schemes

    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["size_band"] = pd.cut(units, bins=[-np.inf, 29, 99, 249, np.inf], labels=["10-29", "30-99", "100-249", "250+"])

    censor = pd.Timestamp(CENSOR_DATE, tz="UTC")
    durations = []
    events = []
    bands = []
    for _, row in frame.iterrows():
        grant = pd.Timestamp(row["GrantDate"])
        if grant.tzinfo is None:
            grant = grant.tz_localize("UTC")
        grant = grant.tz_convert("UTC")
        activation_days = row["activation_days"]
        start = grant + pd.Timedelta(days=int(activation_days)) if pd.notna(activation_days) else grant
        if pd.isna(row["completion_days"]) or not row["completion_linked"]:
            followup = (censor - start).days
            durations.append(max(followup, 0))
            events.append(0)
        else:
            durations.append(max(float(row["completion_days"]), 0))
            events.append(1)
        bands.append(str(row["size_band"]))

    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=int)
    report = {"n_commenced": int(len(durations)), "n_completed": int(events.sum())}
    overall = kaplan_meier(durations, events)
    report["overall"] = {
        "median_days": median_survival_time(overall),
        "p_complete_by_24m": round(km_probability_by(overall, 730), 3),
        "p_complete_by_36m": round(km_probability_by(overall, 1096), 3),
        "p_complete_by_48m": round(km_probability_by(overall, 1460), 3),
    }
    strata = {}
    for band in ["10-29", "30-99", "100-249", "250+"]:
        mask = np.asarray(bands) == band
        if mask.sum() < 20:
            continue
        table = kaplan_meier(durations[mask], events[mask])
        strata[band] = {
            "n": int(mask.sum()),
            "completed": int(events[mask].sum()),
            "median_days": median_survival_time(table),
            "p_complete_by_36m": round(km_probability_by(table, 1096), 3),
        }
    report["by_size_band"] = strata

    out = settings.SILVER_DIR / "completion_survival_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
