"""Runner: build FI/appeal v2 label pools using the 4Dublin pipeline fields.

The pipeline independently maintains FI_Request / Appeal_Submitted / Appeal_Date
for Dublin schemes. Where the register is silent (null), the pipeline value is
taken as the label. Where the register already says the event happened, the
register wins (primary source). Produces fi_appeal_labels_v2.csv.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

DUBLIN_AUTHORITIES = {"Dublin City Council", "Dun Laoghaire Rathdown County Council",
                      "Fingal County Council", "South Dublin County Council"}


def app_norm(raw: object) -> str:
    return re.sub(r"\s+", "", str(raw or "").strip().upper())


if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    frame = register[units.ge(10)].copy()
    frame["app_norm"] = frame["ApplicationNumber"].map(app_norm)
    frame["fi_dt_reg"] = pd.to_datetime(frame[["FIRequestDate", "FIRecDate"]].min(axis=1), utc=True, errors="coerce")
    frame["appeal_dt_reg"] = pd.to_datetime(frame["AppealSubmittedDate"], utc=True, errors="coerce")

    pipe = pd.read_csv(settings.SILVER_DIR / "4dublin" / "pipeline_all.csv", low_memory=False)
    pipe = pipe[pipe["Planning_Authority"].isin(DUBLIN_AUTHORITIES)].copy()
    pipe["app_norm"] = pipe["Planning_Reference"].map(app_norm)
    pipe = pipe.sort_values(["app_norm", "Year_Quarter"])
    latest = pipe.groupby("app_norm").tail(1)
    latest = latest[["app_norm", "FI_Request", "Appeal_Submitted", "Appeal_Date"]].copy()
    latest["fi_pipe_yes"] = latest["FI_Request"].astype(str).str.strip().str.lower().eq("yes")
    latest["appeal_pipe_yes"] = latest["Appeal_Submitted"].astype(str).str.strip().str.lower().eq("yes")
    latest["appeal_pipe_dt"] = pd.to_datetime(latest["Appeal_Date"], utc=True, errors="coerce")

    merged = frame.merge(latest, on="app_norm", how="left")
    dublin = merged["PlanningAuthority"].isin(DUBLIN_AUTHORITIES)

    fi_new_positive = dublin & merged["fi_dt_reg"].isna() & merged["fi_pipe_yes"].fillna(False)
    appeal_new_positive = dublin & merged["appeal_dt_reg"].isna() & merged["appeal_pipe_yes"].fillna(False) & merged["appeal_pipe_dt"].notna()

    merged["fi_requested_v2"] = (merged["fi_dt_reg"].notna() | fi_new_positive).astype(int)
    merged["fi_date_v2"] = merged["fi_dt_reg"]
    merged["appeal_submitted_v2"] = (merged["appeal_dt_reg"].notna() | appeal_new_positive).astype(int)
    merged["appeal_date_v2"] = merged["appeal_dt_reg"].where(merged["appeal_dt_reg"].notna(), merged["appeal_pipe_dt"])
    merged["fi_source"] = np.where(merged["fi_dt_reg"].notna(), "register", np.where(fi_new_positive, "pipeline", "none"))
    merged["appeal_source"] = np.where(merged["appeal_dt_reg"].notna(), "register", np.where(appeal_new_positive, "pipeline", "none"))

    out_cols = ["case_key", "PlanningAuthority", "ApplicationNumber", "ReceivedDate",
                "fi_requested_v2", "fi_date_v2", "fi_source",
                "appeal_submitted_v2", "appeal_date_v2", "appeal_source"]
    out = merged[out_cols].copy()
    out["fi_date_v2"] = out["fi_date_v2"].astype(str)
    out["appeal_date_v2"] = out["appeal_date_v2"].astype(str)
    out_path = settings.SILVER_DIR / "fi_appeal_labels_v2.csv"
    out.to_csv(out_path, index=False)

    summary = {
        "ge10_rows": int(len(frame)),
        "dublin_rows": int(dublin.sum()),
        "fi_positives_register": int(merged["fi_dt_reg"].notna().sum()),
        "fi_positives_v2": int(merged["fi_requested_v2"].sum()),
        "fi_new_from_pipeline": int(fi_new_positive.sum()),
        "appeal_positives_register": int(merged["appeal_dt_reg"].notna().sum()),
        "appeal_positives_v2": int(merged["appeal_submitted_v2"].sum()),
        "appeal_new_from_pipeline": int(appeal_new_positive.sum()),
        "out": str(out_path),
    }
    (settings.SILVER_DIR / "fi_appeal_labels_v2_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
