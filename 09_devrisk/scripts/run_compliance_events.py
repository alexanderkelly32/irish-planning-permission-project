"""Runner: C. Compliance-submission events from the register.

Searches the full register for applications that are compliance
submissions (type/description containing 'compliance'), links them to
parent permissions spatially (<=60m) and chronologically (after parent
decision), builds per-scheme compliance-event features (first submission
date, count, accepted date where decision granted).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    reg = register.drop_duplicates("case_key")
    reg["east"] = pd.to_numeric(reg["ITMEasting"], errors="coerce")
    reg["north"] = pd.to_numeric(reg["ITMNorthing"], errors="coerce")
    reg["received_dt"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce")
    reg["decision_dt"] = pd.to_datetime(reg["DecisionDate"], utc=True, errors="coerce")
    is_compliance = (
        reg["ApplicationType"].fillna("").astype(str).str.contains("compliance", case=False, na=False)
        | reg["DevelopmentDescription"].fillna("").astype(str).str.lower().str.contains(
            r"compliance (submission|with condition)|condition complian", na=False, regex=True)
    )
    compliance = reg[is_compliance & reg["east"].notna()].copy()
    pool = reg[reg["case_key"].astype(str).isin(set(labels["case_key"].astype(str)))].copy()

    tree = cKDTree(compliance[["east", "north"]].to_numpy())
    rows = []
    for _, scheme in pool.iterrows():
        if pd.isna(scheme["east"]):
            rows.append({"case_key": str(scheme["case_key"]), "n_compliance_submissions": 0})
            continue
        idx = tree.query_ball_point([scheme["east"], scheme["north"]], 60.0)
        if not idx:
            rows.append({"case_key": str(scheme["case_key"]), "n_compliance_submissions": 0})
            continue
        subs = compliance.iloc[idx]
        subs = subs[subs["received_dt"] > scheme["decision_dt"]] if pd.notna(scheme["decision_dt"]) else subs
        if len(subs) == 0:
            rows.append({"case_key": str(scheme["case_key"]), "n_compliance_submissions": 0})
            continue
        first = subs["received_dt"].min()
        accepted = subs[subs["Decision"].fillna("").astype(str).str.upper().str.contains("GRANT")]["decision_dt"]
        rows.append({
            "case_key": str(scheme["case_key"]),
            "n_compliance_submissions": int(len(subs)),
            "first_compliance_submission_days_after_decision": float((first - scheme["decision_dt"]).days) if pd.notna(scheme["decision_dt"]) else np.nan,
            "compliance_accepted": int(accepted.notna().any()),
        })
    features = pd.DataFrame(rows)
    features.to_csv(settings.SILVER_DIR / "compliance_event_features.csv", index=False)
    report = {
        "compliance_apps_national": int(len(compliance)),
        "pool_with_compliance_events": int((features["n_compliance_submissions"] > 0).sum()),
        "share_of_pool": round(float((features["n_compliance_submissions"] > 0).mean()), 3),
        "out": str(settings.SILVER_DIR / "compliance_event_features.csv"),
    }
    (settings.SILVER_DIR / "compliance_event_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
