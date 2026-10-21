"""State-machine transitions: two untested observable pre-commencement states.

1. BCMS commencement-notice filing -> site start (statutory lead).
2. FSC/DAC first submission -> commencement (landmark test at 90/180d).

Both use data already held. No model fit - descriptive transition structure.
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


def main() -> None:
    report = {}
    bcms = pd.read_parquet(SILVER / "bcms_events_silver.parquet",
                           columns=["received_date_dt", "commencement_date_dt", "validation_date_dt"])
    for c in ("received_date_dt", "commencement_date_dt", "validation_date_dt"):
        bcms[c] = pd.to_datetime(bcms[c], utc=True, errors="coerce").dt.tz_localize(None)
    sub = bcms.dropna(subset=["received_date_dt", "commencement_date_dt"])
    lead = (sub["commencement_date_dt"] - sub["received_date_dt"]).dt.days
    lead = lead[(lead >= -60) & (lead <= 1500)]
    report["bcms_notice_to_commencement"] = {
        "n": int(len(lead)),
        "median_days": round(float(lead.median()), 1),
        "p25": round(float(lead.quantile(0.25)), 1),
        "p75": round(float(lead.quantile(0.75)), 1),
        "pct_within_14d": round(float((lead <= 14).mean() * 100), 1),
        "pct_within_28d": round(float((lead <= 28).mean() * 100), 1),
        "pct_within_60d": round(float((lead <= 60).mean() * 100), 1),
        "pct_within_90d": round(float((lead <= 90).mean() * 100), 1),
        "pct_commenced_before_filing": round(float((lead < 0).mean() * 100), 1),
    }

    fsc = pd.read_csv(SILVER / "infrastructure_readiness_features.csv")
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    m = fsc.merge(labels[["case_key", "activation"]], on="case_key", how="inner")
    m = m.dropna(subset=["fsc_first_submit_days_from_grant"])
    m["fsc_submit_days"] = pd.to_numeric(m["fsc_first_submit_days_from_grant"], errors="coerce")
    m = m.dropna(subset=["fsc_submit_days", "activation"])
    m = m[(m["fsc_submit_days"] >= 0) & (m["activation"] >= 0)]
    report["fsc_submission_landmark"] = {"n_total": int(len(m))}
    for t in (60, 90, 180):
        uncommenced = m[m["activation"] > t]
        if len(uncommenced) < 10:
            continue
        filed = uncommenced[uncommenced["fsc_submit_days"] <= t]
        not_filed = uncommenced[uncommenced["fsc_submit_days"] > t]
        entry = {"n_uncommenced": int(len(uncommenced)),
                 "n_filed": int(len(filed)), "n_not_filed": int(len(not_filed))}
        for name, grp in (("filed", filed), ("not_filed", not_filed)):
            if len(grp):
                remaining = grp["activation"] - t
                entry[f"{name}_median_remaining"] = round(float(remaining.median()), 1)
                entry[f"{name}_pct_commence_next_90"] = round(float((remaining <= 90).mean() * 100), 1)
                entry[f"{name}_pct_commence_next_180"] = round(float((remaining <= 180).mean() * 100), 1)
                entry[f"{name}_pct_commence_next_365"] = round(float((remaining <= 365).mean() * 100), 1)
        report["fsc_submission_landmark"][f"t{t}"] = entry

    out = SILVER / "state_machine_transitions.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
