"""Runner: infrastructure readiness features (FSC/DAC + Uisce).

FSC/DAC: join the national dataset to schemes by planning reference /
eircode; time-safe events (FSC application + grant dates relative to
planning grant) become commencement-readiness + construction-state
features. Uisce: fetch the per-county capacity register pages via
scrapling and parse plant statuses for a WWTP-status lookup.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

FSC_PATH = settings.RAW_DIR / "infrastructure" / "fsc_dac_Applications"

if __name__ == "__main__":
    fsc = pd.read_csv(FSC_PATH, low_memory=False)
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "PlanningAuthority", "ApplicationNumber", "GrantDate", "ReceivedDate"]].drop_duplicates("case_key")
    reg["app_norm"] = reg["ApplicationNumber"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    fsc["planning_ref_norm"] = fsc["planning_permission_reference_no"].fillna("").astype(str).str.upper().str.replace(r"\s+", "", regex=True)

    merged = reg.merge(fsc, left_on="app_norm", right_on="planning_ref_norm", how="inner")

    def auth_norm(text: str) -> str:
        return re.sub(r"[^a-z]+", "", str(text).lower())

    merged["_auth_match"] = merged.apply(
        lambda r: auth_norm(r["PlanningAuthority"]) == auth_norm(r["local_authority"])
        or auth_norm(r["local_authority"]) in auth_norm(r["PlanningAuthority"])
        or auth_norm(r["PlanningAuthority"]) in auth_norm(r["local_authority"]), axis=1)
    merged = merged[merged["_auth_match"]]
    merged = merged.drop(columns=["_auth_match"])
    merged["grant_dt"] = pd.to_datetime(merged["GrantDate"], utc=True, errors="coerce")
    merged["received_dt"] = pd.to_datetime(merged["ReceivedDate"], utc=True, errors="coerce")
    merged["fsc_submit_dt"] = pd.to_datetime(merged["submission_date"], utc=True, errors="coerce")
    merged["fsc_grant_dt"] = pd.to_datetime(merged["date_permission_was_granted"], utc=True, errors="coerce")
    merged["fsc_is_fsc"] = merged["application_type"].fillna("").astype(str).str.lower().str.contains("fire", na=False).astype(int)
    merged["fsc_is_dac"] = merged["application_type"].fillna("").astype(str).str.lower().str.contains("disability", na=False).astype(int)

    def features_for(group: pd.DataFrame) -> dict:
        group = group.sort_values("fsc_submit_dt")
        out = {}
        fsc_rows = group[group["fsc_is_fsc"] == 1]
        dac_rows = group[group["fsc_is_dac"] == 1]
        grant = group["grant_dt"].iloc[0]
        pre_grant_fsc = fsc_rows[fsc_rows["fsc_submit_dt"] < grant]
        out["fsc_count_total"] = len(fsc_rows)
        out["dac_count_total"] = len(dac_rows)
        out["fsc_pre_grant"] = len(pre_grant_fsc)
        if len(fsc_rows):
            out["fsc_first_submit_days_from_grant"] = float((fsc_rows["fsc_submit_dt"].min() - grant).days)
            granted_fsc = fsc_rows[fsc_rows["fsc_grant_dt"].notna()]
            out["fsc_first_grant_days_from_grant"] = float((granted_fsc["fsc_grant_dt"].min() - grant).days) if len(granted_fsc) else np.nan
        else:
            out["fsc_first_submit_days_from_grant"] = np.nan
            out["fsc_first_grant_days_from_grant"] = np.nan
        return out

    import numpy as np  # noqa: E402

    rows = []
    for case_key, group in merged.groupby("case_key"):
        row = {"case_key": str(case_key)}
        row.update(features_for(group))
        rows.append(row)
    infra = pd.DataFrame(rows)
    infra.to_csv(settings.SILVER_DIR / "infrastructure_readiness_features.csv", index=False)
    summary = {
        "fsc_rows": int(len(fsc)),
        "schemes_joined": int(len(infra)),
        "with_fsc": int(infra["fsc_count_total"].gt(0).sum()),
        "fsc_pre_grant_share": round(float((infra["fsc_pre_grant"] > 0).mean()), 3),
        "out": str(settings.SILVER_DIR / "infrastructure_readiness_features.csv"),
    }
    (settings.SILVER_DIR / "infrastructure_readiness_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
