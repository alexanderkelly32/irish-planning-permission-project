"""Runner: feature-snapshots table (phase plan item) - from the event
ledger. Per scheme, the state at each landmark (submission, grant,
commencement, first CCC, first sale) with dates - the snapshot substrate
for landmark re-forecasting."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    ledger = pd.read_csv(settings.GOLD_DIR / "event_ledger.csv")
    rows = []
    for dev_id, group in ledger.groupby("development_id"):
        snapshot = {"development_id": dev_id}
        for event_type in ("planning_received", "planning_granted", "bcms_commencement",
                           "completion_certificate", "first_sale"):
            part = group[group["event_type"] == event_type]
            snapshot[f"{event_type}_date"] = part["event_date_start"].min() if len(part) else None
        snapshot["n_events"] = len(group)
        rows.append(snapshot)
    frame = pd.DataFrame(rows)
    frame.to_csv(settings.SILVER_DIR / "feature_snapshots.csv", index=False)
    report = {
        "schemes": int(len(frame)),
        "with_grant": int(frame["planning_granted_date"].notna().sum()),
        "with_commencement": int(frame["bcms_commencement_date"].notna().sum()),
        "with_ccc": int(frame["completion_certificate_date"].notna().sum()),
        "with_sale": int(frame["first_sale_date"].notna().sum()),
        "out": str(settings.SILVER_DIR / "feature_snapshots.csv"),
    }
    (settings.SILVER_DIR / "feature_snapshots_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
