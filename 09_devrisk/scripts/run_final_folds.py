"""Runner: fold the two remaining local assets.

1. 4Dublin completion corroboration -> exit/pain labels: Dublin schemes
   with pipeline Units_Completed get a completion-corroboration flag and
   corroborated-completion date band; unlinked schemes with activity on
   site get an activity flag (evidence, not labels).
2. Event ledger -> multi-state engine input: rebuild the multistate
   transition tables from the ledger rather than label pools (ledger
   becomes the single source of dated events).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.labels.event_ledger import build_ledger  # noqa: E402

if __name__ == "__main__":
    report: dict = {}

    # ---- 1. 4Dublin corroboration into labels ----
    corroboration = pd.read_csv(settings.SILVER_DIR / "dublin_activity_corroboration.csv", dtype=str)
    corroboration["Units_Completed_or_Completed_an"] = pd.to_numeric(
        corroboration["Units_Completed_or_Completed_an"], errors="coerce")
    corroboration["Units_Under_Construction"] = pd.to_numeric(
        corroboration["Units_Under_Construction"], errors="coerce")
    corroboration["activity_on_site"] = corroboration["Activity_On_Site"].fillna("").astype(str).str.upper().eq("YES")

    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    exit_labels["case_key"] = exit_labels["scheme_id"].astype(str)
    exit_labels = exit_labels.merge(
        corroboration[["case_key", "Units_Completed_or_Completed_an", "activity_on_site", "Units_Under_Construction"]],
        on="case_key", how="left")
    exit_labels["completion_corroborated_units"] = pd.to_numeric(
        exit_labels["Units_Completed_or_Completed_an"], errors="coerce")
    exit_labels["dublin_activity_on_site"] = exit_labels["activity_on_site"].fillna(False)
    exit_labels = exit_labels.drop(columns=["case_key", "activity_on_site", "Units_Completed_or_Completed_an", "Units_Under_Construction"])
    exit_labels.to_csv(settings.SILVER_DIR / "exit_labels_pool.csv", index=False)
    report["4dublin_fold"] = {
        "schemes_with_corroborated_units": int(exit_labels["completion_corroborated_units"].notna().sum()),
        "schemes_with_activity_flag": int(exit_labels["dublin_activity_on_site"].sum()),
    }

    # ---- 2. Ledger as the multistate input source ----
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    pool = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_pool.parquet")
    cohort = register[register["case_key"].isin(pool["case_key"])].drop_duplicates("case_key").copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    jr = pd.read_csv(settings.SILVER_DIR / "jr_events.csv") if (settings.SILVER_DIR / "jr_events.csv").exists() else None
    ledger = build_ledger(cohort, bcms, links, exit_labels, jr)
    ledger.to_csv(settings.GOLD_DIR / "event_ledger.csv", index=False)

    # Per-development milestone table derived FROM the ledger (single source).
    def first_event_date(group: pd.DataFrame, event_type: str):
        part = group[group["event_type"] == event_type]
        return part["event_date_start"].min() if len(part) else None

    milestones = []
    for development_id, group in ledger.groupby("development_id"):
        milestones.append({
            "development_id": development_id,
            "grant": first_event_date(group, "planning_granted"),
            "commencement": first_event_date(group, "bcms_commencement"),
            "first_ccc": first_event_date(group, "completion_certificate"),
            "first_sale": first_event_date(group, "first_sale"),
        })
    milestone_frame = pd.DataFrame(milestones)
    milestone_frame.to_csv(settings.GOLD_DIR / "ledger_milestones.csv", index=False)
    report["ledger_fold"] = {
        "events": int(len(ledger)),
        "developments": int(len(milestone_frame)),
        "developments_with_commencement": int(milestone_frame["commencement"].notna().sum()),
        "developments_with_ccc": int(milestone_frame["first_ccc"].notna().sum()),
        "developments_with_sale": int(milestone_frame["first_sale"].notna().sum()),
    }

    out = settings.SILVER_DIR / "final_folds.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
